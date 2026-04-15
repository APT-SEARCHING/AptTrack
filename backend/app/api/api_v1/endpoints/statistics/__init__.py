from app.api.api_v1.endpoints.statistics.core import router as statistics_router
from fastapi import APIRouter

router = APIRouter()
router.include_router(statistics_router)
