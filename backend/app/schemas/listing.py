from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class PriceHistoryBase(BaseModel):
    price: float
    recorded_at: datetime

    class Config:
        from_attributes = True

class ListingResponse(BaseModel):
    id: int
    external_id: str
    title: str
    description: str
    location: str
    bedrooms: int
    bathrooms: float
    area_sqft: float
    created_at: datetime
    updated_at: Optional[datetime]
    price_history: List[PriceHistoryBase]

    class Config:
        from_attributes = True

class PriceTrend(BaseModel):
    date: datetime
    avg_price: float 