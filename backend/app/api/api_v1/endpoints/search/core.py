from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.db.session import get_db
from app.models.apartment import Apartment, Plan
from app.schemas.apartment import ApartmentResponse

router = APIRouter()


@router.get("/search", response_model=List[ApartmentResponse])
@limiter.limit("60/minute")
def search_apartments(
    request: Request,
    query: str = Query(..., description="Search query for apartments"),
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    min_bedrooms: Optional[float] = None,
    max_bedrooms: Optional[float] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
):
    search_query = f"%{query}%"

    stmt = select(Apartment).distinct().where(
        (Apartment.title.ilike(search_query))
        | (Apartment.description.ilike(search_query))
        | (Apartment.city.ilike(search_query))
        | (Apartment.zipcode.ilike(search_query))
        | (Apartment.address.ilike(search_query))
    )

    if any([min_bedrooms, max_bedrooms, min_price, max_price]):
        stmt = stmt.join(Plan)
        if min_bedrooms is not None:
            stmt = stmt.where(Plan.bedrooms >= min_bedrooms)
        if max_bedrooms is not None:
            stmt = stmt.where(Plan.bedrooms <= max_bedrooms)
        if min_price is not None:
            stmt = stmt.where(Plan.price >= min_price)
        if max_price is not None:
            stmt = stmt.where(Plan.price <= max_price)

    return db.execute(stmt.offset(skip).limit(limit)).scalars().all()
