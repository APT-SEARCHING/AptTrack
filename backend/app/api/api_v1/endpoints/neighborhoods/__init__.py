from fastapi import APIRouter

from app.api.api_v1.endpoints.neighborhoods.core import router as neighborhoods_router

router = APIRouter()
router.include_router(neighborhoods_router) 