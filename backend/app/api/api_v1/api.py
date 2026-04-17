from app.api.api_v1.endpoints import (
    apartments,
    neighborhoods,
    search,
    statistics,
)
from app.api.api_v1.endpoints.admin import router as admin_router
from app.api.api_v1.endpoints.auth import router as auth_router
from app.api.api_v1.endpoints.favorites import router as favorites_router
from app.api.api_v1.endpoints.subscriptions import router as subscriptions_router
from app.api.api_v1.endpoints.webhooks import router as webhooks_router
from fastapi import APIRouter

api_router = APIRouter()

# Public endpoints
api_router.include_router(auth_router)

# Resource endpoints
api_router.include_router(apartments.router, tags=["apartments"])
api_router.include_router(neighborhoods.router, tags=["neighborhoods"])
api_router.include_router(statistics.router, tags=["statistics"])
api_router.include_router(search.router, tags=["search"])

# Authenticated endpoints
api_router.include_router(subscriptions_router)
api_router.include_router(favorites_router)

# Admin endpoints
api_router.include_router(admin_router)

# Webhook receivers (public, signature-verified)
api_router.include_router(webhooks_router)
