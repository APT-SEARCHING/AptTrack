from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PropertyType(str, Enum):
    APARTMENT = "apartment"
    CONDO = "condo"
    HOUSE = "house"
    TOWNHOUSE = "townhouse"
    STUDIO = "studio"


class PlanPriceHistoryBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    price: float
    recorded_at: datetime


class PlanBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    bedrooms: float
    bathrooms: float
    area_sqft: Optional[float] = None
    price: float
    available_from: Optional[datetime] = None
    is_available: bool = True


class PlanCreate(PlanBase):
    pass


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    bedrooms: Optional[float] = None
    bathrooms: Optional[float] = None
    area_sqft: Optional[float] = None
    price: Optional[float] = None
    available_from: Optional[datetime] = None
    is_available: Optional[bool] = None


class PlanInDB(PlanBase):
    id: int
    apartment_id: int
    created_at: datetime
    updated_at: datetime


class PlanResponse(PlanInDB):
    price_history: list[PlanPriceHistoryBase] = []


class ApartmentImageBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url: str
    caption: Optional[str] = None
    is_primary: bool = False


class ApartmentBase(BaseModel):
    external_id: Optional[str] = None
    title: str
    description: Optional[str] = None

    # Location details
    address: Optional[str] = None
    city: str
    state: str = Field(..., min_length=2, max_length=2)
    zipcode: str = Field(..., min_length=5, max_length=10)
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Property details
    property_type: PropertyType = PropertyType.APARTMENT

    # Amenities
    has_parking: Optional[bool] = None
    has_pool: Optional[bool] = None
    has_gym: Optional[bool] = None
    has_dishwasher: Optional[bool] = None
    has_air_conditioning: Optional[bool] = None
    has_washer_dryer: Optional[bool] = None
    pets_allowed: Optional[bool] = None

    # Availability
    is_available: bool = True

    # Metadata
    source_url: Optional[str] = None


class ApartmentCreate(ApartmentBase):
    plans: Optional[list[PlanCreate]] = None


class ApartmentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    property_type: Optional[PropertyType] = None
    has_parking: Optional[bool] = None
    has_pool: Optional[bool] = None
    has_gym: Optional[bool] = None
    has_dishwasher: Optional[bool] = None
    has_air_conditioning: Optional[bool] = None
    has_washer_dryer: Optional[bool] = None
    pets_allowed: Optional[bool] = None
    is_available: Optional[bool] = None
    source_url: Optional[str] = None


class ApartmentInDB(ApartmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class ApartmentResponse(ApartmentInDB):
    plans: list[PlanResponse] = []
    images: list[ApartmentImageBase] = []


class ApartmentImageCreate(BaseModel):
    url: str
    caption: Optional[str] = None
    is_primary: bool = False


class ApartmentImageResponse(ApartmentImageBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    apartment_id: int
    created_at: datetime


class NeighborhoodBase(BaseModel):
    name: str
    city: str
    state: str = Field(..., min_length=2, max_length=2)
    zipcode: Optional[str] = None
    description: Optional[str] = None
    walkability_score: Optional[int] = Field(None, ge=0, le=100)
    safety_score: Optional[int] = Field(None, ge=0, le=100)
    avg_price_per_sqft: Optional[float] = None


class NeighborhoodCreate(NeighborhoodBase):
    pass


class NeighborhoodUpdate(BaseModel):
    name: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    description: Optional[str] = None
    walkability_score: Optional[int] = Field(None, ge=0, le=100)
    safety_score: Optional[int] = Field(None, ge=0, le=100)
    avg_price_per_sqft: Optional[float] = None


class NeighborhoodInDB(NeighborhoodBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


class PriceTrend(BaseModel):
    date: datetime
    avg_price: float


class ApartmentFilter(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_bedrooms: Optional[float] = None
    max_bedrooms: Optional[float] = None
    min_bathrooms: Optional[float] = None
    max_bathrooms: Optional[float] = None
    min_area: Optional[float] = None
    max_area: Optional[float] = None
    city: Optional[str] = None
    zipcode: Optional[str] = None
    property_type: Optional[PropertyType] = None
    has_parking: Optional[bool] = None
    has_pool: Optional[bool] = None
    has_gym: Optional[bool] = None
    pets_allowed: Optional[bool] = None
    available_from: Optional[datetime] = None
    is_available: Optional[bool] = None
