from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base_class import Base

class Listing(Base):
    __tablename__ = "listings"
    
    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, index=True)
    title = Column(String)
    description = Column(String)
    location = Column(String, index=True)
    bedrooms = Column(Integer)
    bathrooms = Column(Float)
    area_sqft = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship with price history
    price_history = relationship("PriceHistory", back_populates="listing")

class PriceHistory(Base):
    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("listings.id"))
    price = Column(Float)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship with listing
    listing = relationship("Listing", back_populates="price_history") 