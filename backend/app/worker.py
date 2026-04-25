"""Celery application and beat schedule.

Workers:
  celery -A app.worker worker --loglevel=info

Beat scheduler:
  celery -A app.worker beat --loglevel=info
"""

import asyncio
import logging
from typing import List, Optional

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
            "schedule": crontab(hour=8, minute=0),   # 08:00 PT daily
        },
        "refresh-apartment-data": {
            "task": "app.worker.task_refresh_apartment_data",
            "schedule": crontab(hour=2, minute=0),   # 02:00 PT daily
        },
        "nightly-scrape-digest": {
            "task": "app.worker.task_nightly_scrape_digest",
            "schedule": crontab(hour=9, minute=0),   # 09:00 PT daily
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


@celery_app.task(name="app.worker.task_nightly_scrape_digest", bind=True, max_retries=1)
def task_nightly_scrape_digest(self):
    """Aggregate last 24h of ScrapeRun rows and send a Telegram digest.

    Silently skips the Telegram send if TELEGRAM_ADMIN_CHAT_ID is not set.
    """
    from datetime import datetime, timedelta, timezone
    from urllib.parse import urlparse

    from sqlalchemy import select

    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.models.scrape_run import ScrapeRun

    db = SessionLocal()
    try:
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        runs = db.execute(
            select(ScrapeRun).where(ScrapeRun.run_at >= since)
        ).scalars().all()

        if not runs:
            logger.info("task_nightly_scrape_digest: no scrape runs in last 24h")
            return

        total = len(runs)
        by_outcome: dict[str, int] = {}
        for r in runs:
            by_outcome[r.outcome] = by_outcome.get(r.outcome, 0) + 1

        costs = sorted(r.cost_usd for r in runs if r.cost_usd > 0)
        total_cost = sum(costs)
        p50 = costs[len(costs) // 2] if costs else 0.0
        p95 = costs[int(len(costs) * 0.95)] if costs else 0.0

        # Failure count by domain
        domain_failures: dict[str, int] = {}
        for r in runs:
            if r.outcome in ("hard_fail", "validated_fail"):
                domain = urlparse(r.url).netloc.lower()
                domain_failures[domain] = domain_failures.get(domain, 0) + 1
        top_failures = sorted(domain_failures.items(), key=lambda x: -x[1])[:5]

        def pct(n: int) -> str:
            return f"{100 * n // total}%" if total else "0%"

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        lines = [
            f"📊 *AptTrack Nightly Digest* — {date_str}",
            "",
            f"Scrapes last 24h: *{total}*",
            f"✅ Success:    {by_outcome.get('success', 0):>4}  ({pct(by_outcome.get('success', 0))})",
            f"💾 Cache hit:  {by_outcome.get('cache_hit', 0):>4}  ({pct(by_outcome.get('cache_hit', 0))})",
            f"⚡ Unchanged:  {by_outcome.get('content_unchanged', 0):>4}  ({pct(by_outcome.get('content_unchanged', 0))})",
            f"❌ Failed:     {by_outcome.get('hard_fail', 0) + by_outcome.get('validated_fail', 0):>4}  "
            f"({pct(by_outcome.get('hard_fail', 0) + by_outcome.get('validated_fail', 0))})",
            "",
            f"💰 Total cost: *${total_cost:.2f}*",
            f"   Median ${p50:.4f} · p95 ${p95:.4f}",
        ]
        if top_failures:
            lines += ["", "Top failures:"]
            for domain, count in top_failures:
                lines.append(f"  {domain} — {count}")

        message = "\n".join(lines)
        logger.info("Nightly digest:\n%s", message)

        if settings.TELEGRAM_ADMIN_CHAT_ID:
            loop = asyncio.new_event_loop()
            try:
                from app.services.notification import send_telegram_alert
                loop.run_until_complete(
                    send_telegram_alert(settings.TELEGRAM_ADMIN_CHAT_ID, message)
                )
            finally:
                loop.close()
        else:
            logger.info("task_nightly_scrape_digest: TELEGRAM_ADMIN_CHAT_ID not set — digest logged only")

    except Exception as exc:
        logger.error("task_nightly_scrape_digest failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
    finally:
        db.close()


CHUNK_SIZE = 50  # apartments per chunk task


@celery_app.task(name="app.worker.task_refresh_apartment_data", bind=True, max_retries=2)
def task_refresh_apartment_data(self):
    """Dispatcher: query all available apartment IDs and enqueue chunk tasks.

    Splits IDs into chunks of CHUNK_SIZE and dispatches each chunk with a
    30-second countdown stagger to avoid a thundering herd against scrape targets.
    """
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.apartment import Apartment

    db = SessionLocal()
    try:
        rows = db.execute(
            select(Apartment.id)
            .where(Apartment.source_url.isnot(None), Apartment.is_available.is_(True))
        ).scalars().all()
        apt_ids: List[int] = list(rows)
        logger.info(
            "task_refresh_apartment_data: dispatching %d apartment(s) in chunks of %d",
            len(apt_ids), CHUNK_SIZE,
        )

        chunks = [apt_ids[i : i + CHUNK_SIZE] for i in range(0, len(apt_ids), CHUNK_SIZE)]
        for i, chunk in enumerate(chunks):
            task_refresh_apartment_chunk.apply_async(
                args=[chunk],
                countdown=i * 30,  # stagger by 30 s per chunk
            )
            logger.info(
                "Enqueued chunk %d/%d (%d apts, countdown=%ds)",
                i + 1, len(chunks), len(chunk), i * 30,
            )
    except Exception as exc:
        logger.error("task_refresh_apartment_data failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * 10)
    finally:
        db.close()


@celery_app.task(name="app.worker.task_refresh_apartment_chunk", bind=True, max_retries=1)
def task_refresh_apartment_chunk(self, apartment_ids: List[int]):
    """Worker: scrape a chunk of apartments with 2-way concurrency via a browser pool.

    Uses an asyncio.Queue of 2 BrowserSession instances so at most 2 apartments
    are scraped simultaneously.  Each coroutine opens its own DB session to avoid
    SQLAlchemy session-sharing issues.  Errors in one apartment are logged and do
    not abort the rest of the chunk.
    """
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models.apartment import Apartment

    # Fetch (id, source_url) pairs for this chunk and close the DB immediately
    # so no session leaks into the async scope below.
    db = SessionLocal()
    try:
        rows = db.execute(
            select(Apartment.id, Apartment.source_url)
            .where(
                Apartment.id.in_(apartment_ids),
                Apartment.source_url.isnot(None),
                Apartment.is_available.is_(True),
            )
        ).all()
        apt_rows = [(row.id, row.source_url) for row in rows]
    except Exception as exc:
        db.close()
        logger.error("task_refresh_apartment_chunk: DB fetch failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
    else:
        db.close()

    logger.info(
        "task_refresh_apartment_chunk: processing %d apartment(s)", len(apt_rows)
    )

    async def _scrape_one(
        apt_id: int,
        url: str,
        pool: asyncio.Queue,
    ) -> None:
        """Scrape one apartment, borrowing a browser from the pool only when needed.

        Short-circuit order:
          1. aiohttp GET → compute_content_hash → if unchanged, carry forward
             prices and return (0 LLM, 0 browser).
          2. Otherwise acquire a browser and run path-cache replay / LLM agent.

        A ScrapeRun row is written after every code path (best-effort).
        """
        import time
        from datetime import datetime, timezone
        from urllib.parse import urlparse

        import aiohttp
        from sqlalchemy import select as sa_select

        from app.db.session import SessionLocal as _SessionLocal
        from app.models.apartment import Apartment
        from app.models.scrape_run import ScrapeRun
        from app.models.site_registry import ScrapeSiteRegistry
        from app.services.scraper_agent.agent import ApartmentAgent
        from app.services.scraper_agent.content_hash import compute_content_hash

        t_start = time.monotonic()
        original_url = url          # preserved for ScrapeRun.url regardless of redirect
        effective_url: Optional[str] = None  # set when corporate redirect fires
        db = _SessionLocal()
        try:
            domain = urlparse(url).netloc.lower()
            registry = db.execute(
                sa_select(ScrapeSiteRegistry).where(
                    ScrapeSiteRegistry.domain == domain,
                    ScrapeSiteRegistry.is_active.is_(True),
                )
            ).scalar_one_or_none()
            if registry is None:
                logger.warning(
                    "Domain %s not in registry — skipping apt %d", domain, apt_id
                )
                return
            if registry.robots_txt_allows is False:
                logger.warning(
                    "robots.txt disallows %s — skipping apt %d", domain, apt_id
                )
                return

            # ------------------------------------------------------------------
            # Unscrapeable check — site doesn't publish pricing, skip all scraping
            # ------------------------------------------------------------------
            if registry.data_source_type == "unscrapeable":
                logger.info(
                    "apt %d url=%s: registry data_source_type=unscrapeable — skipping",
                    apt_id, url,
                )
                elapsed = time.monotonic() - t_start
                _write_scrape_run(db, apt_id, original_url, ScrapeRun(
                    apartment_id=apt_id,
                    url=original_url,
                    outcome="skipped_unscrapeable",
                    elapsed_sec=elapsed,
                ))
                return

            # ------------------------------------------------------------------
            # Negative-path cache check — skip URLs that have repeatedly failed
            # until their exponential backoff window expires.
            # ------------------------------------------------------------------
            from app.services.scraper_agent.negative_cache import (
                clear as _neg_clear,
                record_failure as _neg_record,
                should_skip as _neg_should_skip,
            )
            neg = _neg_should_skip(original_url, db)
            if neg is not None:
                elapsed = time.monotonic() - t_start
                logger.info(
                    "apt %d: negative cache hit (%s, attempt #%d) — retry_after %s",
                    apt_id, neg.last_reason, neg.attempt_count,
                    neg.retry_after.date().isoformat(),
                )
                _write_scrape_run(db, apt_id, original_url, ScrapeRun(
                    apartment_id=apt_id,
                    url=original_url,
                    outcome="skipped_negative_cache",
                    elapsed_sec=elapsed,
                ))
                return

            # ------------------------------------------------------------------
            # Corporate-parent redirect
            # Brand-front subdomains (e.g. 121tasman.com) serve JS placeholders.
            # When corporate_parent_url is set we scrape the corporate page
            # instead.  original_url is preserved for ScrapeRun.url; the
            # rebound `url` propagates to all downstream code automatically.
            # If the corporate URL is unreachable we fall back to original_url
            # so the LLM agent can still attempt the brand-front site.
            # ------------------------------------------------------------------
            if registry.corporate_parent_url:
                effective_url = registry.corporate_parent_url
                url = registry.corporate_parent_url
                logger.info(
                    "apt %d: corporate redirect %s → %s (%s)",
                    apt_id,
                    original_url,
                    url,
                    registry.corporate_platform or "unknown",
                )

            # ------------------------------------------------------------------
            # Phase 1: content-hash short-circuit (no browser, no LLM)
            # ------------------------------------------------------------------
            new_hash: Optional[str] = None
            _corporate_get_ok: bool = True
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            html = await resp.text(errors="replace")
                            new_hash = compute_content_hash(html)
                        elif effective_url:
                            _corporate_get_ok = False
            except Exception as exc:
                logger.warning(
                    "Content-hash GET failed for apt %d (%s): %s — proceeding to scrape",
                    apt_id, url, exc,
                )
                if effective_url:
                    _corporate_get_ok = False

            # If corporate redirect target is unreachable, fall back to the
            # original brand-front URL for Phase 2 so we don't silently drop
            # the apartment from the scrape cycle.
            if effective_url and not _corporate_get_ok:
                logger.warning(
                    "apt %d: corporate parent %s unreachable — falling back to original %s",
                    apt_id, url, original_url,
                )
                url = original_url
                effective_url = None

            if new_hash is not None:
                apt = db.execute(
                    sa_select(Apartment).where(Apartment.id == apt_id)
                ).scalar_one_or_none()
                if apt is not None and apt.last_content_hash == new_hash:
                    _carry_forward_prices(apt_id, db)
                    apt.last_scraped_at = datetime.now(timezone.utc)
                    db.commit()
                    elapsed = time.monotonic() - t_start
                    logger.info(
                        "apt %d: content unchanged — prices carried forward, $0.00",
                        apt_id,
                    )
                    _write_scrape_run(db, apt_id, original_url, ScrapeRun(
                        apartment_id=apt_id,
                        url=original_url,
                        effective_url=effective_url,
                        outcome="content_unchanged",
                        content_hash_short_circuit=True,
                        elapsed_sec=elapsed,
                    ))
                    _log_scraper_cost(apt_id, original_url, "cache_hit", 0, 0, 0.0, db)
                    _neg_clear(original_url, db)
                    return

            # ------------------------------------------------------------------
            # Phase 2: path-cache replay / LLM agent (requires a browser)
            # ------------------------------------------------------------------
            browser = await pool.get()
            try:
                agent = ApartmentAgent(_browser_instance=browser)
                try:
                    result, metrics = await agent.scrape(url)
                except Exception as exc:
                    elapsed = time.monotonic() - t_start
                    logger.error("Failed to scrape apartment %d (%s): %s", apt_id, url, exc)
                    _write_scrape_run(db, apt_id, original_url, ScrapeRun(
                        apartment_id=apt_id,
                        url=original_url,
                        effective_url=effective_url,
                        outcome="hard_fail",
                        elapsed_sec=elapsed,
                        error_message=str(exc)[:1000],
                    ))
                    _neg_record(original_url, "hard_fail", db)
                    return

                elapsed = time.monotonic() - t_start
                if result and result.floor_plans:
                    outcome = metrics.outcome if metrics.outcome in (
                        "platform_direct", "platform_direct_static", "platform_direct_rendered", "cache_hit",
                    ) else "success"
                    _persist_scraped_prices(apt_id, result, db)
                    if new_hash is not None:
                        apt = db.execute(
                            sa_select(Apartment).where(Apartment.id == apt_id)
                        ).scalar_one_or_none()
                        if apt is not None:
                            apt.last_content_hash = new_hash
                            apt.last_scraped_at = datetime.now(timezone.utc)
                            db.commit()
                else:
                    outcome = "validated_fail"

                logger.info(
                    "apt %d: outcome=%s, %d tok, $%.4f",
                    apt_id, outcome, metrics.total_tokens, metrics.total_cost_usd,
                )
                _write_scrape_run(db, apt_id, original_url, ScrapeRun(
                    apartment_id=apt_id,
                    url=original_url,
                    effective_url=effective_url,
                    outcome=outcome,
                    path_cache_hit=metrics.cache_hit,
                    content_hash_short_circuit=False,
                    iterations=metrics.iterations,
                    llm_calls=len(metrics.calls),
                    input_tokens=metrics.total_input_tokens,
                    output_tokens=metrics.total_output_tokens,
                    cost_usd=metrics.total_cost_usd,
                    elapsed_sec=elapsed,
                    adapter_name=metrics.adapter_name,
                ))
                from app.services.scraper_agent.negative_cache import (
                    SUCCESS_OUTCOMES as _NEG_SUCCESS,
                    FAILURE_OUTCOMES as _NEG_FAIL,
                )
                if outcome in _NEG_SUCCESS:
                    _neg_clear(original_url, db)
                elif outcome in _NEG_FAIL:
                    _neg_record(original_url, outcome, db)
                _log_scraper_cost(
                    apt_id, url,
                    "cache_hit" if metrics.cache_hit else outcome,
                    metrics.total_input_tokens,
                    metrics.total_output_tokens,
                    metrics.total_cost_usd,
                    db,
                )
            finally:
                await asyncio.sleep(5)  # polite inter-scrape delay
                await pool.put(browser)

        except Exception as exc:
            elapsed = time.monotonic() - t_start
            logger.error("Failed to scrape apartment %d (%s): %s", apt_id, url, exc)
            _write_scrape_run(db, apt_id, original_url, ScrapeRun(
                apartment_id=apt_id,
                url=original_url,
                effective_url=effective_url if effective_url != original_url else None,
                outcome="hard_fail",
                elapsed_sec=elapsed,
                error_message=str(exc)[:1000],
            ))
            try:
                from app.services.scraper_agent.negative_cache import record_failure as _nr
                _nr(original_url, "hard_fail", db)
            except Exception:
                pass
        finally:
            db.close()

    async def _run():
        from app.services.scraper_agent.browser_tools import BrowserSession

        # Start exactly 2 browsers and put them in the pool.
        # 50 coroutines are launched simultaneously but at most 2 run at a time
        # because pool.get() blocks until a browser is returned.
        browsers = [BrowserSession(headless=True), BrowserSession(headless=True)]
        for b in browsers:
            await b.__aenter__()

        pool: asyncio.Queue = asyncio.Queue()
        for b in browsers:
            await pool.put(b)

        try:
            await asyncio.gather(*[_scrape_one(apt_id, url, pool) for apt_id, url in apt_rows])
        finally:
            # Drain the pool and close both browsers.
            closed: list = []
            while not pool.empty():
                b = pool.get_nowait()
                if b not in closed:
                    await b.__aexit__(None, None, None)
                    closed.append(b)
            # Close any browsers that were still checked out when gather finished.
            for b in browsers:
                if b not in closed:
                    try:
                        await b.__aexit__(None, None, None)
                    except Exception:
                        pass

    global _current_scrape_loop
    loop = asyncio.new_event_loop()
    _current_scrape_loop = loop
    try:
        loop.run_until_complete(_run())
    except Exception as exc:
        logger.error("task_refresh_apartment_chunk failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)
    finally:
        loop.close()
        _current_scrape_loop = None


def _log_scraper_cost(
    apt_id: int, url: str, outcome: str,
    input_tok: int, output_tok: int, cost_usd: float,
    db,
) -> None:
    """Append one cost log entry — best-effort, never raises."""
    try:
        from sqlalchemy import select as sa_select

        from app.core.cost_log import append_scraper_entry
        from app.models.apartment import Apartment
        apt = db.execute(sa_select(Apartment).where(Apartment.id == apt_id)).scalar_one_or_none()
        name = apt.title if apt else f"apt#{apt_id}"
        append_scraper_entry(
            name=name, url=url, outcome=outcome,
            input_tok=input_tok, output_tok=output_tok, cost_usd=cost_usd,
            db=db,
        )
    except Exception as exc:
        logger.warning("cost_log: failed to write scraper entry for apt %d: %s", apt_id, exc)


def _match_plan(apt_id: int, fp, db):
    """Find the DB Plan that best matches a scraped FloorPlan, or create one.

    Strategy (in order):
    1. Exact ``Plan.name`` match — zero risk.
    2. Fuzzy: same bedroom count + area_sqft within 10% — handles site renames.
    3. Weak fuzzy: same beds + baths, only when single unambiguous candidate.
    4. Auto-create: new Plan row when fp.bedrooms is known.
    """
    from sqlalchemy import select

    from app.models.apartment import Plan

    # 1. Exact name
    plan = db.execute(
        select(Plan).where(Plan.apartment_id == apt_id, Plan.name == fp.name)
    ).scalar_one_or_none()
    if plan:
        return plan

    # 2. Fuzzy by beds + sqft ±10%
    if fp.bedrooms is not None and fp.size_sqft is not None:
        candidates = db.execute(
            select(Plan).where(Plan.apartment_id == apt_id, Plan.bedrooms == fp.bedrooms)
        ).scalars().all()
        for c in candidates:
            if c.area_sqft and abs(c.area_sqft - fp.size_sqft) / c.area_sqft < 0.10:
                logger.debug(
                    "Fuzzy-matched (beds+sqft): %r → %r (apt %d)",
                    fp.name, c.name, apt_id,
                )
                return c

    # 3. Weak fuzzy by beds + baths — only when single unambiguous candidate
    if fp.bedrooms is not None and fp.bathrooms is not None:
        candidates = db.execute(
            select(Plan).where(
                Plan.apartment_id == apt_id,
                Plan.bedrooms == fp.bedrooms,
                Plan.bathrooms == fp.bathrooms,
            )
        ).scalars().all()
        if len(candidates) == 1:
            logger.debug(
                "Weak-matched (beds+baths): %r → %r (apt %d)",
                fp.name, candidates[0].name, apt_id,
            )
            return candidates[0]

    # 4. Auto-create when we have enough info
    if fp.bedrooms is not None:
        new_plan = Plan(
            apartment_id=apt_id,
            name=fp.name or "Unit",
            bedrooms=fp.bedrooms,
            bathrooms=fp.bathrooms or 1.0,
            area_sqft=fp.size_sqft or 0.0,
            price=fp.min_price,
            current_price=fp.min_price,
            is_available=True,
        )
        db.add(new_plan)
        db.flush()  # assign new_plan.id for downstream PlanPriceHistory write
        logger.info(
            "Auto-created Plan for apt %d: %r (%s BR, %s BA)",
            apt_id, fp.name, fp.bedrooms, fp.bathrooms,
        )
        return new_plan

    logger.warning(
        "Could not match or create plan for fp=%r in apt %d (missing bedrooms)",
        fp.name, apt_id,
    )
    return None


def _write_scrape_run(db, apt_id: int, url: str, run) -> None:
    """Persist a ScrapeRun row — best-effort, never raises."""
    try:
        db.add(run)
        db.commit()
    except Exception as exc:
        logger.warning("Failed to write ScrapeRun for apt %d: %s", apt_id, exc)
        db.rollback()


def _carry_forward_prices(apt_id: int, db) -> None:
    """Copy the most recent PlanPriceHistory row for each plan to today.

    Called when the content hash is unchanged so the price-history chain stays
    continuous without a full re-scrape.  No-ops silently if a plan has no
    history yet (new plan that was never scraped with a price).
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.apartment import Plan, PlanPriceHistory

    now = datetime.now(timezone.utc)
    plans = db.execute(
        select(Plan).where(Plan.apartment_id == apt_id)
    ).scalars().all()
    for plan in plans:
        latest = db.execute(
            select(PlanPriceHistory)
            .where(PlanPriceHistory.plan_id == plan.id)
            .order_by(PlanPriceHistory.recorded_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if latest is not None:
            db.add(PlanPriceHistory(
                plan_id=plan.id,
                price=latest.price,
                recorded_at=now,
            ))
            # Keep current_price in sync so apartment-level subscriptions read the correct value
            plan.current_price = latest.price
    db.commit()


def _persist_scraped_prices(apt_id: int, result, db) -> None:
    """Write scraped plan prices back to PlanPriceHistory."""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.apartment import Apartment, PlanPriceHistory

    # Write apartment-level fields (amenities + specials) in one fetch
    needs_apt_update = result.amenities or getattr(result, 'current_special', None) is not None
    if needs_apt_update or getattr(result, 'current_special', None) == '':
        # Always fetch when current_special is present (even empty string = cleared promo)
        pass
    if result.amenities or hasattr(result, 'current_special'):
        apt = db.execute(
            select(Apartment).where(Apartment.id == apt_id)
        ).scalar_one_or_none()
        if apt is not None:
            # Amenities: null from LLM = "unknown" — don't overwrite a previously-captured value
            if result.amenities:
                for key in ("pets_allowed", "has_parking", "has_pool", "has_gym",
                            "has_dishwasher", "has_washer_dryer", "has_air_conditioning"):
                    val = result.amenities.get(key)
                    if val is not None:
                        setattr(apt, key, val)
            # Specials: always overwrite — reflects current promo (None = no promo found)
            if hasattr(result, 'current_special'):
                apt.current_special = result.current_special

    # Aggregate per-unit FloorPlans to one representative per floor plan name.
    # SightMap (and similar platforms) return one FloorPlan per available unit;
    # without this, last-unit-processed wins current_price, causing spurious
    # price-change alerts when scrape order shifts between runs.
    # We keep the lowest-priced unit's full metadata so current_price = "from $X".
    from collections import defaultdict
    plan_groups: dict = defaultdict(lambda: {"price": None, "fp": None})
    for fp in result.floor_plans:
        group = plan_groups[fp.name]
        if fp.min_price is None:
            if group["fp"] is None:
                group["fp"] = fp
            continue
        if group["price"] is None or fp.min_price < group["price"]:
            group["price"] = fp.min_price
            group["fp"] = fp

    for plan_name, group in plan_groups.items():
        fp = group["fp"]
        final_price = group["price"]

        plan = _match_plan(apt_id, fp, db)
        if plan is None:
            continue
        # Always update plan.price (may be None for "Contact for pricing" sites)
        plan.price = final_price
        # current_price is the authoritative live value; plan.price is deprecated seed column
        plan.current_price = final_price
        # Backfill / refresh descriptor fields when the scraper found data the DB doesn't have
        if fp.size_sqft is not None:
            if plan.area_sqft is None or abs((plan.area_sqft or 0) - fp.size_sqft) > 10:
                plan.area_sqft = fp.size_sqft
        if fp.bedrooms is not None and plan.bedrooms != fp.bedrooms:
            plan.bedrooms = fp.bedrooms
        if fp.bathrooms is not None and plan.bathrooms != fp.bathrooms:
            plan.bathrooms = fp.bathrooms
        # Name: only update if DB has placeholder or empty
        if fp.name and plan.name in (None, '', 'Unit'):
            plan.name = fp.name
        # Update deep link / position when the scraper found them; don't overwrite with None
        if fp.external_url:
            plan.external_url = fp.external_url
        if fp.floor_level is not None:
            plan.floor_level = fp.floor_level
        if fp.facing:
            plan.facing = fp.facing
        if final_price is not None:
            history = PlanPriceHistory(
                plan_id=plan.id,
                price=final_price,
                recorded_at=datetime.now(timezone.utc),
            )
            db.add(history)
    db.commit()
