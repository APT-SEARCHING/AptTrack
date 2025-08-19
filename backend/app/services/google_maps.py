import aiohttp
import asyncio
import json
from typing import List, Dict, Optional, Union, Tuple
import logging
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.apartment import Apartment, Plan
from datetime import datetime

logger = logging.getLogger(__name__)

class GoogleMapsService:
    """Service for interacting with Google Maps API to fetch apartment data"""
    
    def __init__(self, db: Session, api_key: Optional[str] = None):
        self.db = db
        self.api_key = api_key or settings.GOOGLE_MAPS_API_KEY
        if not self.api_key:
            logger.warning("No Google Maps API key provided. API requests will likely be denied.")
        # Use the newer Places API endpoints
        self.base_url = "https://places.googleapis.com/v1"
    
    async def fetch_apartments_by_location(self, location: str) -> Tuple[List[Dict], Optional[str]]:
        """
        Fetch apartments in a given location (city or zipcode)
        
        Args:
            location: City name or zipcode
            
        Returns:
            Tuple of (list of apartment details, error message if any)
        """
        try:
            if not self.api_key:
                return [], "No Google Maps API key provided. Please provide a valid API key."
                
            # First, use Places API to search for apartments
            places, error = await self._search_places(location, "apartment")
            if error:
                return [], error
            
            if not places:
                return [], f"No apartments found in location: {location}"
                
            # Then get details for each place
            apartments = []
            for place in places:
                details, error = await self._get_place_details(place["place_id"])
                if error:
                    logger.warning(f"Error getting details for place {place.get('name', 'Unknown')}: {error}")
                    continue
                    
                if details:
                    apartments.append(details)
            
            if not apartments:
                return [], f"Could not retrieve details for any apartments in {location}"
                
            return apartments, None
        
        except Exception as e:
            error_msg = f"Error fetching apartments from Google Maps: {str(e)}"
            logger.error(error_msg)
            return [], error_msg
    
    async def _search_places(self, location: str, keyword: str) -> Tuple[List[Dict], Optional[str]]:
        """
        Search for places using Google Places API (New)
        
        Args:
            location: City name or zipcode
            keyword: Type of place to search for (e.g., "apartment")
            
        Returns:
            Tuple of (list of place results with basic info, error message if any)
        """
        async with aiohttp.ClientSession() as session:
            # Use the newer Places API text search
            url = f"{self.base_url}/places:searchText"
            
            # The new API uses POST with JSON body instead of GET with params
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "places.displayName,places.id,places.types,places.formattedAddress,places.name"
            }
            
            body = {
                "textQuery": f"{keyword} in {location}",
                "maxResultCount": 20
            }
            
            try:
                async with session.post(url, json=body, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        places = data.get("places", [])
                        
                        if places:
                            # Transform the new API response format to match our expected format
                            transformed_places = []
                            for place in places:
                                transformed_places.append({
                                    "place_id": place.get("id"),
                                    "name": place.get("displayName", {}).get("text", "Unknown"),
                                    "formatted_address": place.get("formattedAddress", ""),
                                    "types": place.get("types", [])
                                })
                            return transformed_places, None
                        else:
                            return [], f"No {keyword} found in {location}"
                    elif response.status == 401:
                        error_msg = "Google Places API authentication failed. Please check your API key."
                        logger.error(error_msg)
                        return [], error_msg
                    elif response.status == 403:
                        error_msg = "Google Places API access denied. Please check your API key permissions."
                        logger.error(error_msg)
                        return [], error_msg
                    else:
                        error_msg = f"Failed to fetch places: Status {response.status}"
                        logger.error(error_msg)
                        return [], error_msg
            except Exception as e:
                error_msg = f"Error connecting to Google Places API: {str(e)}"
                logger.error(error_msg)
                return [], error_msg
    
    async def _get_place_details(self, place_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get detailed information about a place using its place_id
        
        Args:
            place_id: Google Place ID
            
        Returns:
            Tuple of (dictionary with place details or None if not found, error message if any)
        """
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/places/{place_id}"
            
            # The new API uses GET with headers instead of params
            # Field mask should not include "places." prefix for GET endpoint
            headers = {
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "name,formattedAddress,location,websiteUri,nationalPhoneNumber,rating,userRatingCount,displayName"
            }
            
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Place details response: {data}")
                        # For GET endpoint, the response structure is different
                        place = data if data else {}
                        
                        if place:
                            return self._format_place_details(place), None
                        else:
                            return None, "Place not found"
                    elif response.status == 400:
                        # Try to get more details about the error
                        try:
                            error_data = await response.json()
                            error_msg = f"Google Place Details API bad request: {error_data}"
                        except:
                            error_msg = f"Google Place Details API bad request: Status {response.status}"
                        logger.error(error_msg)
                        return None, error_msg
                    elif response.status == 401:
                        error_msg = "Google Place Details API authentication failed. Please check your API key."
                        logger.error(error_msg)
                        return None, error_msg
                    elif response.status == 403:
                        error_msg = "Google Place Details API access denied. Please check your API key permissions."
                        logger.error(error_msg)
                        return None, error_msg
                    else:
                        error_msg = f"Failed to fetch place details: Status {response.status}"
                        logger.error(error_msg)
                        return None, error_msg
            except Exception as e:
                error_msg = f"Error connecting to Google Place Details API: {str(e)}"
                logger.error(error_msg)
                return None, error_msg

    async def _get_place_details_raw_only(self, place_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Return raw JSON for a place by ID without formatting."""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/places/{place_id}"
            headers = {
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "*"
            }
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data, None
                    else:
                        try:
                            err = await response.json()
                        except Exception:
                            err = {"status": response.status}
                        return None, f"Failed to fetch raw place details: {err}"
            except Exception as e:
                return None, f"Error connecting to Google Place Details API: {e}"
    
    def _format_place_details(self, place: Dict) -> Dict:
        """
        Format place details into a structure suitable for our database
        
        Args:
            place: Raw place details from Google API (New)
            
        Returns:
            Formatted place details
        """
        # Extract location components
        address_parts = place.get("formattedAddress", "").split(",")
        city = ""
        state = ""
        zipcode = ""
        
        if len(address_parts) >= 2:
            # Try to extract city, state, and zipcode from address
            state_zip = address_parts[-2].strip() if len(address_parts) > 1 else ""
            state_zip_parts = state_zip.split()
            
            if len(state_zip_parts) >= 2:
                state = state_zip_parts[0]
                zipcode = state_zip_parts[1]
            
            city = address_parts[-3].strip() if len(address_parts) > 2 else ""
        
        # Get coordinates from the new API format
        location = place.get("location", {})
        latitude = location.get("latitude")
        longitude = location.get("longitude")
        
        # Get business name and website URL
        business_name = place.get("displayName", {}).get("text", "") or place.get("name", "")
        website_url = place.get("websiteUri", "")
        phone_number = place.get("nationalPhoneNumber", "")
        rating = place.get("rating")
        user_rating_count = place.get("userRatingCount")
        
        # Prefer business name for title, fall back to address
        title = business_name if business_name else place.get("formattedAddress", "")
        
        return {
            # Use resource name (e.g., "places/<place_id>") as stable external id in v1 API
            "external_id": f"google_{place.get('name')}",
            "place_resource_name": place.get("name", ""),
            "title": title,
            "business_name": business_name,
            "description": f"Apartment complex located in {city}, {state}",
            "address": place.get("formattedAddress", ""),
            "city": city,
            "state": state,
            "zipcode": zipcode,
            "latitude": latitude,
            "longitude": longitude,
            "property_type": "apartment",
            "source_url": website_url,
            "phone": phone_number,
            "rating": rating,
            "user_rating_count": user_rating_count
        }

    async def save_places_to_new_tables(self, location: str, db_session: Session) -> Tuple[int, Optional[str]]:
        """
        Fetch places and persist into new google-specific tables without touching legacy schemas.
        """
        from app.models.google_place import GooglePlaceRaw, GoogleApartment

        apartments, error = await self.fetch_apartments_by_location(location)
        if error:
            return 0, error

        saved = 0
        for apt in apartments:
            try:
                # Also fetch and upsert raw record using place_resource_name -> place_id
                resource_name = apt.get("place_resource_name") or ""
                place_id = resource_name.split("/")[-1] if resource_name else None
                if place_id:
                    raw_place, raw_err = await self._get_place_details_raw_only(place_id)
                    if raw_place:
                        # Prepare fields for raw table
                        loc = (raw_place or {}).get("location", {})
                        raw_existing = db_session.query(GooglePlaceRaw).filter(GooglePlaceRaw.place_resource_name == resource_name).first()
                        if raw_existing:
                            raw_existing.place_id = place_id
                            raw_existing.display_name = (raw_place.get("displayName", {}) or {}).get("text")
                            raw_existing.formatted_address = raw_place.get("formattedAddress")
                            raw_existing.website_uri = raw_place.get("websiteUri")
                            raw_existing.national_phone_number = raw_place.get("nationalPhoneNumber")
                            raw_existing.rating = raw_place.get("rating")
                            raw_existing.user_rating_count = raw_place.get("userRatingCount")
                            raw_existing.latitude = loc.get("latitude")
                            raw_existing.longitude = loc.get("longitude")
                            raw_existing.raw_json = raw_place
                            db_session.commit()
                        else:
                            db_session.add(GooglePlaceRaw(
                                place_resource_name=resource_name,
                                place_id=place_id,
                                display_name=(raw_place.get("displayName", {}) or {}).get("text"),
                                formatted_address=raw_place.get("formattedAddress"),
                                website_uri=raw_place.get("websiteUri"),
                                national_phone_number=raw_place.get("nationalPhoneNumber"),
                                rating=raw_place.get("rating"),
                                user_rating_count=raw_place.get("userRatingCount"),
                                latitude=loc.get("latitude"),
                                longitude=loc.get("longitude"),
                                raw_json=raw_place,
                            ))
                            db_session.commit()
                    else:
                        logger.warning(f"Raw fetch failed for {resource_name}: {raw_err}")

                # Save normalized record
                existing = db_session.query(GoogleApartment).filter(GoogleApartment.external_id == apt["external_id"]).first()
                if existing:
                    for key, value in apt.items():
                        if hasattr(existing, key) and key not in ["id", "created_at"]:
                            setattr(existing, key, value)
                    db_session.commit()
                else:
                    ga = GoogleApartment(**apt)
                    db_session.add(ga)
                    db_session.commit()
                saved += 1
            except Exception as e:
                db_session.rollback()
                logger.error(f"Failed saving Google apartment {apt.get('title')}: {e}")

        return saved, None
    
    async def import_apartments_to_db(self, location: str, db_session: Optional[Session] = None) -> Tuple[int, Optional[str]]:
        """
        Import apartments from Google Maps API to the database
        
        Args:
            location: City name or zipcode
            db_session: Optional database session to use (if not provided, uses self.db)
            
        Returns:
            Tuple of (number of apartments imported, error message if any)
        """
        apartments, error = await self.fetch_apartments_by_location(location)
        if error:
            return 0, error
            
        if not apartments:
            return 0, f"No apartments found in location: {location}"
            
        # Use provided session or fall back to self.db
        db = db_session or self.db
        imported_count = 0
        
        for apt_data in apartments:
            try:
                # Check if apartment already exists by external_id
                existing_apartment = db.query(Apartment).filter(
                    Apartment.external_id == apt_data["external_id"]
                ).first()
                
                if existing_apartment:
                    # Update existing apartment
                    for key, value in apt_data.items():
                        if key not in ["external_id"] and hasattr(existing_apartment, key):
                            setattr(existing_apartment, key, value)
                    
                    existing_apartment.updated_at = datetime.now()
                    db.commit()
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
                    
                    db.add(new_apartment)
                    db.commit()
                    logger.info(f"Added new apartment: {apt_data['title']}")
                    imported_count += 1
            
            except Exception as e:
                db.rollback()
                logger.error(f"Error importing apartment {apt_data.get('title', 'Unknown')}: {str(e)}")
        
        if imported_count == 0:
            return 0, "No apartments were imported. Check the logs for details."
            
        return imported_count, None


async def test_fetch_apartments_to_json(location: str, output_file: str = "apartments_data.json") -> Tuple[int, Optional[str]]:
    """
    Test function to fetch apartments from Google Maps API and save to JSON file
    
    Args:
        location: City name or zipcode
        output_file: Name of the output JSON file
        
    Returns:
        Tuple of (number of apartments fetched, error message if any)
    """
    try:
        # Create a mock database session (we won't use it)
        class MockDB:
            def __init__(self):
                pass
            def query(self, *args):
                return self
            def filter(self, *args):
                return self
            def first(self):
                return None
            def commit(self):
                pass
            def rollback(self):
                pass
            def add(self, *args):
                pass
            def close(self):
                pass
        
        mock_db = MockDB()
        service = GoogleMapsService(mock_db)
        
        # Fetch apartments without database operations
        apartments, error = await service.fetch_apartments_by_location(location)
        if error:
            return 0, error
            
        if not apartments:
            return 0, f"No apartments found in location: {location}"
        
        # Save to JSON file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(apartments, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Successfully saved {len(apartments)} apartments to {output_file}")
            return len(apartments), None
            
        except Exception as e:
            error_msg = f"Error saving to JSON file: {str(e)}"
            logger.error(error_msg)
            return 0, error_msg
            
    except Exception as e:
        error_msg = f"Error in test function: {str(e)}"
        logger.error(error_msg)
        return 0, error_msg

async def test_import_apartments_to_db(location: str) -> Tuple[int, Optional[str]]:
    """
    Test function to import apartments from Google Maps API to the database
    
    Args:
        location: City name or zipcode
        
    Returns:
        Tuple of (number of apartments imported, error message if any)
    """
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        
        # Create a local database connection (not Docker)
        local_db_url = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/rental_tracker")
        engine = create_engine(local_db_url)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        db = SessionLocal()
        try:
            service = GoogleMapsService(db)
            
            # Import apartments to database using the local session
            count, error = await service.import_apartments_to_db(location, db_session=db)
            if error:
                return 0, error
                
            logger.info(f"Successfully imported {count} apartments to database")
            return count, None
            
        finally:
            db.close()
            
    except Exception as e:
        error_msg = f"Error in database import test: {str(e)}"
        logger.error(error_msg)
        return 0, error_msg

async def main():
    """Test function for the Google Maps service"""
    import os
    
    # Get API key from environment for testing
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Warning: No GOOGLE_MAPS_API_KEY environment variable found.")
        print("Set this variable before running the script.")
        return
    
    # Test fetching apartments and saving to JSON
    print("Testing Google Maps service...")
    print("Fetching apartments from Santa Clara, CA...")
    
    count, error = await test_fetch_apartments_to_json("Santa Clara, CA", "santa_clara_apartments.json")
    
    if error:
        print(f"Error: {error}")
    else:
        print(f"Successfully fetched {count} apartments")
        print("Results saved to 'santa_clara_apartments.json'")
        print("Check the file to see the apartment details.")
    
    # Test importing to database
    print("\nTesting database import...")
    print("Importing apartments to database...")
    
    db_count, db_error = await test_import_apartments_to_db("Santa Clara, CA")
    
    if db_error:
        print(f"Database import error: {db_error}")
    else:
        print(f"Successfully imported {db_count} apartments to database")
        print("Check the database to see the imported data.")

if __name__ == "__main__":
    asyncio.run(main()) 