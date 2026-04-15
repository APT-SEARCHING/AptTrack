from pydantic import BaseSettings, validator
from pathlib import Path

class Settings(BaseSettings):
    PROJECT_NAME: str = "Rental Price Tracker"
    API_V1_STR: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = ""
    DATABASE_HOST: str = "db"
    DATABASE_PORT: str = "5432"
    DATABASE_NAME: str = "rental_tracker"
    DATABASE_USER: str = "user"
    DATABASE_PASSWORD: str = "password"
    
    # Backend
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_RELOAD: bool = True
    
    # CORS - handle as string and split manually
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080"
    
    # Scraping
    SCRAPE_INTERVAL_MINUTES: int = 60
    
    # Google Maps API
    GOOGLE_MAPS_API_KEY: str = ""

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Redis / Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # Notification services
    SENDGRID_API_KEY: str = ""
    SENDGRID_FROM_EMAIL: str = "noreply@apttrack.app"
    TELEGRAM_BOT_TOKEN: str = ""

    # API
    API_BASE_URL: str = "http://localhost:8000/api/v1"
    API_VERSION: str = "v1"

    # Logging
    LOG_LEVEL: str = "INFO"
    
    @validator('CORS_ORIGINS')
    def parse_cors_origins(cls, v):
        """Convert comma-separated string to list"""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v
    
    @validator('BACKEND_PORT', pre=True)
    def parse_backend_port(cls, v):
        """Convert string to int"""
        return int(v) if isinstance(v, str) else v
    
    @validator('BACKEND_RELOAD', pre=True)
    def parse_backend_reload(cls, v):
        """Convert string to bool"""
        if isinstance(v, str):
            return v.lower() == "true"
        return v
    
    @validator('SCRAPE_INTERVAL_MINUTES', pre=True)
    def parse_scrape_interval(cls, v):
        """Convert string to int"""
        return int(v) if isinstance(v, str) else v
    
    class Config:
        case_sensitive = True
        # Use the top-level .env file
        env_file = str(Path(__file__).parent.parent.parent / ".env")

settings = Settings() 