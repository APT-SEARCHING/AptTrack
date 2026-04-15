from fastapi import APIRouter
from app.api.api_v1.endpoints import (
    apartments,
    neighborhoods,
    statistics,
    search,
)
from app.api.api_v1.endpoints.auth import router as auth_router
from app.api.api_v1.endpoints.subscriptions import router as subscriptions_router

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