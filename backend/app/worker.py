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


import re as _re

# ────────────────────────────────────────────────────────────────────────
# Sanitization heuristics for LLM-extracted floor plan data.
# These are deterministic guards complementing the SYSTEM_PROMPT rules.
# Each filter targets a specific bug class identified during dogfood audit
# (see docs/scraper-bugs.md BUG-04, BUG-05, BUG-06).
# ────────────────────────────────────────────────────────────────────────

# Bay Area realistic monthly rent floor. We accept Phase 1 unscrapeable
# policy excludes affordable/subsidized housing, so any rent value below
# this floor is almost certainly a deposit, fee, or extraction error.
_BAY_AREA_RENT_FLOOR = 1500

# Implausibly high values are typos or mis-extraction (e.g. annual rent
# stored as monthly).
_BAY_AREA_RENT_CEILING = 25_000

# Property-style keywords. If a "plan name" contains one AND has multiple
# words AND doesn't look like a floor plan code, it's likely a sibling
# property name extracted from a multi-property comparison page.
_SIBLING_PROPERTY_KEYWORDS = (
    "village", "creek", "terrace", "plaza", "heights", "park",
    "ridge", "court", "place", "gardens", "estates", "hills",
    "commons", "manor", "lake", "pointe",
    "apartments", "playa", "marina",
)

# Plan code prefix patterns: "A1", "B2G", "1x1A", "Studio S1", "Plan A".
# Names matching these are floor-plan codes, never sibling properties,
# even if they happen to contain a keyword.
_PLAN_CODE_PREFIX_RE = _re.compile(
    r"^[A-Z]\d|^\d[xX]\d|^[Ss]tudio\b|^[Pp]lan\s",
)


def _looks_like_sibling_property(name: str) -> bool:
    """Detect if a 'plan name' is actually a sibling property name
    extracted from a multi-property comparison page (BUG-04).

    Examples that should return True:
        "Marina Playa", "Birch Creek", "River Terrace", "Almaden Lake Village",
        "The Marc Apartments", "Briarwood Apartments"

    Examples that should return False (legitimate plan names):
        "A1", "B2G", "1x1A", "Studio S1", "Plan A", "Studio A Loft"
    """
    if not name or len(name) < 5:
        return False
    lower = name.lower()
    words = lower.split()
    if len(words) < 2:
        return False
    # Doesn't look like a plan code → could be property name
    if _PLAN_CODE_PREFIX_RE.match(name):
        return False
    # Has a property-style keyword → likely sibling property
    return any(kw in lower for kw in _SIBLING_PROPERTY_KEYWORDS)


def _looks_like_starting_from_contamination(floor_plans) -> bool:
    """Detect 'Starting From $X' overview-price contamination (BUG-05).

    When the LLM submits findings after seeing only an overview/summary
    page (rather than navigating into per-plan detail), all plans get
    the same single 'starting from' price applied. Symptom: >50% of
    priced plans share the exact same min_price.

    Returns True if contamination is detected and prices should be nulled.
    """
    priced = [fp for fp in floor_plans if fp.min_price is not None]
    if len(priced) < 4:
        # Need enough samples; small lists may legitimately share a price
        return False
    prices = [fp.min_price for fp in priced]
    most_common = max(set(prices), key=prices.count)
    same_count = prices.count(most_common)
    return (same_count / len(priced)) > 0.5


