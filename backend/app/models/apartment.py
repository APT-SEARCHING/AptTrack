import enum

from app.db.base_class import Base
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class PropertyType(enum.Enum):
    APARTMENT = "apartment"
    CONDO = "condo"
    HOUSE = "house"
    TOWNHOUSE = "townhouse"
    STUDIO = "studio"

class Apartment(Base):
    """
    Main apartment table with detailed information about each property
    """
    __tablename__ = "apartments"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True, comment="ID from external source/listing site")
    title = Column(String, nullable=False, comment="Title of the listing")
    description = Column(Text, nullable=True, comment="Full description of the property")

    # Location details
    address = Column(String, nullable=True, comment="Street address")
    city = Column(String, nullable=False, index=True, comment="City name")
    state = Column(String(2), nullable=False, comment="State code (e.g., CA, NY)")
    zipcode = Column(String(10), nullable=False, index=True, comment="ZIP/Postal code")
    latitude = Column(Float, nullable=True, comment="Latitude coordinate")
    longitude = Column(Float, nullable=True, comment="Longitude coordinate")

    # Property details
    property_type = Column(String, nullable=False, default="apartment", comment="Type of property")
    bedrooms = Column(Float, nullable=True, index=True, comment="Number of bedrooms (can be 0.5 for studios with alcoves)")
    bathrooms = Column(Float, nullable=True, comment="Number of bathrooms")
    area_sqft = Column(Float, nullable=True, comment="Square footage of the unit")

    # Amenities
    has_parking = Column(Boolean, nullable=True, comment="Whether parking is available")
    has_pool = Column(Boolean, nullable=True, comment="Whether a pool is available")
    has_gym = Column(Boolean, nullable=True, comment="Whether a gym/fitness center is available")
    has_dishwasher = Column(Boolean, nullable=True, comment="Whether unit has a dishwasher")
    has_air_conditioning = Column(Boolean, nullable=True, comment="Whether unit has air conditioning")
    has_washer_dryer = Column(Boolean, nullable=True, comment="Whether unit has washer/dryer")
    pets_allowed = Column(Boolean, nullable=True, comment="Whether pets are allowed")

    # Current price (most recent)
    current_price = Column(Float, nullable=True, comment="Current listing price")

    # Availability
    available_from = Column(DateTime, nullable=True, comment="Date when the unit becomes available")
    is_available = Column(Boolean, default=True, comment="Whether the unit is currently available")

    # Metadata
    source_url = Column(String, nullable=True, comment="URL of the original listing")
    phone = Column(String, nullable=True, comment="Phone number for the property")
    rating = Column(Float, nullable=True, comment="Google rating (0-5)")
    user_rating_count = Column(Integer, nullable=True, comment="Number of user ratings")
    business_name = Column(String, nullable=True, comment="Official business name of the property")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="When this record was created")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="When this record was last updated")

    # Content-hash short-circuit (Phase 2)
    last_content_hash = Column(String(64), nullable=True, comment="SHA256 of stripped HTML from last fetch — skip scrape when unchanged")
    last_scraped_at = Column(DateTime(timezone=True), nullable=True, comment="When last_content_hash was last computed")

    # Relationships
    plans = relationship("Plan", back_populates="apartment", cascade="all, delete-orphan")
    images = relationship("ApartmentImage", back_populates="apartment", cascade="all, delete-orphan")

class Plan(Base):
    """
    Floor plan details for an apartment
    """
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False)

    # Plan details
    name = Column(String, nullable=False, comment="Name of the floor plan")
    bedrooms = Column(Float, nullable=False, index=True, comment="Number of bedrooms (can be 0.5 for studios with alcoves)")
    bathrooms = Column(Float, nullable=False, comment="Number of bathrooms")
    area_sqft = Column(Float, nullable=False, comment="Square footage of the unit")

    # Price and availability
    price = Column(Float, nullable=True, comment="Current price for this plan; NULL means 'Contact for pricing'")
    available_from = Column(DateTime, nullable=True, comment="Date when this plan becomes available")
    is_available = Column(Boolean, default=True, comment="Whether this plan is currently available")

    # Deep link
    external_url = Column(String, nullable=True, comment="Deep link to this specific plan on the source site")

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), comment="When this record was created")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), comment="When this record was last updated")

    # Relationships
    apartment = relationship("Apartment", back_populates="plans")
    price_history = relationship("PlanPriceHistory", back_populates="plan", cascade="all, delete-orphan")

class PlanPriceHistory(Base):
    """
    Tracks price changes over time for each plan
    """
    __tablename__ = "plan_price_history"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("plans.id", ondelete="CASCADE"), nullable=False)
    price = Column(Float, nullable=False, comment="Price amount")
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), comment="When this price was recorded")

    # Relationship
    plan = relationship("Plan", back_populates="price_history")

class ApartmentImage(Base):
    """
    Stores images associated with each apartment
    """
    __tablename__ = "apartment_images"

    id = Column(Integer, primary_key=True, index=True)
    apartment_id = Column(Integer, ForeignKey("apartments.id", ondelete="CASCADE"), nullable=False)
    url = Column(String, nullable=False, comment="URL to the image")
    caption = Column(String, nullable=True, comment="Optional caption for the image")
    is_primary = Column(Boolean, default=False, comment="Whether this is the primary/main image")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    apartment = relationship("Apartment", back_populates="images")

class Neighborhood(Base):
    """
    Information about neighborhoods/areas
    """
    __tablename__ = "neighborhoods"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True, comment="Neighborhood name")
    city = Column(String, nullable=False, comment="City name")
    state = Column(String(2), nullable=False, comment="State code")
    zipcode = Column(String(10), nullable=True, comment="Primary ZIP/Postal code")
    description = Column(Text, nullable=True, comment="Description of the neighborhood")

    # Metrics
    walkability_score = Column(Integer, nullable=True, comment="Walkability score (0-100)")
    safety_score = Column(Integer, nullable=True, comment="Safety score (0-100)")
    avg_price_per_sqft = Column(Float, nullable=True, comment="Average price per square foot")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
