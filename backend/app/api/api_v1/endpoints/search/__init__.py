from app.api.api_v1.endpoints.search.core import router as search_router
from fastapi import APIRouter

router = APIRouter()
router.include_router(search_router)
