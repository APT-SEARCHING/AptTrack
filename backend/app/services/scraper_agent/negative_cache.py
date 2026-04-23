"""Negative-path scrape cache.

Suppresses repeated scrape attempts on URLs that have consistently failed,
saving LLM spend on known-broken sites until the backoff window expires.

Backoff schedule (attempt_count → retry window):
  1st failure  →  7 days
  2nd failure  → 14 days
  3rd+ failure → 30 days (capped)

Typical usage in _scrape_one:

    from app.services.scraper_agent.negative_cache import (
        should_skip, record_failure, clear as clear_negative_cache
    )

    # Entry check
    if neg := should_skip(original_url, db):
        logger.info("skipping %s, retry_after=%s", original_url, neg.retry_after)
        return  # write ScrapeRun(outcome="skipped_negative_cache") before returning

    # ... scrape ...

    if outcome in SUCCESS_OUTCOMES:
        clear_negative_cache(original_url, db)
    elif outcome in FAILURE_OUTCOMES:
        record_failure(original_url, outcome, db)

Admin note: when a new PlatformAdapter is added that covers previously failing
sites, clear those entries manually via POST /admin/negative-cache/clear so the
next daily scrape retries them immediately.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.negative_scrape_cache import NegativeScrapeCache

logger = logging.getLogger(__name__)

# Backoff schedule indexed by zero-based attempt number (clamped at index 2).
_BACKOFF_DAYS = [7, 14, 30]

# Outcomes treated as success — clear any suppression entry.
SUCCESS_OUTCOMES = frozenset({"success", "content_unchanged", "cache_hit", "platform_direct"})

# Outcomes treated as failure — record / increment suppression entry.
FAILURE_OUTCOMES = frozenset({"validated_fail", "hard_fail"})


def should_skip(url: str, db: Session) -> Optional[NegativeScrapeCache]:
    """Return the cache row if this URL is still within its suppression window.

    Returns None when the URL is not suppressed (either no entry or backoff expired).
    """
    now = datetime.now(timezone.utc)
    return db.execute(
        select(NegativeScrapeCache).where(
            NegativeScrapeCache.url == url,
            NegativeScrapeCache.retry_after > now,
        )
    ).scalar_one_or_none()


def record_failure(url: str, reason: str, db: Session) -> None:
    """Insert or update the suppression row for *url* with exponential backoff.

    *reason* should be a ScrapeRun outcome string (validated_fail | hard_fail).
    Safe to call multiple times — upserts in place.
    """
    now = datetime.now(timezone.utc)
    existing = db.execute(
        select(NegativeScrapeCache).where(NegativeScrapeCache.url == url)
    ).scalar_one_or_none()

    if existing:
        existing.last_failed_at = now
        existing.last_reason = reason
        existing.attempt_count += 1
        days = _BACKOFF_DAYS[min(existing.attempt_count - 1, len(_BACKOFF_DAYS) - 1)]
        existing.retry_after = now + timedelta(days=days)
        logger.info(
            "negative_cache: %s failure #%d (%s) — suppressed for %d days until %s",
            url, existing.attempt_count, reason, days,
            existing.retry_after.date().isoformat(),
        )
    else:
        days = _BACKOFF_DAYS[0]
        entry = NegativeScrapeCache(
            url=url,
            last_reason=reason,
            retry_after=now + timedelta(days=days),
            attempt_count=1,
        )
        db.add(entry)
        logger.info(
            "negative_cache: new entry for %s (%s) — suppressed for %d days until %s",
            url, reason, days,
            (now + timedelta(days=days)).date().isoformat(),
        )

    try:
        db.commit()
    except Exception as exc:
        logger.warning("negative_cache: failed to persist record_failure for %s: %s", url, exc)
        db.rollback()


def clear(url: str, db: Session) -> None:
    """Remove the suppression entry for *url* (called on successful scrape).

    No-op if no entry exists.
    """
    try:
        result = db.execute(
            delete(NegativeScrapeCache).where(NegativeScrapeCache.url == url)
        )
        db.commit()
        if result.rowcount:
            logger.info("negative_cache: cleared suppression for %s (scrape succeeded)", url)
    except Exception as exc:
        logger.warning("negative_cache: failed to clear %s: %s", url, exc)
        db.rollback()
