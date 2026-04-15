from app.api.api_v1.endpoints.subscriptions.core import router as subs_router
from fastapi import APIRouter

router = APIRouter()
router.include_router(subs_router)
