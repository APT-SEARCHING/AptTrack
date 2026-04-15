import threading
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.core.limiter import limiter
from app.models.user import User
from app.services.google_maps import GoogleMapsService

router = APIRouter()


class LocationQuery(BaseModel):
    location: str
    # api_key intentionally omitted — keys must never travel through HTTP bodies.
    # The backend reads GOOGLE_MAPS_API_KEY from server-side environment only.


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


# In-memory task store (single-process only; Celery/Redis for multi-worker setups)
task_statuses: dict = {}
task_lock = threading.Lock()


@router.post("/apartments/import/google-maps", response_model=ImportResponse)
@limiter.limit("3/hour")
async def import_apartments_from_google_maps(
    request: Request,
    query: LocationQuery,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger a Google Maps import for the given location.

    Requires authentication. Only admin users may call this endpoint to
    prevent uncontrolled API spend.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required to trigger Google Maps imports",
        )

    task_id = str(uuid.uuid4())
    with task_lock:
        task_statuses[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "location": query.location,
            "apartments_imported": 0,
            "error": None,
            "completed_at": None,
        }

    background_tasks.add_task(
        _import_background_task,
        location=query.location,
        db=db,
        task_id=task_id,
    )

    return {
        "message": f"Import task started for location: {query.location}",
        "location": query.location,
        "task_id": task_id,
        "status": "pending",
    }


@router.get("/apartments/import/status/{task_id}", response_model=ImportStatus)
@limiter.limit("60/minute")
async def get_import_status(
    request: Request,
    task_id: str,
    db: Session = Depends(get_db),
):
    with task_lock:
        if task_id not in task_statuses:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Import task {task_id!r} not found",
            )
        return task_statuses[task_id]


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def _import_background_task(location: str, db: Session, task_id: str) -> None:
    import logging
    logger = logging.getLogger(__name__)

    try:
        with task_lock:
            task_statuses[task_id]["status"] = "in_progress"

        # API key read exclusively from server-side settings
        service = GoogleMapsService()
        count, error = await service.import_apartments_to_db(location)

        with task_lock:
            if error:
                task_statuses[task_id]["status"] = "failed"
                task_statuses[task_id]["error"] = error
                logger.error("Task %s: %s", task_id, error)
            else:
                task_statuses[task_id]["status"] = "completed"
                task_statuses[task_id]["apartments_imported"] = count
                logger.info("Task %s: imported %d apartments for %r", task_id, count, location)
            task_statuses[task_id]["completed_at"] = datetime.now().isoformat()

    except Exception as exc:
        error_msg = f"Error importing apartments for {location!r}: {exc}"
        logger.error("Task %s: %s", task_id, error_msg)
        with task_lock:
            task_statuses[task_id]["status"] = "failed"
            task_statuses[task_id]["error"] = error_msg
            task_statuses[task_id]["completed_at"] = datetime.now().isoformat()
