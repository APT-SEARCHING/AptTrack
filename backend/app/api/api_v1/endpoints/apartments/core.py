from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.schemas.apartment import ApartmentResponse, ApartmentCreate, ApartmentUpdate

router = APIRouter()

@router.get("/apartments", response_model=List[ApartmentResponse])
def get_apartments(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    city: Optional[str] = None,
    zipcode: Optional[str] = None,
    min_bedrooms: Optional[float] = None,
    max_bedrooms: Optional[float] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    property_type: Optional[str] = None,
    is_available: Optional[bool] = None
):
    """
    Get all apartments with optional filtering
    """
    query = db.query(Apartment)
    
    # Apply filters
    if city:
        query = query.filter(Apartment.city.ilike(f"%{city}%"))
    if zipcode:
        query = query.filter(Apartment.zipcode == zipcode)
    
    # Join with plans for plan-specific filters
    if any([min_bedrooms, max_bedrooms, min_price, max_price]):
        query = query.join(Plan)
        
        if min_bedrooms is not None:
            query = query.filter(Plan.bedrooms >= min_bedrooms)
        if max_bedrooms is not None:
            query = query.filter(Plan.bedrooms <= max_bedrooms)
        if min_price is not None:
            query = query.filter(Plan.price >= min_price)
        if max_price is not None:
            query = query.filter(Plan.price <= max_price)
        
        # Make sure we get distinct apartments
        query = query.distinct()
    
    if property_type:
        query = query.filter(Apartment.property_type == property_type)
    if is_available is not None:
        query = query.filter(Apartment.is_available == is_available)
    
    return query.offset(skip).limit(limit).all()

@router.post("/apartments", response_model=ApartmentResponse)
def create_apartment(
    apartment: ApartmentCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new apartment listing
    """
    # Extract plans data if provided
    plans_data = None
    if apartment.plans:
        plans_data = apartment.plans
        apartment_dict = apartment.dict(exclude={"plans"})
    else:
        apartment_dict = apartment.dict()
    
    # Create apartment
    db_apartment = Apartment(**apartment_dict)
    db.add(db_apartment)
    db.flush()  # Get the ID without committing
    
    # Create plans if provided
    if plans_data:
        for plan_data in plans_data:
            plan = Plan(**plan_data.dict(), apartment_id=db_apartment.id)
            
            # Create price history entry
            price_history = PlanPriceHistory(price=plan_data.price)
            plan.price_history = [price_history]
            
            db.add(plan)
    
    db.commit()
    db.refresh(db_apartment)
    return db_apartment

@router.get("/apartments/{apartment_id}", response_model=ApartmentResponse)
def get_apartment(
    apartment_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific apartment by ID
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return db_apartment

@router.put("/apartments/{apartment_id}", response_model=ApartmentResponse)
def update_apartment(
    apartment_id: int,
    apartment: ApartmentUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an apartment listing
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    # Update apartment fields
    update_data = apartment.dict(exclude_unset=True)
    
    # Update the apartment object
    for key, value in update_data.items():
        setattr(db_apartment, key, value)
    
    db.commit()
    db.refresh(db_apartment)
    return db_apartment

@router.delete("/apartments/{apartment_id}", response_model=dict)
def delete_apartment(
    apartment_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete an apartment listing
    """
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    db.delete(db_apartment)
    db.commit()
    return {"message": "Apartment deleted successfully"} 