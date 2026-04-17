from datetime import date
from typing import List, Optional

from app.core.limiter import limiter
from app.core.security import require_admin
from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import User
from app.schemas.apartment import ApartmentCreate, ApartmentResponse, ApartmentUpdate
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import asc, desc, exists, func, select
from sqlalchemy.orm import Session

router = APIRouter()


_SORT_OPTIONS = {"price_asc", "price_desc", "updated_desc", "name_asc"}


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
    pets_allowed: Optional[bool] = None,
    has_parking: Optional[bool] = None,
    min_sqft: Optional[float] = None,
    max_sqft: Optional[float] = None,
    available_before: Optional[date] = None,
    sort: str = Query(default="price_asc", description="price_asc | price_desc | updated_desc | name_asc"),
):
    if sort not in _SORT_OPTIONS:
        raise HTTPException(status_code=422, detail=f"sort must be one of {sorted(_SORT_OPTIONS)}")

    stmt = select(Apartment)

    if city:
        stmt = stmt.where(Apartment.city.ilike(f"%{city}%"))
    if zipcode:
        stmt = stmt.where(Apartment.zipcode == zipcode)

    # Apartment-level boolean filters — direct WHERE, use the new indexes
    if pets_allowed is not None:
        stmt = stmt.where(Apartment.pets_allowed.is_(pets_allowed))
    if has_parking is not None:
        stmt = stmt.where(Apartment.has_parking.is_(has_parking))

    if property_type:
        stmt = stmt.where(Apartment.property_type == property_type)
    if is_available is not None:
        stmt = stmt.where(Apartment.is_available == is_available)

    # Plan-level filters: join once if any are needed, then .distinct()
    plan_filters = [min_bedrooms, max_bedrooms, min_price, max_price, min_sqft, max_sqft, available_before]
    if any(f is not None for f in plan_filters):
        stmt = stmt.join(Plan)
        if min_bedrooms is not None:
            stmt = stmt.where(Plan.bedrooms >= min_bedrooms)
        if max_bedrooms is not None:
            stmt = stmt.where(Plan.bedrooms <= max_bedrooms)
        if min_price is not None:
            stmt = stmt.where(Plan.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(Plan.price <= max_price)
        if min_sqft is not None:
            stmt = stmt.where(Plan.area_sqft >= min_sqft)
        if max_sqft is not None:
            stmt = stmt.where(Plan.area_sqft <= max_sqft)
        if available_before is not None:
            stmt = stmt.where(
                Plan.available_from.isnot(None),
                Plan.available_from <= available_before,
            )
        stmt = stmt.distinct()

    # price_asc / price_desc: sort by the minimum available plan price for each
    # apartment.  Apartments with no priced plans sort last (NULLs last).
    if sort in ("price_asc", "price_desc"):
        price_subq = (
            select(
                Plan.apartment_id,
                func.min(Plan.price).label("min_price"),
            )
            .where(Plan.is_available.is_(True), Plan.price.isnot(None))
            .group_by(Plan.apartment_id)
            .subquery()
        )
        stmt = stmt.outerjoin(price_subq, Apartment.id == price_subq.c.apartment_id)
        if sort == "price_asc":
            stmt = stmt.order_by(asc(func.coalesce(price_subq.c.min_price, 999_999_999)))
        else:
            stmt = stmt.order_by(desc(func.coalesce(price_subq.c.min_price, 0)))
    elif sort == "updated_desc":
        stmt = stmt.order_by(desc(Apartment.updated_at))
    elif sort == "name_asc":
        stmt = stmt.order_by(asc(Apartment.title))

    return db.execute(stmt.offset(skip).limit(limit)).scalars().all()


@router.post("/apartments", response_model=ApartmentResponse, status_code=201)
@limiter.limit("10/minute")
def create_apartment(
    request: Request,
    apartment: ApartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    plans_data = apartment.plans or []
    apartment_dict = apartment.model_dump(exclude={"plans"})

    db_apartment = Apartment(**apartment_dict)
    db.add(db_apartment)
    db.flush()

    if plans_data:
        for plan_data in plans_data:
            plan = Plan(**plan_data.model_dump(), apartment_id=db_apartment.id)
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
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
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
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    for key, value in apartment.model_dump(exclude_unset=True).items():
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
    db_apartment = db.execute(
        select(Apartment).where(Apartment.id == apartment_id)
    ).scalar_one_or_none()
    if db_apartment is None:
        raise HTTPException(status_code=404, detail="Apartment not found")

    db.delete(db_apartment)
    db.commit()
    return {"message": "Apartment deleted successfully"}
