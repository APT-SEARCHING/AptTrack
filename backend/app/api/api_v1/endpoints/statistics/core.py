from datetime import datetime, timedelta
from typing import List, Optional

from app.core.limiter import limiter
from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.schemas.apartment import PriceTrend
from fastapi import APIRouter, Depends, Request
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

router = APIRouter()


@router.get("/stats/price-trends", response_model=List[PriceTrend])
@limiter.limit("60/minute")
def get_price_trends(
    request: Request,
    db: Session = Depends(get_db),
    days: int = 30,
    city: Optional[str] = None,
    bedrooms: Optional[float] = None,
):
    start_date = datetime.now() - timedelta(days=days)

    stmt = (
        select(
            cast(PlanPriceHistory.recorded_at, Date).label("date"),
            func.avg(PlanPriceHistory.price).label("avg_price"),
        )
        .join(Plan)
        .join(Apartment)
    )

    if city:
        stmt = stmt.where(Apartment.city.ilike(f"%{city}%"))
    if bedrooms is not None:
        stmt = stmt.where(Plan.bedrooms == bedrooms)

    stmt = (
        stmt.where(PlanPriceHistory.recorded_at >= start_date)
        .group_by(cast(PlanPriceHistory.recorded_at, Date))
        .order_by(cast(PlanPriceHistory.recorded_at, Date))
    )
    result = db.execute(stmt).all()
    return [{"date": date, "avg_price": avg_price} for date, avg_price in result]


@router.get("/stats/apartments-by-city", response_model=List[dict])
@limiter.limit("60/minute")
def get_apartments_by_city(
    request: Request,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(Apartment.city, func.count(Apartment.id).label("count"))
        .group_by(Apartment.city)
    ).all()
    return [{"city": city, "count": count} for city, count in result]


@router.get("/stats/apartments-by-property-type", response_model=List[dict])
@limiter.limit("60/minute")
def get_apartments_by_property_type(
    request: Request,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(Apartment.property_type, func.count(Apartment.id).label("count"))
        .group_by(Apartment.property_type)
    ).all()
    return [{"property_type": pt, "count": count} for pt, count in result]


@router.get("/stats/average-price-by-bedrooms", response_model=List[dict])
@limiter.limit("60/minute")
def get_average_price_by_bedrooms(
    request: Request,
    db: Session = Depends(get_db),
    city: Optional[str] = None,
):
    stmt = (
        select(Plan.bedrooms, func.avg(Plan.price).label("avg_price"))
        .join(Apartment)
    )
    if city:
        stmt = stmt.where(Apartment.city.ilike(f"%{city}%"))
    stmt = stmt.group_by(Plan.bedrooms).order_by(Plan.bedrooms)
    result = db.execute(stmt).all()
    return [{"bedrooms": bedrooms, "avg_price": avg_price} for bedrooms, avg_price in result]


@router.get("/stats/plans-by-bedrooms", response_model=List[dict])
@limiter.limit("60/minute")
def get_plans_by_bedrooms(
    request: Request,
    db: Session = Depends(get_db),
):
    result = db.execute(
        select(Plan.bedrooms, func.count(Plan.id).label("count"))
        .group_by(Plan.bedrooms)
        .order_by(Plan.bedrooms)
    ).all()
    return [{"bedrooms": bedrooms, "count": count} for bedrooms, count in result]


@router.get("/stats/average-area-by-bedrooms", response_model=List[dict])
@limiter.limit("60/minute")
def get_average_area_by_bedrooms(
    request: Request,
    db: Session = Depends(get_db),
    city: Optional[str] = None,
):
    stmt = (
        select(Plan.bedrooms, func.avg(Plan.area_sqft).label("avg_area"))
        .join(Apartment)
    )
    if city:
        stmt = stmt.where(Apartment.city.ilike(f"%{city}%"))
    stmt = stmt.group_by(Plan.bedrooms).order_by(Plan.bedrooms)
    result = db.execute(stmt).all()
    return [{"bedrooms": bedrooms, "avg_area": avg_area} for bedrooms, avg_area in result]
