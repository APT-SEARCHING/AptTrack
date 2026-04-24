"""Unit tests for the hint_adapter_name fast-path in try_platforms."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.services.scraper_agent.platforms.base import PlatformAdapter
from app.services.scraper_agent.platforms.registry import try_platforms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter(name: str, detects: bool = True, units: list | None = None) -> PlatformAdapter:
    adapter = MagicMock(spec=PlatformAdapter)
    adapter.name = name
    adapter.detect = MagicMock(return_value=detects)
    adapter.extract = AsyncMock(return_value=units if units is not None else [{"name": f"plan-{name}"}])
    return adapter


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestHintFastPath:
    def test_hint_hit_short_circuits(self):
        """Hint adapter fires → A and C must never be called."""
        a = _make_adapter("A")
        b = _make_adapter("B")
        c = _make_adapter("C")
        registry = [a, b, c]

        with patch("app.services.scraper_agent.platforms.registry.get_registry", return_value=registry):
            result = _run(try_platforms("<html/>", "https://example.com/fp", MagicMock(), hint_adapter_name="B"))

        assert result is not None
        units, name = result
        assert name == "B"
        b.detect.assert_called_once()
        b.extract.assert_called_once()
        a.detect.assert_not_called()
        c.detect.assert_not_called()

    def test_hint_miss_detect_falls_through(self):
        """Hint adapter detect() returns False → full registry tried (B skipped in loop)."""
        a = _make_adapter("A")
        b = _make_adapter("B", detects=False)
        c = _make_adapter("C")
        registry = [a, b, c]

        with patch("app.services.scraper_agent.platforms.registry.get_registry", return_value=registry):
            result = _run(try_platforms("<html/>", "https://example.com/fp", MagicMock(), hint_adapter_name="B"))

        assert result is not None
        units, name = result
        # B detected False, so A should be found first in fallback
        assert name == "A"
        b.detect.assert_called_once()   # tried first as hint
        a.detect.assert_called_once()   # tried in fallback
        # B must NOT be tried again in the fallback loop
        assert b.detect.call_count == 1

    def test_hint_extract_empty_falls_through(self):
        """Hint detect=True but extract returns [] → fall through to full registry."""
        a = _make_adapter("A")
        b = _make_adapter("B", units=[])   # empty extraction
        c = _make_adapter("C")
        registry = [a, b, c]

        with patch("app.services.scraper_agent.platforms.registry.get_registry", return_value=registry):
            result = _run(try_platforms("<html/>", "https://example.com/fp", MagicMock(), hint_adapter_name="B"))

        assert result is not None
        units, name = result
        assert name == "A"
        b.detect.assert_called_once()
        b.extract.assert_called_once()
        a.detect.assert_called_once()
        # B not retried in the loop
        assert b.detect.call_count == 1

    def test_nonexistent_hint_name_tries_all(self):
        """Hint name 'Z' is not in registry → all adapters tried normally."""
        a = _make_adapter("A")
        b = _make_adapter("B")
        c = _make_adapter("C")
        registry = [a, b, c]

        with patch("app.services.scraper_agent.platforms.registry.get_registry", return_value=registry):
            result = _run(try_platforms("<html/>", "https://example.com/fp", MagicMock(), hint_adapter_name="Z"))

        assert result is not None
        units, name = result
        assert name == "A"    # first in registry
        a.detect.assert_called_once()
        # B and C not needed since A succeeded
        b.detect.assert_not_called()

    def test_no_hint_behaves_as_before(self):
        """Without hint, original left-to-right registry walk is unchanged."""
        a = _make_adapter("A", detects=False)
        b = _make_adapter("B")
        c = _make_adapter("C")
        registry = [a, b, c]

        with patch("app.services.scraper_agent.platforms.registry.get_registry", return_value=registry):
            result = _run(try_platforms("<html/>", "https://example.com/fp", MagicMock()))

        assert result is not None
        units, name = result
        assert name == "B"
        a.detect.assert_called_once()
        b.detect.assert_called_once()
        c.detect.assert_not_called()

    def test_hint_exception_falls_through(self):
        """Hint adapter raises → warning logged, fallback registry tried."""
        a = _make_adapter("A")
        b = _make_adapter("B")
        b.extract = AsyncMock(side_effect=RuntimeError("boom"))
        c = _make_adapter("C")
        registry = [a, b, c]

        with patch("app.services.scraper_agent.platforms.registry.get_registry", return_value=registry):
            result = _run(try_platforms("<html/>", "https://example.com/fp", MagicMock(), hint_adapter_name="B"))

        assert result is not None
        units, name = result
        assert name == "A"
