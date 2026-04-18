"""Pydantic models for apartment data extracted by the agentic scraper."""

from typing import List, Optional

from pydantic import BaseModel, Field


class FloorPlan(BaseModel):
    name: str = Field(..., description="Plan name, e.g. 'Studio', '1 Bed/1 Bath', 'Plan A'")
    unit_number: Optional[str] = Field(None, description="Specific unit identifier, e.g. 'E316', '4B', '#201'. None when price is a plan-level range.")
    bedrooms: Optional[float] = Field(None, description="Bedroom count (0 for studio)")
    bathrooms: Optional[float] = Field(None, description="Bathroom count")
    size_sqft: Optional[float] = Field(None, description="Square footage")
    min_price: Optional[float] = Field(None, description="Starting monthly rent in USD")
    max_price: Optional[float] = Field(None, description="Maximum monthly rent in USD")
    availability: Optional[str] = Field(None, description="'Available', 'Now', a date, or 'Waitlist'")
    external_url: Optional[str] = Field(None, description="Deep link to this specific plan on the source site")


class ApartmentData(BaseModel):
    name: str = Field(..., description="Apartment complex name")
    address: Optional[str] = Field(None, description="Full street address")
    phone: Optional[str] = Field(None, description="Contact phone number")
    website: Optional[str] = Field(None, description="Website URL that was scraped")
    floor_plans: List[FloorPlan] = Field(default_factory=list, description="All floor plan configurations found")
