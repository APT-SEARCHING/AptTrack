from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.services.google_maps import GoogleMapsService

router = APIRouter()

class LocationQuery(BaseModel):
    location: str
    api_key: Optional[str] = None

class ImportResponse(BaseModel):
    message: str
    location: str
    task_id: Optional[str] = None

@router.post("/apartments/import/google-maps", response_model=ImportResponse)
async def import_apartments_from_google_maps(
    query: LocationQuery,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Import apartments from Google Maps API based on location (city or zipcode)
    
    This endpoint will trigger a background task to fetch apartment data from Google Maps
    and import it into the database.
    
    Args:
        query: Location query parameters
        background_tasks: FastAPI background tasks
        db: Database session
        
    Returns:
        Response with task information
    """
    # Create a unique task ID
    import uuid
    task_id = str(uuid.uuid4())
    
    # Add the import task to background tasks
    background_tasks.add_task(
        _import_apartments_background_task,
        location=query.location,
        api_key=query.api_key,
        db=db,
        task_id=task_id
    )
    
    return {
        "message": f"Import task started for location: {query.location}",
        "location": query.location,
        "task_id": task_id
    }

async def _import_apartments_background_task(
    location: str,
    api_key: Optional[str],
    db: Session,
    task_id: str
):
    """
    Background task to import apartments from Google Maps
    
    Args:
        location: City name or zipcode
        api_key: Optional Google Maps API key
        db: Database session
        task_id: Unique task ID
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        service = GoogleMapsService(db, api_key)
        count = await service.import_apartments_to_db(location)
        logger.info(f"Task {task_id}: Successfully imported {count} apartments for location {location}")
    except Exception as e:
        logger.error(f"Task {task_id}: Error importing apartments for location {location}: {str(e)}")
        # Don't raise the exception as this is a background task 