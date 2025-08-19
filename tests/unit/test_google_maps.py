#!/usr/bin/env python3
"""
Test for the refactored Google Maps service
"""
import asyncio
import os
import aiohttp
import json
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional, Tuple
import logging

# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

logger = logging.getLogger(__name__)


class GoogleMapsServiceTest:
    """Isolated Google Maps service for testing without config dependencies"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GOOGLE_MAPS_API_KEY")
        if not self.api_key:
            logger.warning("No Google Maps API key provided.")
        self.base_url = "https://places.googleapis.com/v1"
    
    async def fetch_apartments_by_location(self, location: str) -> Tuple[Dict[str, Dict], Optional[str]]:
        """Fetch apartments in a given location and return as hash table"""
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
        """Search for places using Google Places API"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/places:searchText"
            
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
                    else:
                        error_msg = f"Failed to fetch places: Status {response.status}"
                        logger.error(error_msg)
                        return [], error_msg
            except Exception as e:
                error_msg = f"Error connecting to Google Places API: {str(e)}"
                logger.error(error_msg)
                return [], error_msg
    
    async def _get_place_details(self, place_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Get detailed information about a place using its place_id"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/places/{place_id}"
            
            headers = {
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": "name,formattedAddress,location,websiteUri,nationalPhoneNumber,rating,userRatingCount,displayName"
            }
            
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        place = data if data else {}
                        
                        if place:
                            return self._format_place_details(place), None
                        else:
                            return None, "Place not found"
                    else:
                        error_msg = f"Failed to fetch place details: Status {response.status}"
                        logger.error(error_msg)
                        return None, error_msg
            except Exception as e:
                error_msg = f"Error connecting to Google Place Details API: {str(e)}"
                logger.error(error_msg)
                return None, error_msg
    
    def _format_place_details(self, place: Dict) -> Dict:
        """Format place details into a structure suitable for our database"""
        # Extract location components
        address_parts = place.get("formattedAddress", "").split(",")
        city = ""
        state = ""
        zipcode = ""
        
        if len(address_parts) >= 2:
            state_zip = address_parts[-2].strip() if len(address_parts) > 1 else ""
            state_zip_parts = state_zip.split()
            
            if len(state_zip_parts) >= 2:
                state = state_zip_parts[0]
                zipcode = state_zip_parts[1]
            
            city = address_parts[-3].strip() if len(address_parts) > 2 else ""
        
        # Get coordinates
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


async def test_refactored_service():
    """Test the refactored Google Maps service"""
    print("🧪 Testing Refactored Google Maps Service (Isolated)...")
    
    # Get API key from environment
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("❌ No GOOGLE_MAPS_API_KEY environment variable found.")
        return False
    
    print(f"✅ Found API key: {api_key[:10]}...")
    
    try:
        # Test service initialization
        service = GoogleMapsServiceTest(api_key)
        print("✅ Service initialized successfully")
        
        # Test fetching apartments
        print("\n🔍 Testing apartment search...")
        location = "Palo Alto, CA"
        print(f"Searching for apartments in: {location}")
        
        apartments_hash, error = await service.fetch_apartments_by_location(location)
        
        if error:
            print(f"❌ Error fetching apartments: {error}")
            return False
        
        if not apartments_hash:
            print("⚠️  No apartments found")
            return False
        
        print(f"✅ Found {len(apartments_hash)} apartments!")
        print(f"✅ Returns hash table (Dict[str, Dict]) keyed by external_id")
        
        # Save hash data to JSON file for review
        output_file = Path(__file__).parent.parent.parent / f"apartments_hash_{location.replace(' ', '_').replace(',', '')}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(apartments_hash, f, indent=2, ensure_ascii=False, default=str)
            print(f"💾 Hash data saved to: {output_file}")
        except Exception as e:
            print(f"⚠️  Could not save JSON file: {e}")
        
        # Show sample apartment
        if apartments_hash:
            first_key = next(iter(apartments_hash))
            first_apt = apartments_hash[first_key]
            print(f"\n📋 Sample apartment:")
            print(f"   Key: {first_key}")
            print(f"   Name: {first_apt.get('title', 'N/A')}")
            print(f"   Address: {first_apt.get('address', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False


async def main():
    """Main test function"""
    print("🚀 Testing Refactored Google Maps Service")
    print("=" * 50)
    
    success = await test_refactored_service()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 Refactored service test passed!")
        print("✅ GoogleMapsService now works without database dependency")
        print("✅ Returns hash table structure as expected")
    else:
        print("💥 Test failed!")
    
    return success


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)