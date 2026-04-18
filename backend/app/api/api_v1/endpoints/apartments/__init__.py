from app.api.api_v1.endpoints.apartments.core import router as core_router
from app.api.api_v1.endpoints.apartments.images import router as images_router
from app.api.api_v1.endpoints.apartments.import_api import router as import_router
from app.api.api_v1.endpoints.apartments.plans import router as plans_router
from app.api.api_v1.endpoints.apartments.similar import router as similar_router
from fastapi import APIRouter

router = APIRouter()
router.include_router(core_router)
router.include_router(images_router)
router.include_router(plans_router)
router.include_router(import_router)
router.include_router(similar_router)
