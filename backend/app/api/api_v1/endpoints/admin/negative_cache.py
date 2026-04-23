"""Admin endpoints for the negative-path scrape cache.

GET  /admin/negative-cache       — list all suppressed URLs (most-recently-failed first)
POST /admin/negative-cache/clear — remove one suppression entry
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.negative_scrape_cache import NegativeScrapeCache
from app.services.scraper_agent.negative_cache import clear as _neg_clear

router = APIRouter()


class NegativeCacheEntry(BaseModel):
    url: str
    first_failed_at: datetime
    last_failed_at: datetime
    last_reason: str
    attempt_count: int
    retry_after: datetime
    notes: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ClearRequest(BaseModel):
    url: str


@router.get(
    "/admin/negative-cache",
    response_model=List[NegativeCacheEntry],
    tags=["admin"],
    summary="List all suppressed URLs (admin only)",
)
def list_negative_cache(
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> List[NegativeCacheEntry]:
    rows = db.execute(
        select(NegativeScrapeCache).order_by(NegativeScrapeCache.last_failed_at.desc())
    ).scalars().all()
    return [NegativeCacheEntry.model_validate(r) for r in rows]


@router.post(
    "/admin/negative-cache/clear",
    tags=["admin"],
    summary="Remove a URL from the negative cache (admin only)",
    status_code=200,
)
def clear_negative_cache_entry(
    body: ClearRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    row = db.execute(
        select(NegativeScrapeCache).where(NegativeScrapeCache.url == body.url)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No negative cache entry for {body.url!r}")
    _neg_clear(body.url, db)
    return {"cleared": body.url}
