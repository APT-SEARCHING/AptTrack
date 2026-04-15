from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import PriceSubscription, User
from app.schemas.user import SubscriptionCreate, SubscriptionResponse, SubscriptionUpdate

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post("", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_subscription(
    payload: SubscriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sub = PriceSubscription(**payload.dict(), user_id=current_user.id)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@router.get("", response_model=List[SubscriptionResponse])
def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(PriceSubscription)
        .filter(PriceSubscription.user_id == current_user.id)
        .all()
    )


@router.put("/{sub_id}", response_model=SubscriptionResponse)
def update_subscription(
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
def delete_subscription(
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
