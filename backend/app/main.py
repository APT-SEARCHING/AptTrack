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

@app.get("/health")
async def health_check():
    return {"status": "healthy"} 