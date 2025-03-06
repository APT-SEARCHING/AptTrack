from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.api_v1.api import api_router
from fastapi_utils.tasks import repeat_every
from app.db.session import get_db
from app.services.scraper import IrvineApartmentsScraper
from sqlalchemy.orm import Session

app = FastAPI(
    title="Rental Price Tracker",
    description="API for tracking apartment rental prices",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

@app.on_event("startup")
@repeat_every(seconds=settings.SCRAPE_INTERVAL_MINUTES * 60)  # Convert minutes to seconds
async def scrape_listings_task() -> None:
    """Periodic task to scrape rental listings"""
    try:
        db = next(get_db())  # Get database session
        scraper = IrvineApartmentsScraper(db)
        await scraper.scrape_listings([
            "https://www.irvinecompanyapartments.com/locations/northern-california/santa-clara/santa-clara-square/availability.html"
        ])
    except Exception as e:
        print(f"Error in scheduled scraping task: {str(e)}")
    finally:
        db.close()

@app.get("/health")
async def health_check():
    return {"status": "healthy"} 