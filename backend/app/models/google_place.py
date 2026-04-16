from app.db.base_class import Base
from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.sql import func


class GooglePlaceRaw(Base):
    """
    Stores raw Google Places v1 Place details responses for traceability.
    """
    __tablename__ = "google_places_raw"

    id = Column(Integer, primary_key=True, index=True)

    # Stable resource name from Places API, e.g., "places/<place_id>"
    place_resource_name = Column(String, unique=True, index=True, nullable=False)

    # Commonly used surfaced fields (duplicated for easy querying)
    place_id = Column(String, index=True, nullable=True)
    display_name = Column(String, nullable=True)
    formatted_address = Column(String, nullable=True)
    website_uri = Column(String, nullable=True)
    national_phone_number = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    user_rating_count = Column(Integer, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Full raw JSON payload from Places API
    raw_json = Column(JSON, nullable=False)

    source = Column(String, nullable=False, default="google_places_v1")
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class GoogleApartment(Base):
    """
    Normalized apartment details derived from Google Places data, kept separate
    from the main `apartments` table to avoid impacting existing schema.
    """
    __tablename__ = "google_apartments"

    id = Column(Integer, primary_key=True, index=True)

    # Link back to the raw place (resource name)
    place_resource_name = Column(String, index=True, nullable=False)
    external_id = Column(String, unique=True, index=True, nullable=False)  # e.g., "google_<resource_name>"

    # Business/listing identity
    business_name = Column(String, nullable=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    # Location
    address = Column(String, nullable=True)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)
    zipcode = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Metadata
    property_type = Column(String, nullable=False, default="apartment")
    source_url = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    user_rating_count = Column(Integer, nullable=True)
    source = Column(String, nullable=False, default="google")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


