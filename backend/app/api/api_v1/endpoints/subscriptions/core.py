from typing import List

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import PriceSubscription, User
from app.schemas.user import SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
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
    if payload.target_price is None and payload.price_drop_pct is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of target_price or price_drop_pct must be provided",
        )
    sub = PriceSubscription(**payload.model_dump(), user_id=current_user.id)
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
# Helper
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
