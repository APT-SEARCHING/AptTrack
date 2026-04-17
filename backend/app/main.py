from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.api_v1.api import api_router
from app.api.unsubscribe import router as unsubscribe_router
from app.core.config import settings
from app.core.limiter import limiter  # shared singleton

app = FastAPI(
    title="Rental Price Tracker",
    description="API for tracking apartment rental prices",
    version="1.0.0",
)

# Attach limiter so @limiter.limit() decorators can find it on request.app.state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ---------------------------------------------------------------------------
# CORS — explicit methods/headers instead of wildcard
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(api_router, prefix="/api/v1")
app.include_router(unsubscribe_router)  # /unsubscribe/* — no prefix, returns HTML


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
