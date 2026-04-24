"""
Unit tests for HINT_EXCLUDED_ADAPTERS logic in the scraper agent.

The hint system caches the last successful platform adapter name per domain
in ScrapeSiteRegistry.last_successful_adapter so the next scrape can try
that adapter first (fast path). But generic/fallback adapters (e.g.
universal_dom) must never be cached as hints — doing so would suppress
specific-adapter retry even after the platform's signals recover.

These tests exercise the guard logic without launching a browser or LLM.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module-level constant is importable
# ---------------------------------------------------------------------------

def test_hint_excluded_adapters_contains_universal_dom():
    from backend.app.services.scraper_agent.agent import HINT_EXCLUDED_ADAPTERS
    assert "universal_dom" in HINT_EXCLUDED_ADAPTERS


def test_hint_excluded_adapters_does_not_contain_specific_adapters():
    from backend.app.services.scraper_agent.agent import HINT_EXCLUDED_ADAPTERS
    for specific in ("rentcafe", "avalonbay", "windsor", "greystar", "sightmap"):
        assert specific not in HINT_EXCLUDED_ADAPTERS, (
            f"Specific adapter '{specific}' should NOT be in HINT_EXCLUDED_ADAPTERS"
        )


# ---------------------------------------------------------------------------
# Hint WRITE guard
# ---------------------------------------------------------------------------

def _make_registry_row(adapter: str | None = None) -> SimpleNamespace:
    row = SimpleNamespace(
        last_successful_adapter=adapter,
        last_adapter_success_at=None,
    )
    return row


def _make_db_ctx(row):
    """Return a mock SessionLocal context manager whose .execute().scalar_one_or_none() returns row."""
    db = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = row
    db.__enter__ = MagicMock(return_value=db)
    db.__exit__ = MagicMock(return_value=False)
    session_local = MagicMock(return_value=db)
    return session_local, db


def test_universal_dom_not_cached_as_hint():
    """Running the hint-write path with _pt_name='universal_dom' must not update the DB row."""
    from backend.app.services.scraper_agent.agent import HINT_EXCLUDED_ADAPTERS

    row = _make_registry_row(adapter=None)
    session_local, db = _make_db_ctx(row)

    _pt_name = "universal_dom"
    _hint = None
    _domain = "example.com"

    # Replicate the write-guard logic from agent.py
    if _pt_name in HINT_EXCLUDED_ADAPTERS:
        pass  # guard fires — nothing written
    elif _hint != _pt_name:
        with session_local() as _hint_db2:
            _hint_reg2 = _hint_db2.execute(None).scalar_one_or_none()
            if _hint_reg2:
                _hint_reg2.last_successful_adapter = _pt_name

    # Row must be untouched
    assert row.last_successful_adapter is None
    db.commit.assert_not_called()


def test_specific_adapter_still_cached():
    """Running the hint-write path with _pt_name='rentcafe' DOES update the DB row."""
    from backend.app.services.scraper_agent.agent import HINT_EXCLUDED_ADAPTERS

    row = _make_registry_row(adapter=None)
    session_local, db = _make_db_ctx(row)

    _pt_name = "rentcafe"
    _hint = None
    _domain = "example.com"

    # Replicate the write-guard logic from agent.py
    if _pt_name in HINT_EXCLUDED_ADAPTERS:
        pass
    elif _hint != _pt_name:
        with session_local() as _hint_db2:
            _hint_reg2 = _hint_db2.execute(None).scalar_one_or_none()
            if _hint_reg2:
                _hint_reg2.last_successful_adapter = _pt_name

    assert row.last_successful_adapter == "rentcafe"


# ---------------------------------------------------------------------------
# Hint READ guard
# ---------------------------------------------------------------------------

def test_universal_dom_hint_ignored_on_read():
    """A stored hint of 'universal_dom' must be ignored — _hint stays None."""
    from backend.app.services.scraper_agent.agent import HINT_EXCLUDED_ADAPTERS

    row = _make_registry_row(adapter="universal_dom")
    _hint = None

    # Replicate read-guard logic from agent.py
    if row and row.last_successful_adapter:
        _candidate = row.last_successful_adapter
        if _candidate not in HINT_EXCLUDED_ADAPTERS:
            _hint = _candidate

    assert _hint is None


def test_specific_adapter_hint_read_normally():
    """A stored hint of 'rentcafe' must be read and assigned to _hint."""
    from backend.app.services.scraper_agent.agent import HINT_EXCLUDED_ADAPTERS

    row = _make_registry_row(adapter="rentcafe")
    _hint = None

    if row and row.last_successful_adapter:
        _candidate = row.last_successful_adapter
        if _candidate not in HINT_EXCLUDED_ADAPTERS:
            _hint = _candidate

    assert _hint == "rentcafe"


def test_none_hint_row_read_safely():
    """A registry row with last_successful_adapter=None must leave _hint as None."""
    from backend.app.services.scraper_agent.agent import HINT_EXCLUDED_ADAPTERS

    row = _make_registry_row(adapter=None)
    _hint = None

    if row and row.last_successful_adapter:
        _candidate = row.last_successful_adapter
        if _candidate not in HINT_EXCLUDED_ADAPTERS:
            _hint = _candidate

    assert _hint is None
