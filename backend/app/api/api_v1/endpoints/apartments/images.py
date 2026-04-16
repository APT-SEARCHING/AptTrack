from typing import List

from app.core.limiter import limiter
from app.core.security import require_admin
from app.db.session import get_db
from app.models.apartment import Apartment, ApartmentImage
from app.models.user import User
from app.schemas.apartment import ApartmentImageCreate, ApartmentImageResponse
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/apartments/{apartment_id}/images", response_model=List[ApartmentImageResponse])
@limiter.limit("60/minute")
def get_apartment_images(
    request: Request,
    apartment_id: int,
    db: Session = Depends(get_db),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return db_apartment.images


@router.post("/apartments/{apartment_id}/images", response_model=ApartmentImageResponse, status_code=201)
@limiter.limit("10/minute")
def add_apartment_image(
    request: Request,
    apartment_id: int,
    image: ApartmentImageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    if image.is_primary:
        db.execute(
            update(ApartmentImage)
            .where(ApartmentImage.apartment_id == apartment_id, ApartmentImage.is_primary == True)  # noqa: E712
            .values(is_primary=False)
        )

    db_image = ApartmentImage(**image.model_dump(), apartment_id=apartment_id)
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image


@router.put("/apartments/{apartment_id}/images/{image_id}", response_model=ApartmentImageResponse)
@limiter.limit("10/minute")
def update_apartment_image(
    request: Request,
    apartment_id: int,
    image_id: int,
    image_update: ApartmentImageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db_image = db.execute(
        select(ApartmentImage).where(
            ApartmentImage.id == image_id,
            ApartmentImage.apartment_id == apartment_id,
        )
    ).scalar_one_or_none()
    if db_image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    if image_update.is_primary and not db_image.is_primary:
        db.execute(
            update(ApartmentImage)
            .where(ApartmentImage.apartment_id == apartment_id, ApartmentImage.is_primary == True)  # noqa: E712
            .values(is_primary=False)
        )

    for key, value in image_update.model_dump().items():
        setattr(db_image, key, value)

    db.commit()
    db.refresh(db_image)
    return db_image


@router.delete("/apartments/{apartment_id}/images/{image_id}", response_model=dict)
@limiter.limit("10/minute")
def delete_apartment_image(
    request: Request,
    apartment_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db_image = db.execute(
        select(ApartmentImage).where(
            ApartmentImage.id == image_id,
            ApartmentImage.apartment_id == apartment_id,
        )
    ).scalar_one_or_none()
    if db_image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    db.delete(db_image)
    db.commit()
    return {"message": "Image deleted successfully"}
