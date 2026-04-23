from fastapi import APIRouter

from app.api.api_v1.endpoints.admin.negative_cache import router as negative_cache_router
from app.api.api_v1.endpoints.admin.notification_stats import router as notification_stats_router
from app.api.api_v1.endpoints.admin.scrape_stats import router as scrape_stats_router

router = APIRouter()
router.include_router(scrape_stats_router)
router.include_router(notification_stats_router)
router.include_router(negative_cache_router)
