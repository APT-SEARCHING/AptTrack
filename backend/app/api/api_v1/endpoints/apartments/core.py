from typing import List, Optional

from app.core.limiter import limiter
from app.core.security import require_admin
from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import User
from app.schemas.apartment import ApartmentCreate, ApartmentResponse, ApartmentUpdate
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/apartments", response_model=List[ApartmentResponse])
@limiter.limit("60/minute")
def get_apartments(
    request: Request,
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
    is_available: Optional[bool] = None,
):
    query = db.query(Apartment)

    if city:
        query = query.filter(Apartment.city.ilike(f"%{city}%"))
    if zipcode:
        query = query.filter(Apartment.zipcode == zipcode)

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
        query = query.distinct()

    if property_type:
        query = query.filter(Apartment.property_type == property_type)
    if is_available is not None:
        query = query.filter(Apartment.is_available == is_available)

    return query.offset(skip).limit(limit).all()


@router.post("/apartments", response_model=ApartmentResponse, status_code=201)
@limiter.limit("10/minute")
def create_apartment(
    request: Request,
    apartment: ApartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    plans_data = None
    if apartment.plans:
        plans_data = apartment.plans
        apartment_dict = apartment.dict(exclude={"plans"})
    else:
        apartment_dict = apartment.dict()

    db_apartment = Apartment(**apartment_dict)
    db.add(db_apartment)
    db.flush()

    if plans_data:
        for plan_data in plans_data:
            plan = Plan(**plan_data.dict(), apartment_id=db_apartment.id)
            plan.price_history = [PlanPriceHistory(price=plan_data.price)]
            db.add(plan)

    db.commit()
    db.refresh(db_apartment)
    return db_apartment


@router.get("/apartments/{apartment_id}", response_model=ApartmentResponse)
@limiter.limit("60/minute")
def get_apartment(
    request: Request,
    apartment_id: int,
    db: Session = Depends(get_db),
):
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return db_apartment


@router.put("/apartments/{apartment_id}", response_model=ApartmentResponse)
@limiter.limit("10/minute")
def update_apartment(
    request: Request,
    apartment_id: int,
    apartment: ApartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    for key, value in apartment.dict(exclude_unset=True).items():
        setattr(db_apartment, key, value)

    db.commit()
    db.refresh(db_apartment)
    return db_apartment


@router.delete("/apartments/{apartment_id}", response_model=dict)
@limiter.limit("10/minute")
def delete_apartment(
    request: Request,
    apartment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db_apartment = db.query(Apartment).filter(Apartment.id == apartment_id).first()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db.delete(db_apartment)
    db.commit()
    return {"message": "Apartment deleted successfully"}