def _sanitize_floor_plans(floor_plans: List) -> tuple:
    """Apply three contamination filters to LLM-extracted floor plans
    before they enter _persist_scraped_prices.

    Filter A (BUG-04): drop FloorPlans whose name looks like a sibling
        property (multi-property comparison contamination)
    Filter B (BUG-06): null min_price/max_price below Bay Area rent floor
        (deposit/fee values misread as rent)
    Filter C (BUG-06): null min_price/max_price above ceiling (typos)
    Filter D (BUG-05): if >50% of priced plans share the same price,
        null all prices (overview "Starting From" contamination)

    Returns a tuple of (cleaned_floor_plans, summary_dict) where
    summary_dict has counts:
        sibling_dropped, deposit_nulled, ceiling_nulled, starting_from_triggered
    """
    summary = {
        "sibling_dropped": 0,
        "deposit_nulled": 0,
        "ceiling_nulled": 0,
        "starting_from_triggered": False,
    }

    cleaned = []
    for fp in floor_plans:
        # Filter A: sibling property
        if _looks_like_sibling_property(fp.name):
            logger.warning(
                "_sanitize: dropping suspected sibling-property name='%s' "
                "(min_price=%s, max_price=%s)",
                fp.name, fp.min_price, fp.max_price,
            )
            summary["sibling_dropped"] += 1
            continue

        # Filter B: deposit/fee floor
        if fp.min_price is not None and fp.min_price < _BAY_AREA_RENT_FLOOR:
            logger.warning(
                "_sanitize: nulling min_price=%s for plan '%s' "
                "(below $%d Bay Area rent floor)",
                fp.min_price, fp.name, _BAY_AREA_RENT_FLOOR,
            )
            fp.min_price = None
            summary["deposit_nulled"] += 1
        if fp.max_price is not None and fp.max_price < _BAY_AREA_RENT_FLOOR:
            fp.max_price = None

        # Filter C: ceiling
        if fp.min_price is not None and fp.min_price > _BAY_AREA_RENT_CEILING:
            logger.warning(
                "_sanitize: nulling min_price=%s for plan '%s' "
                "(above $%d ceiling)",
                fp.min_price, fp.name, _BAY_AREA_RENT_CEILING,
            )
            fp.min_price = None
            summary["ceiling_nulled"] += 1
        if fp.max_price is not None and fp.max_price > _BAY_AREA_RENT_CEILING:
            fp.max_price = None

        cleaned.append(fp)

    # Filter D: starting-from contamination check (after A/B/C)
    if _looks_like_starting_from_contamination(cleaned):
        priced_count = sum(1 for fp in cleaned if fp.min_price is not None)
        logger.warning(
            "_sanitize: 'Starting From' contamination detected: %d/%d plans "
            "share the same price. Nulling all prices to prevent misleading data.",
            priced_count, len(cleaned),
        )
        for fp in cleaned:
            fp.min_price = None
            fp.max_price = None
        summary["starting_from_triggered"] = True

    if any([summary["sibling_dropped"], summary["deposit_nulled"],
            summary["ceiling_nulled"], summary["starting_from_triggered"]]):
        logger.info(
            "_sanitize summary: dropped=%d sibling, nulled=%d below-floor, "
            "nulled=%d above-ceiling, starting_from=%s",
            summary["sibling_dropped"], summary["deposit_nulled"],
            summary["ceiling_nulled"], summary["starting_from_triggered"],
        )

    return cleaned, summary


_GENERIC_NAME_RE = _re.compile(
    r"^\s*(?:studio|\d+)\s*(?:bed)?(?:room)?s?\s*[/\-]\s*\d+\s*bath",
    _re.I,
)

_AVALON_DOMAIN_PATTERNS = (
    "avaloncommunities.com",
    "eavesbyavalon.com",
    "avabyavalon.com",
)


