from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.session import get_db
from app.models.apartment import Apartment, Plan
from app.schemas.apartment import ApartmentResponse

router = APIRouter()

@router.get("/search", response_model=List[ApartmentResponse])
def search_apartments(
    query: str = Query(..., description="Search query for apartments"),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    min_bedrooms: Optional[float] = None,
    max_bedrooms: Optional[float] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None
):
    """
    Search for apartments by title, description, or location
    """
    search_query = f"%{query}%"
    
    # Base query
    db_query = db.query(Apartment).distinct()
    
    # Apply text search filters
    db_query = db_query.filter(
        (Apartment.title.ilike(search_query)) |
        (Apartment.description.ilike(search_query)) |
        (Apartment.city.ilike(search_query)) |
        (Apartment.zipcode.ilike(search_query)) |
        (Apartment.address.ilike(search_query))
    )
    
    # Apply plan-specific filters if needed
    if any([min_bedrooms, max_bedrooms, min_price, max_price]):
        db_query = db_query.join(Plan)
        
        if min_bedrooms is not None:
            db_query = db_query.filter(Plan.bedrooms >= min_bedrooms)
        if max_bedrooms is not None:
            db_query = db_query.filter(Plan.bedrooms <= max_bedrooms)
        if min_price is not None:
            db_query = db_query.filter(Plan.price >= min_price)
        if max_price is not None:
            db_query = db_query.filter(Plan.price <= max_price)
    
    return db_query.offset(skip).limit(limit).all() 