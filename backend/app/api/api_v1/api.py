from fastapi import APIRouter
from app.api.api_v1.endpoints import (
    apartments,
    neighborhoods,
    statistics,
    search
)

api_router = APIRouter()

# Register all routers
api_router.include_router(apartments.router, tags=["apartments"])
api_router.include_router(neighborhoods.router, tags=["neighborhoods"])
api_router.include_router(statistics.router, tags=["statistics"])
api_router.include_router(search.router, tags=["search"]) 