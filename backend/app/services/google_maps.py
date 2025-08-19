import aiohttp
import asyncio
import json
import os
import sys
from typing import List, Dict, Optional, Tuple
import logging
from pathlib import Path

# Handle imports for both direct execution and module import
try:
    from app.core.config import settings
except ImportError:
    # Add the backend/app directory to Python path for direct execution
    backend_app_path = Path(__file__).parent.parent
    sys.path.insert(0, str(backend_app_path))
    from core.config import settings

logger = logging.getLogger(__name__)

class GoogleMapsService:
    """Service for interacting with Google Maps API to fetch apartment data"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GOOGLE_MAPS_API_KEY
        if not self.api_key:
            logger.warning("No Google Maps API key provided. API requests will likely be denied.")
        # Use the newer Places API endpoints
        self.base_url = "https://places.googleapis.com/v1"
    
    async def fetch_apartments_by_location(self, location: str) -> Tuple[Dict[str, Dict], Optional[str]]:
        """
        Fetch apartments in a given location (city or zipcode)
        
        Args:
            location: City name or zipcode
            
        Returns:
            Tuple of (hash table with apartment details keyed by external_id, error message if any)
        """
        try:
            if not self.api_key:
                return {}, "No Google Maps API key provided. Please provide a valid API key."
                
            # First, use Places API to search for apartments
            places, error = await self._search_places(location, "apartment")
            if error:
                return {}, error
            
            if not places:
                return {}, f"No apartments found in location: {location}"
                
            # Then get details for each place and build hash table
            apartments_hash = {}
            for place in places:
                details, error = await self._get_place_details(place["place_id"])
                if error:
                    logger.warning(f"Error getting details for place {place.get('name', 'Unknown')}: {error}")
                    continue
                    
                if details:
                    external_id = details.get("external_id")
                    if external_id:
                        apartments_hash[external_id] = details
            
            if not apartments_hash:
                return {}, f"Could not retrieve details for any apartments in {location}"
                
            return apartments_hash, None
        
        except Exception as e:
            error_msg = f"Error fetching apartments from Google Maps: {str(e)}"
            logger.error(error_msg)
            return {}, error_msg
    
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
        # Create service without database dependency
        service = GoogleMapsService()
        
        # Fetch apartments without database operations
        apartments_hash, error = await service.fetch_apartments_by_location(location)
        if error:
            return 0, error
            
        if not apartments_hash:
            return 0, f"No apartments found in location: {location}"
        
        # Save to JSON file
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(apartments_hash, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"Successfully saved {len(apartments_hash)} apartments to {output_file}")
            return len(apartments_hash), None
            
        except Exception as e:
            error_msg = f"Error saving to JSON file: {str(e)}"
            logger.error(error_msg)
            return 0, error_msg
            
    except Exception as e:
        error_msg = f"Error in test function: {str(e)}"
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
        print("Note: Database operations have been separated into a different service.")

if __name__ == "__main__":
    asyncio.run(main()) 