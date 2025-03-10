from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import Dict, Optional, List
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
    status: str = "pending"
    error: Optional[str] = None

class ImportStatus(BaseModel):
    task_id: str
    status: str
    location: str
    apartments_imported: int = 0
    error: Optional[str] = None
    completed_at: Optional[str] = None

# In-memory storage for task status (would use a proper database in production)
import threading
task_statuses = {}
task_lock = threading.Lock()

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
    # Validate API key if provided
    if query.api_key and len(query.api_key.strip()) == 0:
        query.api_key = None
        
    # Create a unique task ID
    import uuid
    task_id = str(uuid.uuid4())
    
    # Initialize task status
    with task_lock:
        task_statuses[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "location": query.location,
            "apartments_imported": 0,
            "error": None,
            "completed_at": None
        }
    
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
        "task_id": task_id,
        "status": "pending"
    }

@router.get("/apartments/import/status/{task_id}", response_model=ImportStatus)
async def get_import_status(
    task_id: str,
    db: Session = Depends(get_db)
):
    """
    Get the status of an import task
    
    Args:
        task_id: The ID of the import task
        
    Returns:
        Status information for the task
    """
    with task_lock:
        if task_id not in task_statuses:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Import task with ID {task_id} not found"
            )
        
        return task_statuses[task_id]

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
    from datetime import datetime
    
    logger = logging.getLogger(__name__)
    
    try:
        # Update task status to in progress
        with task_lock:
            if task_id in task_statuses:
                task_statuses[task_id]["status"] = "in_progress"
        
        # Create service and import apartments
        service = GoogleMapsService(db, api_key)
        count, error = await service.import_apartments_to_db(location)
        
        # Update task status based on result
        with task_lock:
            if task_id in task_statuses:
                if error:
                    task_statuses[task_id]["status"] = "failed"
                    task_statuses[task_id]["error"] = error
                    logger.error(f"Task {task_id}: {error}")
                else:
                    task_statuses[task_id]["status"] = "completed"
                    task_statuses[task_id]["apartments_imported"] = count
                    logger.info(f"Task {task_id}: Successfully imported {count} apartments for location {location}")
                
                task_statuses[task_id]["completed_at"] = datetime.now().isoformat()
                
    except Exception as e:
        # Update task status to failed
        error_msg = f"Error importing apartments for location {location}: {str(e)}"
        logger.error(f"Task {task_id}: {error_msg}")
        
        with task_lock:
            if task_id in task_statuses:
                task_statuses[task_id]["status"] = "failed"
                task_statuses[task_id]["error"] = error_msg
                task_statuses[task_id]["completed_at"] = datetime.now().isoformat() 