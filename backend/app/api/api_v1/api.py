from fastapi import APIRouter
from app.api.api_v1.endpoints import listings

api_router = APIRouter()
api_router.include_router(listings.router, tags=["listings"]) 