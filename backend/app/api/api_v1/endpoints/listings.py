from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.session import get_db
from app.models.listing import Listing, PriceHistory
from app.schemas.listing import ListingResponse, PriceTrend
from sqlalchemy import func
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/listings", response_model=List[ListingResponse])
def get_listings(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    location: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    bedrooms: Optional[int] = None
):
    query = db.query(Listing)
    
    if location:
        query = query.filter(Listing.location.ilike(f"%{location}%"))
    if bedrooms:
        query = query.filter(Listing.bedrooms == bedrooms)
    
    # Filter by latest price
    if min_price or max_price:
        latest_prices = (
            db.query(
                PriceHistory.listing_id,
                func.max(PriceHistory.recorded_at).label('max_date')
            )
            .group_by(PriceHistory.listing_id)
            .subquery()
        )
        
        query = query.join(
            latest_prices,
            Listing.id == latest_prices.c.listing_id
        ).join(
            PriceHistory,
            (PriceHistory.listing_id == latest_prices.c.listing_id) &
            (PriceHistory.recorded_at == latest_prices.c.max_date)
        )
        
        if min_price:
            query = query.filter(PriceHistory.price >= min_price)
        if max_price:
            query = query.filter(PriceHistory.price <= max_price)
    
    return query.offset(skip).limit(limit).all()

@router.get("/listings/{listing_id}", response_model=ListingResponse)
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    listing = db.query(Listing).filter(Listing.id == listing_id).first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing

@router.get("/price-trends")
def get_price_trends(
    db: Session = Depends(get_db),
    location: Optional[str] = None,
    days: int = Query(default=30, le=365)
):
    start_date = datetime.now() - timedelta(days=days)
    
    query = (
        db.query(
            func.date_trunc('day', PriceHistory.recorded_at).label('date'),
            func.avg(PriceHistory.price).label('avg_price')
        )
        .join(Listing)
    )
    
    if location:
        query = query.filter(Listing.location.ilike(f"%{location}%"))
    
    query = (
        query.filter(PriceHistory.recorded_at >= start_date)
        .group_by(func.date_trunc('day', PriceHistory.recorded_at))
        .order_by(func.date_trunc('day', PriceHistory.recorded_at))
    )
    
    return query.all() 