import secrets
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import PriceSubscription, User
from app.schemas.user import SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_subscription(
    request: Request,
    payload: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.apartment_id is None and payload.plan_id is None and payload.unit_id is None and payload.city is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of apartment_id, plan_id, unit_id, or city must be provided",
        )
    if any(
        v is not None
        for v in (payload.city, payload.zipcode, payload.min_bedrooms, payload.max_bedrooms)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Area-level subscriptions are temporarily disabled. "
                "Subscribe to a specific apartment or plan instead."
            ),
        )
    if payload.target_price is None and payload.price_drop_pct is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of target_price or price_drop_pct must be provided",
        )

    # Resolve baseline price: use frontend-supplied value or infer from DB.
    baseline_price = payload.baseline_price
    if baseline_price is None:
        baseline_price = _infer_baseline(payload, db)
    baseline_recorded_at = datetime.now(timezone.utc) if baseline_price is not None else None

    sub_data = payload.model_dump(exclude={"baseline_price"})
    sub = PriceSubscription(
        **sub_data,
        user_id=current_user.id,
        baseline_price=baseline_price,
        baseline_recorded_at=baseline_recorded_at,
        unsubscribe_token=secrets.token_urlsafe(16),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("", response_model=List[SubscriptionResponse])
@limiter.limit("60/minute")
def list_subscriptions(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Load subs with related objects in 3 queries (selectinload avoids N+1)
    subs = db.execute(
        select(PriceSubscription)
        .where(PriceSubscription.user_id == current_user.id)
        .options(
            selectinload(PriceSubscription.apartment),
            selectinload(PriceSubscription.plan).selectinload(Plan.apartment),
        )
    ).scalars().all()

    if not subs:
        return []

    # Batch-fetch latest prices — one query each for plan-level and apt-level subs
    plan_ids = [s.plan_id for s in subs if s.plan_id is not None]
    apt_ids = [s.apartment_id for s in subs if s.apartment_id is not None and s.plan_id is None]

    latest_by_plan: Dict[int, float] = {}
    if plan_ids:
        # Latest PlanPriceHistory entry per plan via max(recorded_at) subquery
        subq = (
            select(
                PlanPriceHistory.plan_id,
                func.max(PlanPriceHistory.recorded_at).label("max_at"),
            )
            .where(PlanPriceHistory.plan_id.in_(plan_ids))
            .group_by(PlanPriceHistory.plan_id)
            .subquery()
        )
        rows = db.execute(
            select(PlanPriceHistory.plan_id, PlanPriceHistory.price)
            .join(
                subq,
                (PlanPriceHistory.plan_id == subq.c.plan_id)
                & (PlanPriceHistory.recorded_at == subq.c.max_at),
            )
        ).all()
        latest_by_plan = {r.plan_id: r.price for r in rows}

    latest_by_apt: Dict[int, float] = {}
    if apt_ids:
        rows = db.execute(
            select(Plan.apartment_id, func.min(Plan.price))
            .where(
                Plan.apartment_id.in_(apt_ids),
                Plan.is_available.is_(True),
                Plan.price.is_not(None),
            )
            .group_by(Plan.apartment_id)
        ).all()
        latest_by_apt = {r.apartment_id: r[1] for r in rows}

    return [_enrich(s, latest_by_plan, latest_by_apt) for s in subs]


@router.put("/{sub_id}", response_model=SubscriptionResponse)
@limiter.limit("10/minute")
def update_subscription(
    request: Request,
    sub_id: int,
    payload: SubscriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = _get_owned_or_404(sub_id, current_user.id, db)
    was_active = sub.is_active
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sub, field, value)
    if was_active is False and sub.is_active is True:
        _refresh_baseline(sub, db)
    db.commit()
    db.refresh(sub)
    return sub


@router.delete("/{sub_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def delete_subscription(
    request: Request,
    sub_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = _get_owned_or_404(sub_id, current_user.id, db)
    db.delete(sub)
    db.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_owned_or_404(sub_id: int, user_id: int, db: Session) -> PriceSubscription:
    sub = db.execute(
        select(PriceSubscription).where(
            PriceSubscription.id == sub_id,
            PriceSubscription.user_id == user_id,
        )
    ).scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return sub


def _enrich(
    sub: PriceSubscription,
    latest_by_plan: Dict[int, float],
    latest_by_apt: Dict[int, float],
) -> dict:
    """Return a dict suitable for SubscriptionResponse, with enriched display fields."""
    apt = sub.apartment
    plan = sub.plan
    # For plan-level subs apartment_id is null; resolve via plan.apartment
    eff_apt = apt or (plan.apartment if plan else None)
    return {
        # Core ORM fields
        "id": sub.id,
        "user_id": sub.user_id,
        "apartment_id": sub.apartment_id,
        "plan_id": sub.plan_id,
        "city": sub.city,
        "zipcode": sub.zipcode,
        "min_bedrooms": sub.min_bedrooms,
        "max_bedrooms": sub.max_bedrooms,
        "target_price": sub.target_price,
        "price_drop_pct": sub.price_drop_pct,
        "baseline_price": sub.baseline_price,
        "baseline_recorded_at": sub.baseline_recorded_at,
        "notify_email": sub.notify_email,
        "notify_telegram": sub.notify_telegram,
        "telegram_chat_id": sub.telegram_chat_id,
        "is_active": sub.is_active,
        "is_demo": sub.is_demo,
        "last_notified_at": sub.last_notified_at,
        "trigger_count": sub.trigger_count,
        "created_at": sub.created_at,
        # Enriched display fields
        "apartment_title": eff_apt.title if eff_apt else None,
        "apartment_city": eff_apt.city if eff_apt else None,
        "plan_name": plan.name if plan else None,
        "plan_spec": _fmt_plan_spec(plan) if plan else None,
        "latest_price": (
            latest_by_plan.get(sub.plan_id) if sub.plan_id is not None
            else latest_by_apt.get(sub.apartment_id) if sub.apartment_id is not None
            else None
        ),
    }


def _fmt_plan_spec(plan: Plan) -> Optional[str]:
    """Format compact plan spec: '1BR · 1BA · 520 sqft'."""
    parts = []
    if plan.bedrooms is not None:
        b = "Studio" if plan.bedrooms == 0 else f"{int(plan.bedrooms)}BR"
        parts.append(b)
    if plan.bathrooms is not None:
        parts.append(f"{int(plan.bathrooms)}BA")
    if plan.area_sqft:
        parts.append(f"{int(plan.area_sqft):,} sqft")
    return " · ".join(parts) if parts else None


def _refresh_baseline(sub: PriceSubscription, db: Session) -> None:
    """Refresh baseline_price on re-arm (False → True toggle).

    Pulls the current price from PlanPriceHistory so price_drop_pct is
    anchored to now, not to whatever stale baseline existed when the sub
    was first created. Always clears last_notified_at so the debounce
    window resets cleanly for the new arm period.
    """
    from app.services.price_checker import _get_latest_price

    new_baseline = _get_latest_price(sub, db)
    if new_baseline is not None:
        sub.baseline_price = new_baseline
        sub.baseline_recorded_at = datetime.now(timezone.utc)
    sub.last_notified_at = None


def _infer_baseline(payload: SubscriptionCreate, db: Session) -> Optional[float]:
    """Compute the current price for the subscription target to use as baseline."""
    if payload.unit_id is not None:
        from app.models.apartment import Unit
        return db.execute(
            select(Unit.price).where(Unit.id == payload.unit_id, Unit.is_available.is_(True))
        ).scalar_one_or_none()

    if payload.plan_id is not None:
        # Latest price history entry, falling back to Plan.price
        price = db.execute(
            select(PlanPriceHistory.price)
            .where(PlanPriceHistory.plan_id == payload.plan_id)
            .order_by(PlanPriceHistory.recorded_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if price is not None:
            return price
        return db.execute(
            select(Plan.price).where(Plan.id == payload.plan_id)
        ).scalar_one_or_none()

    if payload.apartment_id is not None:
        return db.execute(
            select(func.min(Plan.price))
            .where(
                Plan.apartment_id == payload.apartment_id,
                Plan.is_available.is_(True),
                Plan.price.is_not(None),
            )
        ).scalar_one_or_none()

    # Area-level
    stmt = (
        select(func.avg(Plan.price))
        .join(Apartment, Plan.apartment_id == Apartment.id)
        .where(Plan.is_available.is_(True), Plan.price.is_not(None))
    )
    if payload.city:
        stmt = stmt.where(func.lower(Apartment.city) == payload.city.lower())
    if payload.zipcode:
        stmt = stmt.where(Apartment.zipcode == payload.zipcode)
    if payload.min_bedrooms is not None:
        stmt = stmt.where(Plan.bedrooms >= payload.min_bedrooms)
    if payload.max_bedrooms is not None:
        stmt = stmt.where(Plan.bedrooms <= payload.max_bedrooms)
    return db.execute(stmt).scalar_one_or_none()
