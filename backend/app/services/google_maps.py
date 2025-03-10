import aiohttp
import asyncio
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
        self.base_url = "https://maps.googleapis.com/maps/api"
    
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
        Search for places using Google Places API
        
        Args:
            location: City name or zipcode
            keyword: Type of place to search for (e.g., "apartment")
            
        Returns:
            Tuple of (list of place results with basic info, error message if any)
        """
        async with aiohttp.ClientSession() as session:
            # Construct the URL for the Places API text search
            url = f"{self.base_url}/place/textsearch/json"
            params = {
                "query": f"{keyword} in {location}",
                "key": self.api_key
            }
            
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        status = data.get("status")
                        
                        if status == "OK":
                            return data.get("results", []), None
                        elif status == "ZERO_RESULTS":
                            return [], f"No {keyword} found in {location}"
                        elif status == "REQUEST_DENIED":
                            error_msg = f"Google Places API request denied: {data.get('error_message', 'No API key or invalid API key')}"
                            logger.error(error_msg)
                            return [], error_msg
                        else:
                            error_msg = f"Google Places API error: {status} - {data.get('error_message', '')}"
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
            url = f"{self.base_url}/place/details/json"
            params = {
                "place_id": place_id,
                "fields": "name,formatted_address,geometry,website,url,formatted_phone_number,rating,types",
                "key": self.api_key
            }
            
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        status = data.get("status")
                        
                        if status == "OK":
                            return self._format_place_details(data.get("result", {})), None
                        elif status == "REQUEST_DENIED":
                            error_msg = f"Google Place Details API request denied: {data.get('error_message', 'No API key or invalid API key')}"
                            logger.error(error_msg)
                            return None, error_msg
                        else:
                            error_msg = f"Google Place Details API error: {status} - {data.get('error_message', '')}"
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
    
    def _format_place_details(self, place: Dict) -> Dict:
        """
        Format place details into a structure suitable for our database
        
        Args:
            place: Raw place details from Google API
            
        Returns:
            Formatted place details
        """
        # Extract location components
        address_parts = place.get("formatted_address", "").split(",")
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
        
        # Get coordinates
        location = place.get("geometry", {}).get("location", {})
        latitude = location.get("lat")
        longitude = location.get("lng")
        
        return {
            "external_id": f"google_{place.get('place_id')}",
            "title": place.get("name", ""),
            "description": f"Apartment complex located in {city}, {state}",
            "address": place.get("formatted_address", ""),
            "city": city,
            "state": state,
            "zipcode": zipcode,
            "latitude": latitude,
            "longitude": longitude,
            "property_type": "apartment",
            "source_url": place.get("website") or place.get("url", ""),
            "phone": place.get("formatted_phone_number", ""),
            "rating": place.get("rating")
        }
    
    async def import_apartments_to_db(self, location: str) -> Tuple[int, Optional[str]]:
        """
        Import apartments from Google Maps API to the database
        
        Args:
            location: City name or zipcode
            
        Returns:
            Tuple of (number of apartments imported, error message if any)
        """
        apartments, error = await self.fetch_apartments_by_location(location)
        if error:
            return 0, error
            
        if not apartments:
            return 0, f"No apartments found in location: {location}"
            
        imported_count = 0
        
        for apt_data in apartments:
            try:
                # Check if apartment already exists by external_id
                existing_apartment = self.db.query(Apartment).filter(
                    Apartment.external_id == apt_data["external_id"]
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
                    imported_count += 1
            
            except Exception as e:
                self.db.rollback()
                logger.error(f"Error importing apartment {apt_data.get('title', 'Unknown')}: {str(e)}")
        
        if imported_count == 0:
            return 0, "No apartments were imported. Check the logs for details."
            
        return imported_count, None


async def main():
    """Test function for the Google Maps service"""
    from app.db.session import SessionLocal
    import os
    
    # Get API key from environment for testing
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Warning: No GOOGLE_MAPS_API_KEY environment variable found.")
        print("Set this variable before running the script.")
        return
        
    db = SessionLocal()
    try:
        service = GoogleMapsService(db, api_key)
        count, error = await service.import_apartments_to_db("Santa Clara, CA")
        if error:
            print(f"Error: {error}")
        else:
            print(f"Imported {count} apartments")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main()) 