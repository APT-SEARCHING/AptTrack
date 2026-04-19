import threading
import uuid
from datetime import datetime
from typing import Optional

from app.core.limiter import limiter
from app.core.security import require_admin
from app.db.session import get_db
from app.models.user import User
from app.services.google_maps import GoogleMapsService
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

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
    _: User = Depends(require_admin),
):
    """Trigger a Google Maps import for the given location.

    Requires admin access to prevent uncontrolled Google Maps API spend.
    """

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

        # Pre-load cached Place Details from GooglePlaceRaw — avoids re-paying
        # for Place Details ($7/1K Pro) on places already fetched in a prior import.
        from sqlalchemy import select as sa_select
        from app.models.google_place import GooglePlaceRaw
        cached_details: dict = {}
        for row in db.execute(sa_select(GooglePlaceRaw)).scalars().all():
            if row.place_id and row.raw_json:
                cached_details[row.place_id] = row.raw_json
        logger.info("Loaded %d cached place(s) from GooglePlaceRaw", len(cached_details))

        # API key read exclusively from server-side settings
        service = GoogleMapsService()
        apartments_hash, error = await service.fetch_apartments_by_location(
            location, cached_details=cached_details, db=db
        )
        if error:
            raise RuntimeError(error)

        from app.services.apartment_db_service import ApartmentDatabaseService
        db_service = ApartmentDatabaseService(db)
        count, error = await db_service.save_apartments_to_legacy_schema(apartments_hash)

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
