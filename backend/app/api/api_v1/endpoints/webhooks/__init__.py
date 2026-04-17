from app.api.api_v1.endpoints.webhooks.sendgrid import router as sendgrid_router
from fastapi import APIRouter

router = APIRouter()
router.include_router(sendgrid_router)
