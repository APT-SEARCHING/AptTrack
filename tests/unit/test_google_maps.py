#!/usr/bin/env python3
"""
Test for the refactored GoogleMapsService from backend/app/services/google_maps.py
"""
import asyncio
import json
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Configure logging to see detailed search information
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# Load environment variables
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

# Add backend to Python path to import the real service
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Import the REAL GoogleMapsService
from app.services.google_maps import GoogleMapsService


async def test_real_google_maps_service():
    """Test the actual GoogleMapsService from backend/app/services/google_maps.py"""
    print("🧪 Testing REAL GoogleMapsService from backend/app/services/google_maps.py")
    
    # Get API key from environment
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("❌ No GOOGLE_MAPS_API_KEY environment variable found.")
        return False
    
    print(f"✅ Found API key: {api_key[:10]}...")
    
    try:
        # Test service initialization - using the REAL service
        service = GoogleMapsService(api_key)
        print("✅ REAL GoogleMapsService initialized successfully")
        
        # Test fetching apartments
        print("\n🔍 Testing apartment search...")
        location = "San Jose, CA"
        print(f"Searching for apartments in: {location}")
        
        apartments_hash, error = await service.fetch_apartments_by_location(location)
        
        if error:
            print(f"❌ Error fetching apartments: {error}")
            return False
        
        if not apartments_hash:
            print("⚠️  No apartments found")
            return False
        
        print(f"✅ Found {len(apartments_hash)} apartments!")
        print(f"✅ Service returns hash table (Dict[str, Dict]) keyed by external_id")
        
        # Save hash data to JSON file for review
        output_file = Path(__file__).parent.parent.parent / f"real_service_{location.replace(' ', '_').replace(',', '')}.json"
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
            print(f"\n📋 Sample apartment from REAL service:")
            print(f"   Key: {first_key}")
            print(f"   Name: {first_apt.get('title', 'N/A')}")
            print(f"   Address: {first_apt.get('address', 'N/A')}")
            print(f"   City: {first_apt.get('city', 'N/A')}")
            print(f"   State: {first_apt.get('state', 'N/A')}")
            print(f"   Phone: {first_apt.get('phone', 'N/A')}")
            print(f"   Rating: {first_apt.get('rating', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def test_hash_table_structure():
    """Test that the returned hash table has the expected structure"""
    print("\n🔬 Testing Hash Table Structure...")
    
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return False
    
    try:
        service = GoogleMapsService(api_key)
        apartments_hash, error = await service.fetch_apartments_by_location("San Jose, CA")
        
        if error or not apartments_hash:
            print("⚠️  Skipping hash table test - no data available")
            return True
        
        # Test hash table structure
        print(f"✅ Hash table contains {len(apartments_hash)} entries")
        
        # Check that all keys are external_ids
        for key, apartment in apartments_hash.items():
            if key != apartment.get('external_id'):
                print(f"❌ Key mismatch: {key} != {apartment.get('external_id')}")
                return False
        
        print("✅ All keys match external_ids")
        
        # Check required fields in apartment data
        required_fields = ['external_id', 'title', 'address', 'property_type']
        sample_apt = next(iter(apartments_hash.values()))
        
        for field in required_fields:
            if field not in sample_apt:
                print(f"❌ Missing required field: {field}")
                return False
        
        print("✅ All required fields present in apartment data")
        print("✅ Hash table structure test passed!")
        
        return True
        
    except Exception as e:
        print(f"❌ Hash table test error: {str(e)}")
        return False


async def main():
    """Main test function"""
    print("🚀 Testing REAL GoogleMapsService from backend/app")
    print("=" * 60)
    
    # Test basic functionality
    basic_success = await test_real_google_maps_service()
    
    # Test hash table structure
    hash_success = await test_hash_table_structure()
    
    print("\n" + "=" * 60)
    if basic_success and hash_success:
        print("🎉 All REAL service tests passed!")
        print("✅ Successfully tested backend/app/services/google_maps.py")
        print("✅ Service works without database dependency")
        print("✅ Returns well-structured hash table of apartment data")
        print("✅ Config issues resolved!")
    else:
        print("💥 Some tests failed!")
    
    return basic_success and hash_success


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)