import secrets
from datetime import datetime, timezone
from typing import List, Optional

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import PriceSubscription, User
from app.schemas.user import SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def create_subscription(
    request: Request,
    payload: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.apartment_id is None and payload.plan_id is None and payload.city is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of apartment_id, plan_id, or city must be provided",
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
    return db.execute(
        select(PriceSubscription).where(PriceSubscription.user_id == current_user.id)
    ).scalars().all()


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
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(sub, field, value)
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


def _infer_baseline(payload: SubscriptionCreate, db: Session) -> Optional[float]:
    """Compute the current price for the subscription target to use as baseline."""
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
