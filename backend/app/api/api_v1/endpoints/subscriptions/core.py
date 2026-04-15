from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.db.session import get_db
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
    # At least one targeting criterion must be set so the checker knows what to watch.
    if payload.apartment_id is None and payload.plan_id is None and payload.city is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of apartment_id, plan_id, or city must be provided",
        )
    sub = PriceSubscription(**payload.dict(), user_id=current_user.id)
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
    return (
        db.query(PriceSubscription)
        .filter(PriceSubscription.user_id == current_user.id)
        .all()
    )


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
    for field, value in payload.dict(exclude_unset=True).items():
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
    sub = (
        db.query(PriceSubscription)
        .filter(PriceSubscription.id == sub_id, PriceSubscription.user_id == user_id)
        .first()
    )
    if sub is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    return sub
