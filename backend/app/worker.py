"""Celery application and beat schedule.

Workers:
  celery -A app.worker worker --loglevel=info

Beat scheduler:
  celery -A app.worker beat --loglevel=info
"""

import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

logger = logging.getLogger(__name__)

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
    import asyncio

    from app.db.session import SessionLocal
    from app.models.apartment import Apartment

    db = SessionLocal()
    try:
        # Import the agentic scraper. It lives in tests/ during development;
        # in production Docker the repo root is on PYTHONPATH so both paths work.
        try:
            from tests.integration.agentic_scraper.agent import ApartmentAgent
        except ImportError:
            try:
                from integration.agentic_scraper.agent import ApartmentAgent  # type: ignore[no-redef]
            except ImportError:
                logger.error(
                    "task_refresh_apartment_data: ApartmentAgent not importable — "
                    "ensure the repo root is on PYTHONPATH or the scraper has been "
                    "promoted to backend/app/services/."
                )
                return

        apts = (
            db.query(Apartment.id, Apartment.source_url)
            .filter(Apartment.source_url.isnot(None), Apartment.is_available.is_(True))
            .all()
        )
        logger.info("task_refresh_apartment_data: refreshing %d apartment(s)", len(apts))

        async def _run():
            agent = ApartmentAgent()
            for apt_id, url in apts:
                try:
                    result = await agent.scrape(url)
                    if result:
                        _persist_scraped_prices(apt_id, result, db)
                except Exception as exc:
                    logger.error("Failed to scrape apartment %d (%s): %s", apt_id, url, exc)

        asyncio.run(_run())
    except Exception as exc:
        logger.error("task_refresh_apartment_data failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 10)
    finally:
        db.close()


def _persist_scraped_prices(apt_id: int, result, db) -> None:
    """Write scraped plan prices back to PlanPriceHistory."""
    from datetime import datetime, timezone

    from app.models.apartment import Plan, PlanPriceHistory

    for fp in result.floor_plans:
        if fp.min_price is None:
            continue
        plan = (
            db.query(Plan)
            .filter(Plan.apartment_id == apt_id, Plan.name == fp.name)
            .first()
        )
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
