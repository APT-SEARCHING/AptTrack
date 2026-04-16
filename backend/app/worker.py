"""Celery application and beat schedule.

Workers:
  celery -A app.worker worker --loglevel=info

Beat scheduler:
  celery -A app.worker beat --loglevel=info
"""

import asyncio
import logging
from typing import Optional

from celery import Celery, signals
from celery.schedules import crontab

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful shutdown — terminate any in-flight Playwright browser on SIGTERM
# ---------------------------------------------------------------------------

_current_scrape_loop: Optional[asyncio.AbstractEventLoop] = None


@signals.worker_shutting_down.connect
def _on_worker_shutdown(sig, how, exitcode, **kwargs):
    """Cancel all running async tasks so Playwright browsers are closed cleanly."""
    loop = _current_scrape_loop
    if loop is None or not loop.is_running():
        return
    logger.info("Worker shutting down — cancelling in-flight scrape tasks")
    for task in asyncio.all_tasks(loop):
        task.cancel()

celery_app = Celery(
    "apttrack",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Los_Angeles",
    enable_utc=True,
    beat_schedule={
        "check-price-drops": {
            "task": "app.worker.task_check_price_drops",
            "schedule": crontab(hour=8, minute=0),  # 08:00 PT daily
        },
        "refresh-apartment-data": {
            "task": "app.worker.task_refresh_apartment_data",
            "schedule": crontab(hour=2, minute=0),  # 02:00 PT daily
        },
    },
)


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="app.worker.task_check_price_drops", bind=True, max_retries=3)
def task_check_price_drops(self):
    """Check all active price-drop subscriptions and send alerts."""
    from app.db.session import SessionLocal
    from app.services.price_checker import check_all_subscriptions

    db = SessionLocal()
    try:
        check_all_subscriptions(db)
    except Exception as exc:
        logger.error("task_check_price_drops failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 5)
    finally:
        db.close()


@celery_app.task(name="app.worker.task_refresh_apartment_data", bind=True, max_retries=2)
def task_refresh_apartment_data(self):
    """Re-scrape all tracked apartments to refresh pricing data."""
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.apartment import Apartment

    db = SessionLocal()
    try:
        from app.services.scraper_agent.agent import ApartmentAgent

        rows = db.execute(
            select(Apartment.id, Apartment.source_url)
            .where(Apartment.source_url.isnot(None), Apartment.is_available.is_(True))
        ).all()
        logger.info("task_refresh_apartment_data: refreshing %d apartment(s)", len(rows))

        async def _run():
            from urllib.parse import urlparse

            from app.models.site_registry import ScrapeSiteRegistry
            from app.services.scraper_agent.browser_tools import BrowserSession

            async with BrowserSession(headless=True) as shared_browser:
                agent = ApartmentAgent(_browser_instance=shared_browser)
                for apt_id, url in rows:
                    domain = urlparse(url).netloc.lower()
                    registry = db.execute(
                        select(ScrapeSiteRegistry).where(
                            ScrapeSiteRegistry.domain == domain,
                            ScrapeSiteRegistry.is_active.is_(True),
                        )
                    ).scalar_one_or_none()
                    if registry is None:
                        logger.warning(
                            "Domain %s not in registry — skipping apt %d", domain, apt_id
                        )
                        continue
                    if registry.robots_txt_allows is False:
                        logger.warning(
                            "robots.txt disallows %s — skipping apt %d", domain, apt_id
                        )
                        continue

                    try:
                        result, metrics = await agent.scrape(url)
                        logger.info(
                            "Scraped apt %d: cache=%s, %d tok, $%.4f",
                            apt_id, metrics.cache_hit,
                            metrics.total_tokens, metrics.total_cost_usd,
                        )
                        if result:
                            _persist_scraped_prices(apt_id, result, db)
                    except Exception as exc:
                        logger.error(
                            "Failed to scrape apartment %d (%s): %s", apt_id, url, exc
                        )
                    await asyncio.sleep(5)

        global _current_scrape_loop
        loop = asyncio.new_event_loop()
        _current_scrape_loop = loop
        try:
            loop.run_until_complete(_run())
        finally:
            loop.close()
            _current_scrape_loop = None
    except Exception as exc:
        logger.error("task_refresh_apartment_data failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 10)
    finally:
        db.close()


def _match_plan(apt_id: int, fp, db):
    """Find the DB Plan that best matches a scraped FloorPlan.

    Strategy (in order):
    1. Exact ``Plan.name`` match — current behaviour, zero risk.
    2. Fuzzy: same bedroom count + area_sqft within 10% — handles site renames
       like "Studio A" → "S1" without breaking price-history chains.
    """
    from sqlalchemy import select

    from app.models.apartment import Plan

    # 1. Exact match
    plan = db.execute(
        select(Plan).where(Plan.apartment_id == apt_id, Plan.name == fp.name)
    ).scalar_one_or_none()
    if plan:
        return plan

    # 2. Fuzzy match
    if fp.bedrooms is not None and fp.size_sqft is not None:
        candidates = db.execute(
            select(Plan).where(Plan.apartment_id == apt_id, Plan.bedrooms == fp.bedrooms)
        ).scalars().all()
        for c in candidates:
            if c.area_sqft and abs(c.area_sqft - fp.size_sqft) / c.area_sqft < 0.10:
                logger.debug(
                    "Fuzzy-matched scraped plan %r → DB plan %r (apt %d)",
                    fp.name, c.name, apt_id,
                )
                return c
    return None


def _persist_scraped_prices(apt_id: int, result, db) -> None:
    """Write scraped plan prices back to PlanPriceHistory."""
    from datetime import datetime, timezone

    from app.models.apartment import PlanPriceHistory

    for fp in result.floor_plans:
        if fp.min_price is None:
            continue
        plan = _match_plan(apt_id, fp, db)
        if plan is None:
            continue
        history = PlanPriceHistory(
            plan_id=plan.id,
            price=fp.min_price,
            recorded_at=datetime.now(timezone.utc),
        )
        db.add(history)
        plan.price = fp.min_price
    db.commit()
