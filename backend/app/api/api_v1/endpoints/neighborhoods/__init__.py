from app.api.api_v1.endpoints.neighborhoods.core import router as neighborhoods_router
from fastapi import APIRouter

router = APIRouter()
router.include_router(neighborhoods_router)
