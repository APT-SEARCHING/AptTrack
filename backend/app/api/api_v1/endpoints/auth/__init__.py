from app.api.api_v1.endpoints.auth.core import router as auth_router
from fastapi import APIRouter

router = APIRouter()
router.include_router(auth_router)
