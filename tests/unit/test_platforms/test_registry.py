"""Unit tests for the platform adapter registry (try_platforms)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "backend"))

from app.services.scraper_agent.platforms.base import PlatformAdapter
from app.services.scraper_agent.platforms.registry import try_platforms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter(name: str, *, detects: bool, units: list | None = None, raises: bool = False):
    """Build a minimal mock PlatformAdapter."""

    class _Adapter(PlatformAdapter):
        def detect(self, html, url):
            return detects

        async def extract(self, html, url, browser):
            if raises:
                raise RuntimeError("boom")
            return units or []

    a = _Adapter()
    a.name = name
    return a


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_try_platforms_returns_first_match():
    """First adapter that detects AND returns units wins; second adapter not called."""
    units_a = [{"plan_name": "A1", "bedrooms": 1, "price": 2000}]
    adapter_a = _make_adapter("alpha", detects=True, units=units_a)
    adapter_b = _make_adapter("beta", detects=True, units=[{"plan_name": "B1"}])

    # Spy on beta's extract to confirm it's never reached
    beta_extract_called = False
    original_extract = adapter_b.extract

    async def _spy(html, url, browser):
        nonlocal beta_extract_called
        beta_extract_called = True
        return await original_extract(html, url, browser)

    adapter_b.extract = _spy

    with patch(
        "app.services.scraper_agent.platforms.registry.get_registry",
        return_value=[adapter_a, adapter_b],
    ):
        result = await try_platforms("<html>", "https://example.com", browser=MagicMock())

    assert result is not None
    returned_units, name = result
    assert name == "alpha"
    assert returned_units == units_a
    assert not beta_extract_called


@pytest.mark.asyncio
async def test_try_platforms_falls_through_on_exception():
    """If an adapter's extract() raises, registry logs a warning and tries the next adapter."""
    adapter_bad = _make_adapter("bad", detects=True, raises=True)
    units_good = [{"plan_name": "G1", "bedrooms": 0, "price": 1800}]
    adapter_good = _make_adapter("good", detects=True, units=units_good)

    with patch(
        "app.services.scraper_agent.platforms.registry.get_registry",
        return_value=[adapter_bad, adapter_good],
    ):
        result = await try_platforms("<html>", "https://example.com", browser=MagicMock())

    assert result is not None
    units, name = result
    assert name == "good"
    assert units == units_good


@pytest.mark.asyncio
async def test_try_platforms_returns_none_when_no_match():
    """All adapters detect=False → try_platforms returns None."""
    adapters = [
        _make_adapter("x", detects=False),
        _make_adapter("y", detects=False),
    ]

    with patch(
        "app.services.scraper_agent.platforms.registry.get_registry",
        return_value=adapters,
    ):
        result = await try_platforms("<html>", "https://example.com", browser=MagicMock())

    assert result is None
