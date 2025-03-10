from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.models.apartment import Apartment, ApartmentImage
from app.schemas.apartment import ApartmentImageCreate, ApartmentImageResponse

router = APIRouter()

@router.post("/apartments/{apartment_id}/images", response_model=ApartmentImageResponse)
def add_apartment_image(
    apartment_id: int,
    image: ApartmentImageCreate,
    db: Session = Depends(get_db)
):
    """
    Add an image to an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    # If this is marked as primary, unset any existing primary images
    if image.is_primary:
        db.query(ApartmentImage).filter(
            ApartmentImage.apartment_id == apartment_id,
            ApartmentImage.is_primary == True
        ).update({"is_primary": False})
    
    db_image = ApartmentImage(**image.dict(), apartment_id=apartment_id)
    db.add(db_image)
    db.commit()
    db.refresh(db_image)
    return db_image

@router.get("/apartments/{apartment_id}/images", response_model=List[ApartmentImageResponse])
def get_apartment_images(
    apartment_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all images for an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    return db_apartment.images

@router.delete("/apartments/{apartment_id}/images/{image_id}", response_model=dict)
def delete_apartment_image(
    apartment_id: int,
    image_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete an image from an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    db_image = db.query(ApartmentImage).filter(
        ApartmentImage.id == image_id,
        ApartmentImage.apartment_id == apartment_id
    ).first()
    
    if db_image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    
    db.delete(db_image)
    db.commit()
    return {"message": "Image deleted successfully"}

@router.put("/apartments/{apartment_id}/images/{image_id}", response_model=ApartmentImageResponse)
def update_apartment_image(
    apartment_id: int,
    image_id: int,
    image_update: ApartmentImageCreate,
    db: Session = Depends(get_db)
):
    """
    Update an image for an apartment
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    db_image = db.query(ApartmentImage).filter(
        ApartmentImage.id == image_id,
        ApartmentImage.apartment_id == apartment_id
    ).first()
    
    if db_image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    
    # If this is marked as primary, unset any existing primary images
    if image_update.is_primary and not db_image.is_primary:
        db.query(ApartmentImage).filter(
            ApartmentImage.apartment_id == apartment_id,
            ApartmentImage.is_primary == True
        ).update({"is_primary": False})
    
    # Update image fields
    update_data = image_update.dict()
    for key, value in update_data.items():
        setattr(db_image, key, value)
    
    db.commit()
    db.refresh(db_image)
    return db_image 