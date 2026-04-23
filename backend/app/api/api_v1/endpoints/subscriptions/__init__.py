from fastapi import APIRouter

from app.api.api_v1.endpoints.subscriptions.core import router as subs_router

router = APIRouter()
router.include_router(subs_router)
