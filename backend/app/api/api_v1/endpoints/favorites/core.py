from typing import List

from app.core.limiter import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.apartment import Apartment
from app.models.favorite import ApartmentFavorite
from app.models.user import User
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=List[int])
@limiter.limit("60/minute")
def list_favorites(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[int]:
    """Return the list of apartment IDs the current user has favorited."""
    rows = db.execute(
        select(ApartmentFavorite.apartment_id)
        .where(ApartmentFavorite.user_id == current_user.id)
        .order_by(ApartmentFavorite.created_at.desc())
    ).scalars().all()
    return list(rows)


@router.post("/{apartment_id}", status_code=status.HTTP_201_CREATED)
@limiter.limit("60/minute")
def add_favorite(
    request: Request,
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Verify apartment exists
    exists = db.execute(
        select(Apartment.id).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Apartment not found")

    fav = ApartmentFavorite(user_id=current_user.id, apartment_id=apartment_id)
    db.add(fav)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Already favorited — treat as idempotent success
    return {"apartment_id": apartment_id, "favorited": True}


@router.delete("/{apartment_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
def remove_favorite(
    request: Request,
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    fav = db.execute(
        select(ApartmentFavorite).where(
            ApartmentFavorite.user_id == current_user.id,
            ApartmentFavorite.apartment_id == apartment_id,
        )
    ).scalar_one_or_none()
    if fav is not None:
        db.delete(fav)
        db.commit()
