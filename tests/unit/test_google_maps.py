#!/usr/bin/env python3
"""
Test script for Google Maps service with real API calls
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the top-level .env file
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

# Add the app directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend" / "app"))

from app.services.google_maps import GoogleMapsService
from app.db.session import SessionLocal

async def test_google_maps_service():
	"""Test the Google Maps service with real API calls"""
	print("Testing Google Maps Service with Real API Calls...")
	
	# Get API key from environment
	api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
	if not api_key:
		print("❌ No GOOGLE_MAPS_API_KEY environment variable found.")
		print("Please set this variable before running the test.")
		return False
	
	print(f"✅ Found API key: {api_key[:10]}...")
	
	# Create database session
	db = SessionLocal()
	try:
		print("🔌 Connecting to database...")
		
		# Test basic service initialization
		service = GoogleMapsService(db, api_key)
		print("✅ Service initialized successfully")
		print(f"✅ Using API endpoint: {service.base_url}")
		
		# Test fetching apartments from a location
		print("\n🔍 Testing apartment search...")
		location = "Santa Clara, CA"
		print(f"Searching for apartments in: {location}")
		
		apartments, error = await service.fetch_apartments_by_location(location)
		
		if error:
			print(f"❌ Error fetching apartments: {error}")
			return False
		
		if not apartments:
			print("⚠️  No apartments found")
			return False
		
		print(f"✅ Found {len(apartments)} apartments!")
		
		# Show first apartment details
		if apartments:
			first_apt = apartments[0]
			print(f"\n📋 First apartment details:")
			print(f"   Name: {first_apt.get('title', 'N/A')}")
			print(f"   Address: {first_apt.get('address', 'N/A')}")
			print(f"   City: {first_apt.get('city', 'N/A')}")
			print(f"   State: {first_apt.get('state', 'N/A')}")
			print(f"   Phone: {first_apt.get('phone', 'N/A')}")
			print(f"   Website: {first_apt.get('source_url', 'N/A')}")
			print(f"   Rating: {first_apt.get('rating', 'N/A')}")
			print(f"   Coordinates: ({first_apt.get('latitude', 'N/A')}, {first_apt.get('longitude', 'N/A')})")
		
		# Test importing to database
		print("\n💾 Testing database import...")
		imported_count, import_error = await service.import_apartments_to_db(location)
		
		if import_error:
			print(f"❌ Error importing to database: {import_error}")
			return False
		
		print(f"✅ Successfully imported {imported_count} apartments to database!")
		
		return True
		
	except Exception as e:
		print(f"❌ Unexpected error: {str(e)}")
		import traceback
		traceback.print_exc()
		return False
	finally:
		db.close()

async def main():
	"""Main test function"""
	print("🚀 Starting Google Maps Service API Test")
	print("=" * 50)
	
	success = await test_google_maps_service()
	
	print("\n" + "=" * 50)
	if success:
		print("🎉 All tests passed!")
	else:
		print("💥 Some tests failed!")
	
	return success

if __name__ == "__main__":
	asyncio.run(main())
