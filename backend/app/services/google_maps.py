import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp

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

            # Use multiple search queries to get more comprehensive results
            search_queries = [
                "apartment",
                "apartment complex",
                "apartments for rent",
                "residential complex",
                "housing complex",
                "rental apartments",
                "apartment homes",
                "luxury apartments",
                "affordable housing",
                "student housing",
                "senior housing",
                "condos for rent",
                "rental properties",
                "multifamily housing",
                "garden apartments"
            ]

            all_places = {}  # Use dict to avoid duplicates based on place_id

            for query in search_queries:
                places, error = await self._search_places(location, query)
                if error:
                    logger.warning(f"Error searching for '{query}' in {location}: {error}")
                    continue

                # Add places to our collection, avoiding duplicates
                new_places = 0
                for place in places:
                    place_id = place.get("place_id")
                    if place_id and place_id not in all_places:
                        all_places[place_id] = place
                        new_places += 1

                logger.info(f"Query '{query}': {len(places)} results, {new_places} new unique places")

            # Also try nearby search if we have geocoding available
            nearby_places, error = await self._nearby_search(location)
            if nearby_places and not error:
                nearby_new = 0
                for place in nearby_places:
                    place_id = place.get("place_id")
                    if place_id and place_id not in all_places:
                        all_places[place_id] = place
                        nearby_new += 1
                logger.info(f"Nearby search: {len(nearby_places)} results, {nearby_new} new unique places")

            if not all_places:
                return {}, f"No apartments found in location: {location}"

            logger.info(f"Found {len(all_places)} unique places across all search queries")

            # Then get details for each place and build hash table
            apartments_hash = {}
            failed_count = 0

            for place in all_places.values():
                details, error = await self._get_place_details(place["place_id"])
                if error:
                    failed_count += 1
                    logger.warning(f"Error getting details for place {place.get('name', 'Unknown')}: {error}")
                    continue

                if details:
                    external_id = details.get("external_id")
                    if external_id:
                        apartments_hash[external_id] = details

            logger.info(f"Successfully retrieved details for {len(apartments_hash)} apartments, {failed_count} failed")

            if not apartments_hash:
                return {}, f"Could not retrieve details for any apartments in {location} (found {len(all_places)} places but all detail fetches failed)"

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
                "maxResultCount": 20  # Google Places API v1 max limit per query
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
                            logger.info(f"Found {len(transformed_places)} places for query '{keyword} in {location}'")
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

    async def _nearby_search(self, location: str) -> Tuple[List[Dict], Optional[str]]:
        """
        Use Nearby Search to find apartments around a location
        This requires geocoding the location first
        """
        try:
            # First geocode the location to get coordinates
            coordinates, error = await self._geocode_location(location)
            if error or not coordinates:
                logger.warning(f"Could not geocode location '{location}' for nearby search: {error}")
                return [], error

            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/places:searchNearby"

                headers = {
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": "places.displayName,places.id,places.types,places.formattedAddress,places.name"
                }

                body = {
                    "includedTypes": ["lodging", "real_estate_agency"],
                    "maxResultCount": 20,
                    "locationRestriction": {
                        "circle": {
                            "center": {
                                "latitude": coordinates["lat"],
                                "longitude": coordinates["lng"]
                            },
                            "radius": 10000.0  # 10km radius
                        }
                    }
                }

                try:
                    async with session.post(url, json=body, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            places = data.get("places", [])

                            if places:
                                transformed_places = []
                                for place in places:
                                    # Filter for apartment-related places
                                    place_types = place.get("types", [])
                                    place_name = place.get("displayName", {}).get("text", "").lower()

                                    if (any(apt_type in str(place_types).lower() for apt_type in ["lodging", "real_estate"]) or
                                        any(keyword in place_name for keyword in ["apartment", "housing", "residence", "complex"])):

                                        transformed_places.append({
                                            "place_id": place.get("id"),
                                            "name": place.get("displayName", {}).get("text", "Unknown"),
                                            "formatted_address": place.get("formattedAddress", ""),
                                            "types": place.get("types", [])
                                        })

                                return transformed_places, None
                            else:
                                return [], None
                        else:
                            logger.warning(f"Nearby search failed with status {response.status}")
                            return [], f"Nearby search failed: Status {response.status}"

                except Exception as e:
                    logger.warning(f"Error in nearby search: {str(e)}")
                    return [], str(e)

        except Exception as e:
            return [], f"Error in nearby search: {str(e)}"

    async def _geocode_location(self, location: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Geocode a location string to get coordinates"""
        try:
            async with aiohttp.ClientSession() as session:
                url = "https://maps.googleapis.com/maps/api/geocode/json"
                params = {
                    "address": location,
                    "key": self.api_key
                }

                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get("results", [])

                        if results:
                            location_data = results[0]["geometry"]["location"]
                            return {"lat": location_data["lat"], "lng": location_data["lng"]}, None
                        else:
                            return None, f"No geocoding results for {location}"
                    else:
                        return None, f"Geocoding failed: Status {response.status}"

        except Exception as e:
            return None, f"Geocoding error: {str(e)}"

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
                        except Exception:
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
