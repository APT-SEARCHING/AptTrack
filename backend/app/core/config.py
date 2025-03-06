from pydantic import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Rental Price Tracker"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        "postgresql://user:password@localhost:5432/rental_tracker"
    )
    
    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",  # Frontend development server
        "http://localhost:8080",  # Production frontend
    ]
    
    # Scraping
    SCRAPE_INTERVAL_MINUTES: int = 60
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings() 