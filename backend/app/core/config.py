from pydantic import BaseSettings
from typing import List
import os
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "Rental Price Tracker"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    DATABASE_HOST: str = os.getenv("DATABASE_HOST", "db")
    DATABASE_PORT: str = os.getenv("DATABASE_PORT", "5432")
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "rental_tracker")
    DATABASE_USER: str = os.getenv("DATABASE_USER", "user")
    DATABASE_PASSWORD: str = os.getenv("DATABASE_PASSWORD", "password")
    
    # Backend
    BACKEND_HOST: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))
    BACKEND_RELOAD: bool = os.getenv("BACKEND_RELOAD", "true").lower() == "true"
    
    # CORS
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")
    
    # Scraping
    SCRAPE_INTERVAL_MINUTES: int = int(os.getenv("SCRAPE_INTERVAL_MINUTES", "60"))
    
    # Google Maps API
    GOOGLE_MAPS_API_KEY: str = os.getenv("GOOGLE_MAPS_API_KEY", "")
    
    # API
    API_BASE_URL: str = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
    API_VERSION: str = os.getenv("API_VERSION", "v1")
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        case_sensitive = True
        # Use the top-level .env file
        env_file = str(Path(__file__).parent.parent.parent / ".env")

settings = Settings() 