from bs4 import BeautifulSoup
import aiohttp
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.models.listing import Listing, PriceHistory
from app.core.config import settings
import logging
import json
import re

logger = logging.getLogger(__name__)

class RentalScraper:
    def __init__(self, db: Session):
        self.db = db
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    async def fetch_page(self, url: str) -> Optional[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        return await response.text()
                    logger.error(f"Failed to fetch {url}: Status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {str(e)}")
            return None

    async def parse_listing(self, html: str) -> List[Dict]:
        """
        Parse the HTML content and extract listing information.
        This is a sample implementation - adjust based on target website structure.
        """
        listings = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Example parsing - adjust selectors based on target website
        for item in soup.select('.listing-item'):  # Example selector
            try:
                listing = {
                    'external_id': item.get('data-id', ''),
                    'title': item.select_one('.title').text.strip(),
                    'description': item.select_one('.description').text.strip(),
                    'location': item.select_one('.location').text.strip(),
                    'price': float(item.select_one('.price').text.replace('$', '').replace(',', '')),
                    'bedrooms': int(item.select_one('.beds').text.strip()),
                    'bathrooms': float(item.select_one('.baths').text.strip()),
                    'area_sqft': float(item.select_one('.sqft').text.replace(',', '')),
                }
                listings.append(listing)
            except Exception as e:
                logger.error(f"Error parsing listing: {str(e)}")
                continue
        
        return listings

    def save_listing(self, listing_data: Dict):
        """Save or update listing and its price history"""
        try:
            existing_listing = self.db.query(Listing).filter_by(
                external_id=listing_data['external_id']
            ).first()
            
            if existing_listing:
                # Update existing listing
                for key, value in listing_data.items():
                    if key != 'price':
                        setattr(existing_listing, key, value)
                
                # Add new price point if changed
                latest_price = existing_listing.price_history[-1].price if existing_listing.price_history else None
                if latest_price != listing_data['price']:
                    price_history = PriceHistory(
                        listing_id=existing_listing.id,
                        price=listing_data['price']
                    )
                    self.db.add(price_history)
            else:
                # Create new listing
                new_listing = Listing(
                    **{k: v for k, v in listing_data.items() if k != 'price'}
                )
                self.db.add(new_listing)
                self.db.flush()  # Get the ID of the new listing
                
                # Add initial price history
                price_history = PriceHistory(
                    listing_id=new_listing.id,
                    price=listing_data['price']
                )
                self.db.add(price_history)
            
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving listing: {str(e)}")
            raise

    async def scrape_listings(self, urls: List[str]):
        """Scrape multiple URLs for listings"""
        for url in urls:
            html = await self.fetch_page(url)
            if html:
                listings = await self.parse_listing(html)
                for listing_data in listings:
                    self.save_listing(listing_data)

class IrvineApartmentsScraper:
    def __init__(self, db: Session):
        self.db = db
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        self.base_url = "https://www.irvinecompanyapartments.com/locations/northern-california/santa-clara/santa-clara-square/availability.html"
        
    async def fetch_data(self) -> Optional[Dict]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, headers=self.headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        # Extract the JSON data from the script tag
                        soup = BeautifulSoup(html, 'html.parser')
                        script_tag = soup.find('script', string=re.compile('window.availabilityData'))
                        if script_tag:
                            json_str = re.search(r'window\.availabilityData\s*=\s*({.*?});', script_tag.string, re.DOTALL)
                            if json_str:
                                return json.loads(json_str.group(1))
                    return None
        except Exception as e:
            print(f"Error fetching data: {str(e)}")
            return None

    async def parse_listings(self) -> List[Dict]:
        data = await self.fetch_data()
        if not data:
            return []

        listings = []
        try:
            for unit_type in data.get('floorPlans', []):
                base_info = {
                    'floor_plan_name': unit_type.get('name'),
                    'bedrooms': unit_type.get('beds'),
                    'bathrooms': unit_type.get('baths'),
                    'sq_ft': unit_type.get('sqft'),
                }

                for unit in unit_type.get('units', []):
                    listing = {
                        **base_info,
                        'unit_number': unit.get('unitNumber'),
                        'price': unit.get('price'),
                        'available_date': unit.get('availableDate'),
                        'floor': unit.get('floor'),
                        'building': unit.get('building')
                    }
                    listings.append(listing)

        except Exception as e:
            print(f"Error parsing listings: {str(e)}")

        return listings

    async def scrape_listings(self, urls: List[str]) -> None:
        """Scrape listings and save to database"""
        try:
            listings = await self.parse_listings()
            for listing_data in listings:
                # Convert the data to our model format
                listing = {
                    'external_id': f"irvine-{listing_data['unit_number']}",
                    'title': f"{listing_data['floor_plan_name']} - Unit {listing_data['unit_number']}",
                    'description': f"Floor {listing_data['floor']} in Building {listing_data['building']}",
                    'location': 'Santa Clara Square',
                    'bedrooms': listing_data['bedrooms'],
                    'bathrooms': listing_data['bathrooms'],
                    'area_sqft': listing_data['sq_ft'],
                }
                
                # Check if listing exists
                existing = self.db.query(Listing).filter_by(external_id=listing['external_id']).first()
                
                if existing:
                    # Update existing listing
                    for key, value in listing.items():
                        setattr(existing, key, value)
                    
                    # Add new price point if changed
                    latest_price = existing.price_history[-1].price if existing.price_history else None
                    if latest_price != listing_data['price']:
                        price_history = PriceHistory(
                            listing_id=existing.id,
                            price=listing_data['price']
                        )
                        self.db.add(price_history)
                else:
                    # Create new listing
                    new_listing = Listing(**listing)
                    self.db.add(new_listing)
                    self.db.flush()  # Get the ID
                    
                    # Add initial price history
                    price_history = PriceHistory(
                        listing_id=new_listing.id,
                        price=listing_data['price']
                    )
                    self.db.add(price_history)
                
                self.db.commit()
                
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving listings: {str(e)}")
            raise

async def main():
    scraper = IrvineApartmentsScraper()
    listings = await scraper.parse_listings()
    
    # Print results in a formatted way
    for listing in listings:
        print("\n=== Apartment Listing ===")
        for key, value in listing.items():
            print(f"{key}: {value}")

if __name__ == "__main__":
    asyncio.run(main()) 