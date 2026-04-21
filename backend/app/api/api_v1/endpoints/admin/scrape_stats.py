"""GET /admin/scrape-stats — aggregate ScrapeRun data for cost/quality monitoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.session import get_db
from app.models.scrape_run import ScrapeRun

router = APIRouter()


class DomainFailureCount(BaseModel):
    domain: str
    count: int


class ScrapeStatsResponse(BaseModel):
    period_days: int
    total_scrapes: int
    by_outcome: Dict[str, int]
    cache_hit_pct: float
    short_circuit_pct: float
    total_cost_usd: float
    cost_p50_usd: float
    cost_p95_usd: float
    failures_by_domain: List[DomainFailureCount]


@router.get(
    "/admin/scrape-stats",
    response_model=ScrapeStatsResponse,
    tags=["admin"],
    summary="Aggregated scrape metrics for the last N days (admin only)",
)
def get_scrape_stats(
    days: int = Query(default=7, ge=1, le=90, description="Look-back window in days"),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
) -> ScrapeStatsResponse:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    runs = db.execute(
        select(ScrapeRun).where(ScrapeRun.run_at >= since)
    ).scalars().all()

    total = len(runs)
    if total == 0:
        return ScrapeStatsResponse(
            period_days=days,
            total_scrapes=0,
            by_outcome={},
            cache_hit_pct=0.0,
            short_circuit_pct=0.0,
            total_cost_usd=0.0,
            cost_p50_usd=0.0,
            cost_p95_usd=0.0,
            failures_by_domain=[],
        )

    by_outcome: Dict[str, int] = {}
    for r in runs:
        by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1

    cache_hits = by_outcome.get("cache_hit", 0)
    unchanged = by_outcome.get("content_unchanged", 0)

    costs = sorted(r.cost_usd for r in runs if r.cost_usd > 0)
    total_cost = sum(r.cost_usd for r in runs)
    p50 = costs[len(costs) // 2] if costs else 0.0
    p95 = costs[int(len(costs) * 0.95)] if costs else 0.0

    domain_failures: Dict[str, int] = {}
    for r in runs:
        if r.outcome in ("hard_fail", "validated_fail"):
            domain = urlparse(r.url).netloc.lower()
            domain_failures[domain] = domain_failures.get(domain, 0) + 1
    failures_by_domain = [
        DomainFailureCount(domain=d, count=c)
        for d, c in sorted(domain_failures.items(), key=lambda x: -x[1])
    ]

    return ScrapeStatsResponse(
        period_days=days,
        total_scrapes=total,
        by_outcome=by_outcome,
        cache_hit_pct=round(100 * cache_hits / total, 1),
        short_circuit_pct=round(100 * unchanged / total, 1),
        total_cost_usd=round(total_cost, 4),
        cost_p50_usd=round(p50, 5),
        cost_p95_usd=round(p95, 5),
        failures_by_domain=failures_by_domain,
    )
