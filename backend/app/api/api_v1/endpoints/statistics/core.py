from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.db.session import get_db
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.schemas.apartment import PriceTrend

router = APIRouter()

@router.get("/stats/price-trends", response_model=List[PriceTrend])
def get_price_trends(
    db: Session = Depends(get_db),
    days: int = 30,
    city: Optional[str] = None,
    bedrooms: Optional[float] = None
):
    """
    Get price trends over time
    """
    from sqlalchemy import func, cast, Date
    
    # Calculate the start date
    start_date = datetime.now() - timedelta(days=days)
    
    # Base query
    query = db.query(
        cast(PlanPriceHistory.recorded_at, Date).label('date'),
        func.avg(PlanPriceHistory.price).label('avg_price')
    ).join(Plan).join(Apartment)
    
    # Apply filters
    if city:
        query = query.filter(Apartment.city.ilike(f"%{city}%"))
    if bedrooms is not None:
        query = query.filter(Plan.bedrooms == bedrooms)
    
    # Filter by date and group by date
    result = query.filter(PlanPriceHistory.recorded_at >= start_date) \
        .group_by(cast(PlanPriceHistory.recorded_at, Date)) \
        .order_by(cast(PlanPriceHistory.recorded_at, Date)) \
        .all()
    
    return [{"date": date, "avg_price": avg_price} for date, avg_price in result]

@router.get("/stats/apartments-by-city", response_model=List[dict])
def get_apartments_by_city(
    db: Session = Depends(get_db)
):
    """
    Get apartment count by city
    """
    from sqlalchemy import func
    
    result = db.query(
        Apartment.city,
        func.count(Apartment.id).label('count')
    ).group_by(Apartment.city).all()
    
    return [{"city": city, "count": count} for city, count in result]

@router.get("/stats/apartments-by-property-type", response_model=List[dict])
def get_apartments_by_property_type(
    db: Session = Depends(get_db)
):
    """
    Get apartment count by property type
    """
    from sqlalchemy import func
    
    result = db.query(
        Apartment.property_type,
        func.count(Apartment.id).label('count')
    ).group_by(Apartment.property_type).all()
    
    return [{"property_type": property_type, "count": count} for property_type, count in result]

@router.get("/stats/average-price-by-bedrooms", response_model=List[dict])
def get_average_price_by_bedrooms(
    db: Session = Depends(get_db),
    city: Optional[str] = None
):
    """
    Get average price by number of bedrooms
    """
    from sqlalchemy import func
    
    query = db.query(
        Plan.bedrooms,
        func.avg(Plan.price).label('avg_price')
    ).join(Apartment)
    
    if city:
        query = query.filter(Apartment.city.ilike(f"%{city}%"))
    
    result = query.group_by(Plan.bedrooms).order_by(Plan.bedrooms).all()
    
    return [{"bedrooms": bedrooms, "avg_price": avg_price} for bedrooms, avg_price in result]

@router.get("/stats/plans-by-bedrooms", response_model=List[dict])
def get_plans_by_bedrooms(
    db: Session = Depends(get_db)
):
    """
    Get plan count by number of bedrooms
    """
    from sqlalchemy import func
    
    result = db.query(
        Plan.bedrooms,
        func.count(Plan.id).label('count')
    ).group_by(Plan.bedrooms).order_by(Plan.bedrooms).all()
    
    return [{"bedrooms": bedrooms, "count": count} for bedrooms, count in result]

@router.get("/stats/average-area-by-bedrooms", response_model=List[dict])
def get_average_area_by_bedrooms(
    db: Session = Depends(get_db),
    city: Optional[str] = None
):
    """
    Get average area by number of bedrooms
    """
    from sqlalchemy import func
    
    query = db.query(
        Plan.bedrooms,
        func.avg(Plan.area_sqft).label('avg_area')
    ).join(Apartment)
    
    if city:
        query = query.filter(Apartment.city.ilike(f"%{city}%"))
    
    result = query.group_by(Plan.bedrooms).order_by(Plan.bedrooms).all()
    
    return [{"bedrooms": bedrooms, "avg_area": avg_area} for bedrooms, avg_area in result] 