def _normalize_avalon_plan_names(
    apt_id: int,
    source_url: str,
    scraped_floor_plans,
    db,
) -> int:
    """For Avalon properties: rename DB plans with generic names to the
    specific plan codes returned by AvalonBayAdapter, when beds+sqft match.

    Returns count of plans renamed.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.apartment import Plan

    url_lower = (source_url or "").lower()
    if not any(domain in url_lower for domain in _AVALON_DOMAIN_PATTERNS):
        return 0

    existing = db.execute(
        select(Plan).where(
            Plan.apartment_id == apt_id,
            Plan.is_available.is_(True),
        )
    ).scalars().all()

    generic_existing = [p for p in existing if p.name and _GENERIC_NAME_RE.match(p.name)]
    if not generic_existing:
        return 0

    renamed = 0
    for fp in scraped_floor_plans:
        if not fp.name or _GENERIC_NAME_RE.match(fp.name):
            continue  # adapter returned generic too — nothing better to rename to
        if fp.size_sqft is None:
            continue  # need sqft to match

        for plan in list(generic_existing):
            if plan.bedrooms != fp.bedrooms:
                continue
            if plan.area_sqft is None:
                continue
            sqft_delta = abs(plan.area_sqft - fp.size_sqft) / plan.area_sqft
            if sqft_delta > 0.05:
                continue

            logger.info(
                "Avalon name normalize: apt=%d renaming '%s' → '%s' "
                "(beds=%s, db_sqft=%.0f, fp_sqft=%.0f)",
                apt_id, plan.name, fp.name,
                plan.bedrooms, plan.area_sqft, fp.size_sqft,
            )
            plan.name = fp.name
            plan.updated_at = datetime.now(timezone.utc)
            generic_existing.remove(plan)
            renamed += 1
            break  # don't reuse this DB plan for a second fp

    if renamed:
        db.flush()
    return renamed


def _match_plan(apt_id: int, fp, db):
    """Find the DB Plan that best matches a scraped FloorPlan, or create one.

    Strategy (in order):
    1. Exact name match on active plans.
    2. Exact name match on archived plans — reactivate instead of duplicating.
    3. Exact beds + sqft match (±5 sqft tolerance for rounding only) on active
       plans — handles the rare case where an adapter returns the same plan with
       a sqft value rounded differently (e.g. 637 vs 638). Does NOT merge
       distinct floor-plan types with similar sqft.
    4. Auto-create a new Plan row.

    Strategies 2 (beds+sqft ±10%) and 3 (beds+baths weak fuzzy) from the old
    implementation are intentionally removed: they merged distinct floor-plan
    types that happened to have similar sqft, causing prices from different
    plans to collide and be silently dropped (see BUG-12, BUG-13).
    """
    from sqlalchemy import select

    from app.models.apartment import Plan

    # 1. Exact name — active plans
    plan = db.execute(
        select(Plan).where(
            Plan.apartment_id == apt_id,
            Plan.name == fp.name,
            Plan.is_available.is_(True),
        )
    ).scalar_one_or_none()
    if plan:
        return plan

    # 2. Exact name — archived plans (reactivate rather than duplicate)
    archived = db.execute(
        select(Plan).where(
            Plan.apartment_id == apt_id,
            Plan.name == fp.name,
            Plan.is_available.is_(False),
        )
    ).scalar_one_or_none()
    if archived:
        archived.is_available = True
        logger.info(
            "Reactivated archived Plan for apt %d: %r", apt_id, fp.name
        )
        return archived

    # 3. Exact sqft match (±5 sqft) — same bedroom count, single unambiguous candidate
    if fp.bedrooms is not None and fp.size_sqft is not None:
        candidates = db.execute(
            select(Plan).where(
                Plan.apartment_id == apt_id,
                Plan.bedrooms == fp.bedrooms,
                Plan.is_available.is_(True),
            )
        ).scalars().all()
        sqft_matches = [
            c for c in candidates
            if c.area_sqft is not None and abs(c.area_sqft - fp.size_sqft) <= 5
        ]
        if len(sqft_matches) == 1:
            logger.debug(
                "Sqft-matched: %r → %r (apt %d, sqft %.0f≈%.0f)",
                fp.name, sqft_matches[0].name, apt_id,
                fp.size_sqft, sqft_matches[0].area_sqft,
            )
            return sqft_matches[0]

    # 4. Auto-create
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
        db.flush()
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


_AVAIL_DATE_RE = _re.compile(
    r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})"   # MM/DD/YYYY or MM-DD-YY
    r"|(\d{4})-(\d{2})-(\d{2})",               # YYYY-MM-DD
)


def _parse_availability(availability: str):
    """Parse a raw availability string into (is_available, available_from).

    Examples:
        "Available Now" / "Available" / None → (True, None)
        "Available 06/04/2026"               → (False, date(2026, 6, 4))
        "Waitlist"                           → (False, None)
    """
    from datetime import date, datetime

    if not availability:
        return True, None

    low = availability.lower().strip()

    if "waitlist" in low:
        return False, None

    m = _AVAIL_DATE_RE.search(availability)
    if m:
        try:
            if m.group(1):  # MM/DD/YYYY
                mo, dy, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if yr < 100:
                    yr += 2000
            else:            # YYYY-MM-DD
                yr, mo, dy = int(m.group(4)), int(m.group(5)), int(m.group(6))
            avail_date = datetime(yr, mo, dy)
            is_now = avail_date.date() <= date.today()
            return is_now, None if is_now else avail_date
        except ValueError:
            pass

    # "now" / "available" / unknown → treat as available now
    return True, None


def _match_or_create_unit(plan_id: int, fp, db):
    """Find an existing Unit by unit_number and update it, or create a new one."""
    from sqlalchemy import select
    from app.models.apartment import Unit

    is_available, available_from = _parse_availability(
        getattr(fp, "availability", None)
    )

    if fp.unit_number:
        unit = db.execute(
            select(Unit).where(Unit.plan_id == plan_id, Unit.unit_number == fp.unit_number)
        ).scalar_one_or_none()
        if unit:
            unit.price = fp.min_price
            unit.is_available = is_available
            unit.available_from = available_from
            unit.area_sqft = fp.size_sqft
            unit.floor_level = fp.floor_level
            unit.facing = fp.facing
            return unit

    unit = Unit(
        plan_id=plan_id,
        unit_number=fp.unit_number,
        price=fp.min_price,
        area_sqft=fp.size_sqft,
        floor_level=fp.floor_level,
        facing=fp.facing,
        is_available=is_available,
        available_from=available_from,
    )
    db.add(unit)
    db.flush()
    return unit


def _pause_stale_unit_subscriptions(apt_id: int, db) -> None:
    """Auto-pause unit-level subscriptions when the unit is no longer available (D1)."""
    from sqlalchemy import select
    from app.models.apartment import Plan, Unit
    from app.models.user import PriceSubscription

    stale_subs = db.execute(
        select(PriceSubscription)
        .join(Unit, Unit.id == PriceSubscription.unit_id)
        .join(Plan, Plan.id == Unit.plan_id)
        .where(
            Plan.apartment_id == apt_id,
            PriceSubscription.unit_id.isnot(None),
            PriceSubscription.is_active.is_(True),
            Unit.is_available.is_(False),
        )
    ).scalars().all()

    for sub in stale_subs:
        sub.is_active = False
        logger.info(
            "Auto-paused sub %d (unit %d no longer available)",
            sub.id, sub.unit_id,
        )
        try:
            from app.services.notification import send_unit_unavailable_notice
            send_unit_unavailable_notice(sub, db)
        except Exception as exc:
            logger.warning("Failed to send unit-unavailable notice for sub %d: %s", sub.id, exc)

    if stale_subs:
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

    from app.models.apartment import Unit

    now = datetime.now(timezone.utc)

    # Sanitize floor plans: filter contamination from LLM extraction
    # (sibling properties, deposit/fee floor, "starting from" overview).
    # See docs/scraper-bugs.md BUG-04, BUG-05, BUG-06.
    result.floor_plans, _sanitize_summary = _sanitize_floor_plans(result.floor_plans)

    # Avalon name normalization pre-pass: rename generic DB plan names (e.g.
    # "1 Bed / 1 Bath") to specific adapter codes (e.g. "A2G") so that
    # _match_plan strategy 1 (exact name) succeeds on this and future scrapes.
    try:
        _apt_for_norm = db.execute(
            select(Apartment).where(Apartment.id == apt_id)
        ).scalar_one_or_none()
        if _apt_for_norm and _apt_for_norm.source_url:
            _renamed = _normalize_avalon_plan_names(
                apt_id, _apt_for_norm.source_url, result.floor_plans, db,
            )
            if _renamed > 0:
                logger.info(
                    "apt %d: %d Avalon plan(s) renamed from generic to specific code",
                    apt_id, _renamed,
                )
    except Exception as _exc:
        logger.warning("Avalon name normalize failed for apt %d: %s", apt_id, _exc)

    # Pass 1: collect all FloorPlans grouped by matched Plan, preserving per-unit detail.
    # Each FloorPlan becomes one Unit row; Plan gets min/max across its units.
    plan_fps: dict = {}  # plan.id → {"plan": Plan, "fps": [FloorPlan]}

    for fp in result.floor_plans:
        plan = _match_plan(apt_id, fp, db)
        if plan is None:
            continue
        if plan.id not in plan_fps:
            plan_fps[plan.id] = {"plan": plan, "fps": []}
        plan_fps[plan.id]["fps"].append(fp)

    # Pass 2: persist per-plan aggregate + per-unit rows.
    scraped_plan_ids: set = set()
    for plan_id, data in plan_fps.items():
        plan = data["plan"]
        fps = data["fps"]
        scraped_plan_ids.add(plan_id)

        priced = [f.min_price for f in fps if f.min_price is not None]
        min_price = min(priced) if priced else None
        max_price = max(priced) if priced else None

        plan.price = min_price
        plan.current_price = min_price
        plan.max_price = max_price if (max_price is not None and max_price != min_price) else None

        # Backfill descriptors from the min-price representative FloorPlan
        rep = min(fps, key=lambda f: f.min_price or float("inf")) if priced else fps[0]
        if rep.size_sqft is not None:
            if plan.area_sqft is None or abs((plan.area_sqft or 0) - rep.size_sqft) > 10:
                plan.area_sqft = rep.size_sqft
        if rep.bedrooms is not None and plan.bedrooms != rep.bedrooms:
            plan.bedrooms = rep.bedrooms
        if rep.bathrooms is not None and plan.bathrooms != rep.bathrooms:
            plan.bathrooms = rep.bathrooms
        if rep.name and plan.name in (None, "", "Unit"):
            plan.name = rep.name
        if rep.external_url:
            plan.external_url = rep.external_url
        if rep.floor_level is not None:
            plan.floor_level = rep.floor_level
        if rep.facing:
            plan.facing = rep.facing

        # PlanPriceHistory: one row per scrape cycle at the min (from $X) price
        if min_price is not None:
            db.add(PlanPriceHistory(plan_id=plan.id, price=min_price, recorded_at=now))

        # Upsert Unit rows — one per FloorPlan entry
        scraped_unit_numbers: set = set()
        for fp in fps:
            unit = _match_or_create_unit(plan.id, fp, db)
            unit.price = fp.min_price
            if fp.size_sqft is not None:
                unit.area_sqft = fp.size_sqft
            if fp.floor_level is not None:
                unit.floor_level = fp.floor_level
            if fp.facing:
                unit.facing = fp.facing
            unit.is_available = True
            unit.last_scraped_at = now
            if fp.unit_number:
                scraped_unit_numbers.add(fp.unit_number)

        # Mark units no longer returned as unavailable (they've been leased)
        if scraped_unit_numbers:
            from sqlalchemy import update as sa_update
            db.execute(
                sa_update(Unit)
                .where(
                    Unit.plan_id == plan.id,
                    Unit.unit_number.notin_(scraped_unit_numbers),
                    Unit.unit_number.isnot(None),
                )
                .values(is_available=False)
            )

    db.commit()

    # D1: auto-pause unit subscriptions whose unit is now unavailable + notify
    _pause_stale_unit_subscriptions(apt_id, db)
