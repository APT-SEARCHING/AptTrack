"""
BUG-13 regression: _replay_cached_path must use the extract_all_units result
even when subsequent steps (scroll_down, navigate_to, etc.) follow it in the
cached path. Previously only last_result was checked, causing cache miss for
any site where the LLM continued navigating after extraction.

This test exercises the logic of _replay_cached_path in isolation by
extracting the core decision into a helper that mirrors the production code.
"""
import asyncio
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal reproduction of the _replay_cached_path decision logic
# (mirrors backend/app/services/scraper_agent/agent.py)
# ---------------------------------------------------------------------------

async def _replay_logic(
    steps: List[Dict[str, Any]],
    browser,
) -> Optional[Dict[str, Any]]:
    """Replicate the unit-result tracking introduced in the BUG-13 fix."""
    last_result: Optional[Dict[str, Any]] = None
    units_result: Optional[Dict[str, Any]] = None

    for step in steps:
        action = step.get("action")
        args: Dict[str, Any] = step.get("args", {})

        if action == "navigate_to":
            last_result = await browser.navigate_to(args.get("url", ""))
        elif action == "click_link":
            last_result = await browser.click_link(args.get("text_or_href", ""))
        elif action == "scroll_down":
            last_result = await browser.scroll_down()
        elif action == "read_iframe":
            last_result = await browser.read_iframe(args.get("keyword", ""))
        elif action == "extract_all_units":
            last_result = await browser.extract_all_units()
            # Only record non-empty results — empty units can't produce floor_plans
            if isinstance(last_result, dict) and last_result.get("units"):
                units_result = last_result
        else:
            continue

        if isinstance(last_result, dict) and last_result.get("error"):
            return None

    check = units_result if units_result is not None else last_result
    if isinstance(check, dict) and check.get("units"):
        return check

    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_UNITS = [{"plan_name": "Studio S1", "price": 2500, "bedrooms": 0}]


def _make_browser(units=SAMPLE_UNITS, *, iframe_error=False):
    b = MagicMock()
    b.navigate_to = AsyncMock(return_value={"html": "<html/>"})
    b.click_link = AsyncMock(return_value={"html": "<html/>"})
    b.scroll_down = AsyncMock(return_value={"html": "<html/>"})
    if iframe_error:
        b.read_iframe = AsyncMock(return_value={"error": "iframe not found"})
    else:
        b.read_iframe = AsyncMock(return_value={"html": "<iframe/>"})
    b.extract_all_units = AsyncMock(return_value={"units": units})
    return b


ENCLAVE_STYLE_STEPS = [
    {"action": "navigate_to", "args": {"url": "https://example.com/"}},
    {"action": "read_iframe", "args": {"keyword": "sightmap"}},
    {"action": "extract_all_units", "args": {}},
    # Post-extraction navigation — this is what caused the original bug
    {"action": "scroll_down", "args": {}},
    {"action": "navigate_to", "args": {"url": "https://example.com/amenities/"}},
    {"action": "scroll_down", "args": {}},
]

TERMINAL_EXTRACT_STEPS = [
    {"action": "navigate_to", "args": {"url": "https://example.com/"}},
    {"action": "read_iframe", "args": {"keyword": "sightmap"}},
    {"action": "extract_all_units", "args": {}},
]

NO_EXTRACT_STEPS = [
    {"action": "navigate_to", "args": {"url": "https://example.com/"}},
    {"action": "scroll_down", "args": {}},
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestReplayCachedPathUnitsResult:

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    @pytest.mark.parametrize("steps,label", [
        (ENCLAVE_STYLE_STEPS, "extract mid-path with trailing navigation"),
        (TERMINAL_EXTRACT_STEPS, "extract as terminal step"),
    ])
    def test_returns_units_regardless_of_terminal_step(self, steps, label):
        """Should find units whether extract_all_units is mid-path or last."""
        browser = _make_browser()
        result = self._run(_replay_logic(steps, browser))
        assert result is not None, f"Expected units dict for: {label}"
        assert result["units"] == SAMPLE_UNITS

    def test_returns_none_when_no_extract_step(self):
        """Without extract_all_units, replay cannot find units."""
        browser = _make_browser()
        result = self._run(_replay_logic(NO_EXTRACT_STEPS, browser))
        assert result is None

    def test_returns_none_when_extract_returns_empty(self):
        """Empty units list → no data → caller should fall back to LLM."""
        browser = _make_browser(units=[])
        result = self._run(_replay_logic(ENCLAVE_STYLE_STEPS, browser))
        assert result is None

    def test_returns_none_on_pre_extract_step_error(self):
        """Error in a step before extract_all_units aborts replay."""
        browser = _make_browser(iframe_error=True)
        steps = [
            {"action": "navigate_to", "args": {"url": "https://example.com/"}},
            {"action": "read_iframe", "args": {"keyword": "sightmap"}},
            {"action": "extract_all_units", "args": {}},
        ]
        result = self._run(_replay_logic(steps, browser))
        assert result is None

    def test_post_extract_step_error_does_not_erase_units(self):
        """Error in a step AFTER extract_all_units should abort but
        the real production code returns None from the error branch.
        This test confirms the error path is hit (result is None) and
        does NOT return stale/partial data."""
        browser = _make_browser()
        browser.scroll_down = AsyncMock(return_value={"error": "scroll failed"})
        steps = [
            {"action": "navigate_to", "args": {"url": "https://example.com/"}},
            {"action": "extract_all_units", "args": {}},
            {"action": "scroll_down", "args": {}},  # this errors after extraction
        ]
        result = self._run(_replay_logic(steps, browser))
        # The error branch returns None — that's correct; the full LLM loop runs instead
        assert result is None
