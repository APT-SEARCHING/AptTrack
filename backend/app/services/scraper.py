from bs4 import BeautifulSoup
import aiohttp
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from app.models.apartment import Apartment, Plan, PlanPriceHistory, PropertyType
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
        # This is a generic parser that should be overridden by specific scrapers
        pass
    
    def save_listing(self, listing_data: Dict):
        """
        Save listing data to the database using the new Apartment model
        """
        try:
            # Check if apartment already exists by external_id
            existing_apartment = self.db.query(Apartment).filter(
                Apartment.external_id == listing_data["external_id"]
            ).first()
            
            # Extract location data
            location_parts = listing_data.get("location", "").split(",")
            city = location_parts[0].strip() if location_parts else ""
            state = "CA"  # Default to California
            zipcode = "00000"  # Default zipcode
            
            # Try to extract zipcode if available
            if len(location_parts) > 1:
                zip_match = re.search(r'\b\d{5}\b', location_parts[-1])
                if zip_match:
                    zipcode = zip_match.group(0)
            
            # Extract or set property type
            property_type = "apartment"
            if "condo" in listing_data.get("title", "").lower():
                property_type = "condo"
            elif "townhouse" in listing_data.get("title", "").lower():
                property_type = "townhouse"
            elif "studio" in listing_data.get("title", "").lower() or listing_data.get("bedrooms", 0) == 0:
                property_type = "studio"
            
            if existing_apartment:
                # Update existing apartment
                existing_apartment.title = listing_data["title"]
                existing_apartment.description = listing_data.get("description", "")
                existing_apartment.updated_at = datetime.now()
                
                # Check if there's an existing plan with these specs
                existing_plan = None
                for plan in existing_apartment.plans:
                    if (plan.bedrooms == listing_data["bedrooms"] and 
                        plan.bathrooms == listing_data["bathrooms"] and
                        plan.area_sqft == listing_data.get("area_sqft", 0)):
                        existing_plan = plan
                        break
                
                # Update or create plan
                if existing_plan:
                    # Check if price has changed
                    current_price = listing_data.get("price")
                    if current_price and current_price != existing_plan.price:
                        existing_plan.price = current_price
                        # Add price history entry
                        price_history = PlanPriceHistory(
                            plan_id=existing_plan.id,
                            price=current_price
                        )
                        self.db.add(price_history)
                else:
                    # Create new plan
                    new_plan = Plan(
                        apartment_id=existing_apartment.id,
                        name=f"Plan {len(existing_apartment.plans) + 1}",
                        bedrooms=listing_data["bedrooms"],
                        bathrooms=listing_data["bathrooms"],
                        area_sqft=listing_data.get("area_sqft", 0),
                        price=listing_data.get("price", 0)
                    )
                    
                    # Add price history
                    if listing_data.get("price"):
                        price_history = PlanPriceHistory(price=listing_data["price"])
                        new_plan.price_history = [price_history]
                    
                    self.db.add(new_plan)
                
                self.db.commit()
                logger.info(f"Updated apartment: {existing_apartment.title}")
            else:
                # Create new apartment
                new_apartment = Apartment(
                    external_id=listing_data["external_id"],
                    title=listing_data["title"],
                    description=listing_data.get("description", ""),
                    city=city,
                    state=state,
                    zipcode=zipcode,
                    property_type=property_type,
                    source_url=listing_data.get("url", "")
                )
                
                self.db.add(new_apartment)
                self.db.flush()  # Get the ID without committing
                
                # Create plan
                new_plan = Plan(
                    apartment_id=new_apartment.id,
                    name="Default Plan",
                    bedrooms=listing_data["bedrooms"],
                    bathrooms=listing_data["bathrooms"],
                    area_sqft=listing_data.get("area_sqft", 0),
                    price=listing_data.get("price", 0)
                )
                
                # Add price history if price is available
                if listing_data.get("price"):
                    price_history = PlanPriceHistory(price=listing_data["price"])
                    new_plan.price_history = [price_history]
                
                self.db.add(new_plan)
                self.db.commit()
                logger.info(f"Added new apartment: {new_apartment.title}")
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error saving listing: {str(e)}")
    
    async def scrape_listings(self, urls: List[str]):
        for url in urls:
            html = await self.fetch_page(url)
            if html:
                listings = await self.parse_listing(html)
                for listing in listings:
                    self.save_listing(listing)

class IrvineApartmentsScraper(RentalScraper):
    def __init__(self, db: Session):
        super().__init__(db)
        self.data = None
        self.base_url = "https://www.irvinecompanyapartments.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    async def fetch_data(self) -> Optional[Dict]:
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/api/v1/apartments"
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.data = data
                        return data
                    logger.error(f"Failed to fetch data: Status {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching data: {str(e)}")
            return None
    
    async def parse_listings(self) -> List[Dict]:
        if not self.data:
            await self.fetch_data()
            if not self.data:
                return []
        
        listings = []
        for item in self.data.get('apartments', []):
            try:
                external_id = item.get('id')
                title = item.get('name', '')
                description = item.get('description', '')
                location = f"{item.get('city', '')}, {item.get('state', '')} {item.get('zip', '')}"
                
                # Parse bedrooms and bathrooms
                bedrooms = float(item.get('bedrooms', 0))
                bathrooms = float(item.get('bathrooms', 0))
                
                # Parse area
                area_sqft = float(item.get('squareFeet', 0))
                
                # Parse price
                price = float(item.get('price', 0))
                
                # Create listing object
                listing = {
                    'external_id': external_id,
                    'title': title,
                    'description': description,
                    'location': location,
                    'bedrooms': bedrooms,
                    'bathrooms': bathrooms,
                    'area_sqft': area_sqft,
                    'price': price,
                    'url': f"{self.base_url}/apartments/{external_id}"
                }
                listings.append(listing)
            except Exception as e:
                logger.error(f"Error parsing listing: {str(e)}")
        
        return listings
    
    async def scrape_listings(self, urls: List[str]) -> None:
        try:
            # For Irvine Apartments, we don't need the URLs, we use the API
            await self.fetch_data()
            listings = await self.parse_listings()
            
            for listing in listings:
                self.save_listing(listing)
            
            logger.info(f"Scraped {len(listings)} listings from Irvine Apartments")
        except Exception as e:
            logger.error(f"Error in scrape_listings: {str(e)}")

async def main():
    # This is for testing purposes
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    try:
        scraper = IrvineApartmentsScraper(db)
        await scraper.scrape_listings([])
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main()) 