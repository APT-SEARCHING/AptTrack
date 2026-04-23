"""Unit tests for the negative-path scrape cache module."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

import app.db.base  # noqa: F401 — registers all models
from app.db.base_class import Base
from app.models.negative_scrape_cache import NegativeScrapeCache
from app.services.scraper_agent.negative_cache import (
    FAILURE_OUTCOMES,
    SUCCESS_OUTCOMES,
    clear,
    record_failure,
    should_skip,
)

URL = "https://www.example-apt.com/floorplans"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# should_skip
# ---------------------------------------------------------------------------

def test_should_skip_returns_none_when_no_entry(db):
    assert should_skip(URL, db) is None


def test_should_skip_returns_none_when_retry_after_passed(db):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    db.add(NegativeScrapeCache(
        url=URL,
        last_reason="validated_fail",
        attempt_count=1,
        retry_after=past,
    ))
    db.commit()
    assert should_skip(URL, db) is None


def test_should_skip_returns_row_within_window(db):
    future = datetime.now(timezone.utc) + timedelta(days=5)
    db.add(NegativeScrapeCache(
        url=URL,
        last_reason="validated_fail",
        attempt_count=1,
        retry_after=future,
    ))
    db.commit()
    row = should_skip(URL, db)
    assert row is not None
    assert row.url == URL


# ---------------------------------------------------------------------------
# record_failure — new entry
# ---------------------------------------------------------------------------

def test_record_failure_creates_entry(db):
    record_failure(URL, "validated_fail", db)
    row = db.get(NegativeScrapeCache, URL)
    assert row is not None
    assert row.last_reason == "validated_fail"
    assert row.attempt_count == 1


def test_record_failure_first_backoff_is_7_days(db):
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    record_failure(URL, "validated_fail", db)
    row = db.get(NegativeScrapeCache, URL)
    # SQLite returns naive datetimes; strip tz for comparison
    retry = row.retry_after.replace(tzinfo=None) if row.retry_after.tzinfo else row.retry_after
    delta = retry - before
    assert 6 <= delta.days <= 7  # at least 6 days, at most 7


# ---------------------------------------------------------------------------
# record_failure — exponential backoff
# ---------------------------------------------------------------------------

def test_record_failure_backoff_14_days_on_second(db):
    record_failure(URL, "validated_fail", db)
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    record_failure(URL, "hard_fail", db)
    row = db.get(NegativeScrapeCache, URL)
    assert row.attempt_count == 2
    retry = row.retry_after.replace(tzinfo=None) if row.retry_after.tzinfo else row.retry_after
    delta = retry - before
    assert 13 <= delta.days <= 14


def test_record_failure_backoff_30_days_on_third(db):
    record_failure(URL, "validated_fail", db)
    record_failure(URL, "validated_fail", db)
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    record_failure(URL, "hard_fail", db)
    row = db.get(NegativeScrapeCache, URL)
    assert row.attempt_count == 3
    retry = row.retry_after.replace(tzinfo=None) if row.retry_after.tzinfo else row.retry_after
    delta = retry - before
    assert 29 <= delta.days <= 30


def test_record_failure_backoff_capped_at_30_days(db):
    """4th+ failure must still use 30-day window."""
    for _ in range(5):
        record_failure(URL, "validated_fail", db)
    row = db.get(NegativeScrapeCache, URL)
    assert row.attempt_count == 5
    before = datetime.now(timezone.utc).replace(tzinfo=None)
    record_failure(URL, "validated_fail", db)
    row = db.get(NegativeScrapeCache, URL)
    retry = row.retry_after.replace(tzinfo=None) if row.retry_after.tzinfo else row.retry_after
    delta = retry - before
    assert 29 <= delta.days <= 30


def test_record_failure_updates_last_reason(db):
    record_failure(URL, "validated_fail", db)
    record_failure(URL, "hard_fail", db)
    row = db.get(NegativeScrapeCache, URL)
    assert row.last_reason == "hard_fail"


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_removes_entry(db):
    record_failure(URL, "validated_fail", db)
    assert db.get(NegativeScrapeCache, URL) is not None
    clear(URL, db)
    assert db.get(NegativeScrapeCache, URL) is None


def test_clear_noop_when_no_entry(db):
    # Should not raise
    clear(URL, db)


def test_clear_then_record_resets_count(db):
    """After a clear + new failure the attempt_count resets to 1."""
    record_failure(URL, "validated_fail", db)
    record_failure(URL, "validated_fail", db)
    clear(URL, db)
    record_failure(URL, "validated_fail", db)
    row = db.get(NegativeScrapeCache, URL)
    assert row.attempt_count == 1


# ---------------------------------------------------------------------------
# Round-trip: should_skip gates correctly after record_failure / clear
# ---------------------------------------------------------------------------

def test_round_trip_suppressed_then_cleared(db):
    record_failure(URL, "validated_fail", db)
    assert should_skip(URL, db) is not None   # suppressed
    clear(URL, db)
    assert should_skip(URL, db) is None       # cleared


def test_round_trip_suppressed_then_expired(db):
    # Manually insert an already-expired row
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.add(NegativeScrapeCache(
        url=URL,
        last_reason="validated_fail",
        attempt_count=1,
        retry_after=past,
    ))
    db.commit()
    assert should_skip(URL, db) is None       # expired — not suppressed


# ---------------------------------------------------------------------------
# Outcome set membership
# ---------------------------------------------------------------------------

def test_success_outcomes_set():
    assert "success" in SUCCESS_OUTCOMES
    assert "content_unchanged" in SUCCESS_OUTCOMES
    assert "cache_hit" in SUCCESS_OUTCOMES
    assert "platform_direct" in SUCCESS_OUTCOMES
    assert "validated_fail" not in SUCCESS_OUTCOMES


def test_failure_outcomes_set():
    assert "validated_fail" in FAILURE_OUTCOMES
    assert "hard_fail" in FAILURE_OUTCOMES
    assert "success" not in FAILURE_OUTCOMES
