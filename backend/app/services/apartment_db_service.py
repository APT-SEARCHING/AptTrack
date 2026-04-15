"""
Database service for apartment persistence operations
"""
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

# Handle imports for both direct execution and module import
try:
    from app.models.apartment import Apartment, Plan
    from app.models.google_place import GoogleApartment, GooglePlaceRaw
except ImportError:
    from models.apartment import Apartment, Plan
    from models.google_place import GoogleApartment, GooglePlaceRaw

logger = logging.getLogger(__name__)


class ApartmentDatabaseService:
    """Service for database operations related to apartments"""

    def __init__(self, db_session: Session):
        self.db = db_session

    async def save_apartments_to_legacy_schema(self, apartments_hash: Dict[str, Dict]) -> Tuple[int, Optional[str]]:
        """
        Save apartments to the legacy apartment schema

        Args:
            apartments_hash: Hash table of apartment data keyed by external_id

        Returns:
            Tuple of (number of apartments saved, error message if any)
        """
        if not apartments_hash:
            return 0, "No apartments provided to save"

        saved_count = 0

        for external_id, apt_data in apartments_hash.items():
            try:
                # Check if apartment already exists by external_id
                existing_apartment = self.db.query(Apartment).filter(
                    Apartment.external_id == external_id
                ).first()

                if existing_apartment:
                    # Update existing apartment
                    for key, value in apt_data.items():
                        if key not in ["external_id"] and hasattr(existing_apartment, key):
                            setattr(existing_apartment, key, value)

                    existing_apartment.updated_at = datetime.now()
                    self.db.commit()
                    logger.info(f"Updated apartment: {apt_data['title']}")
                else:
                    # Create new apartment
                    # Filter out any keys that aren't in the Apartment model
                    valid_keys = [column.name for column in Apartment.__table__.columns]
                    filtered_data = {k: v for k, v in apt_data.items() if k in valid_keys}

                    new_apartment = Apartment(**filtered_data)

                    # Create a default plan since we don't have specific floor plan data
                    default_plan = Plan(
                        name="Default Plan",
                        bedrooms=1.0,  # Default values since we don't have this info
                        bathrooms=1.0,
                        area_sqft=800.0,
                        price=0.0,  # We don't have price info from Google Maps
                        is_available=True
                    )

                    new_apartment.plans = [default_plan]

                    self.db.add(new_apartment)
                    self.db.commit()
                    logger.info(f"Added new apartment: {apt_data['title']}")
                    saved_count += 1

            except Exception as e:
                self.db.rollback()
                logger.error(f"Error saving apartment {apt_data.get('title', 'Unknown')}: {str(e)}")

        if saved_count == 0:
            return 0, "No apartments were saved. Check the logs for details."

        return saved_count, None

    async def save_apartments_to_google_schema(self, apartments_hash: Dict[str, Dict], raw_places_data: Optional[Dict] = None) -> Tuple[int, Optional[str]]:
        """
        Save apartments to the Google-specific schema tables

        Args:
            apartments_hash: Hash table of apartment data keyed by external_id
            raw_places_data: Optional raw Google Places API data for detailed storage

        Returns:
            Tuple of (number of apartments saved, error message if any)
        """
        if not apartments_hash:
            return 0, "No apartments provided to save"

        saved_count = 0

        for external_id, apt_data in apartments_hash.items():
            try:
                # Save to GoogleApartment table
                existing = self.db.query(GoogleApartment).filter(
                    GoogleApartment.external_id == external_id
                ).first()

                if existing:
                    # Update existing record
                    for key, value in apt_data.items():
                        if hasattr(existing, key) and key not in ["id", "created_at"]:
                            setattr(existing, key, value)
                    self.db.commit()
                    logger.info(f"Updated Google apartment: {apt_data['title']}")
                else:
                    # Create new record
                    ga = GoogleApartment(**apt_data)
                    self.db.add(ga)
                    self.db.commit()
                    logger.info(f"Added new Google apartment: {apt_data['title']}")
                    saved_count += 1

                # Save raw data if provided
                if raw_places_data and external_id in raw_places_data:
                    await self._save_raw_place_data(apt_data, raw_places_data[external_id])

            except Exception as e:
                self.db.rollback()
                logger.error(f"Failed saving Google apartment {apt_data.get('title')}: {e}")

        return saved_count, None

    async def _save_raw_place_data(self, apt_data: Dict, raw_place_data: Dict) -> None:
        """Save raw Google Places API data to GooglePlaceRaw table"""
        try:
            resource_name = apt_data.get("place_resource_name", "")
            place_id = resource_name.split("/")[-1] if resource_name else None

            if not place_id:
                return

            # Check if raw record exists
            existing_raw = self.db.query(GooglePlaceRaw).filter(
                GooglePlaceRaw.place_resource_name == resource_name
            ).first()

            location = raw_place_data.get("location", {})

            if existing_raw:
                # Update existing raw record
                existing_raw.place_id = place_id
                existing_raw.display_name = (raw_place_data.get("displayName", {}) or {}).get("text")
                existing_raw.formatted_address = raw_place_data.get("formattedAddress")
                existing_raw.website_uri = raw_place_data.get("websiteUri")
                existing_raw.national_phone_number = raw_place_data.get("nationalPhoneNumber")
                existing_raw.rating = raw_place_data.get("rating")
                existing_raw.user_rating_count = raw_place_data.get("userRatingCount")
                existing_raw.latitude = location.get("latitude")
                existing_raw.longitude = location.get("longitude")
                existing_raw.raw_json = raw_place_data
                self.db.commit()
            else:
                # Create new raw record
                self.db.add(GooglePlaceRaw(
                    place_resource_name=resource_name,
                    place_id=place_id,
                    display_name=(raw_place_data.get("displayName", {}) or {}).get("text"),
                    formatted_address=raw_place_data.get("formattedAddress"),
                    website_uri=raw_place_data.get("websiteUri"),
                    national_phone_number=raw_place_data.get("nationalPhoneNumber"),
                    rating=raw_place_data.get("rating"),
                    user_rating_count=raw_place_data.get("userRatingCount"),
                    latitude=location.get("latitude"),
                    longitude=location.get("longitude"),
                    raw_json=raw_place_data,
                ))
                self.db.commit()

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving raw place data: {e}")
