from fastapi import APIRouter

from app.api.api_v1.endpoints.statistics.core import router as statistics_router

router = APIRouter()
router.include_router(statistics_router)
