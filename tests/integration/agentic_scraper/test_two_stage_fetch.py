"""Integration tests: two-stage fetch (static → rendered).

These tests hit real websites and cost real Playwright time (~30s each).
Tag: @pytest.mark.integration @pytest.mark.slow

Run explicitly:
    pytest tests/integration/agentic_scraper/test_two_stage_fetch.py \
           -m "integration" -s -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tests.integration.agentic_scraper.agent import ApartmentAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_key() -> str:
    key = os.environ.get("MINIMAX_API_KEY", "")
    if not key:
        pytest.skip("MINIMAX_API_KEY not set")
    return key


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.slow
async def test_modesanmateo_rescued_by_rendered_fetch():
    """Mode San Mateo: Cloudflare blocks static fetch → rendered → RentCafe fires.

    Expected: outcome == "platform_direct_rendered", adapter == "rentcafe", plans > 0.
    """
    agent = ApartmentAgent(api_key=_api_key())
    data, metrics = await agent.scrape("https://www.modesanmateo.com/floorplans", headless=True)

    assert data is not None, "Scrape returned None — no data extracted"
    assert len(data.floor_plans) > 0, "No floor plans extracted"
    assert metrics.outcome == "platform_direct_rendered", (
        f"Expected platform_direct_rendered, got {metrics.outcome!r}"
    )
    assert metrics.adapter_name == "rentcafe", (
        f"Expected rentcafe adapter, got {metrics.adapter_name!r}"
    )
    assert metrics.total_cost_usd == 0.0, "platform_direct path should have $0 LLM cost"


@pytest.mark.integration
@pytest.mark.slow
async def test_rentmiro_static_path_unchanged():
    """Miro (Jonah Digital): static HTML has jd-fp-floorplan-card → no rendered upgrade.

    Expected: outcome == "platform_direct_static", adapter == "jonah_digital".
    """
    agent = ApartmentAgent(api_key=_api_key())
    data, metrics = await agent.scrape("https://www.rentmiro.com/floorplans", headless=True)

    assert data is not None
    assert len(data.floor_plans) > 0
    assert metrics.outcome == "platform_direct_static", (
        f"Regression: rentmiro upgraded to rendered — has_sufficient_plan_signals too strict. "
        f"Got outcome={metrics.outcome!r}"
    )
    assert metrics.adapter_name == "jonah_digital"


@pytest.mark.integration
@pytest.mark.slow
async def test_ryden_static_path_unchanged():
    """The Ryden (FatWin): static HTML contains fatwin.com signal → no rendered upgrade."""
    agent = ApartmentAgent(api_key=_api_key())
    data, metrics = await agent.scrape("https://www.theryden.com/floorplans", headless=True)

    assert data is not None
    assert len(data.floor_plans) > 0
    assert metrics.outcome == "platform_direct_static", (
        f"Regression: theryden upgraded to rendered. Got outcome={metrics.outcome!r}"
    )


@pytest.mark.integration
@pytest.mark.slow
async def test_viewpoint_rejected_as_not_apartment():
    """Viewpoint Brighthaven: rendered page contains 'affordable housing' → not_apartment.

    Expected: data is None, metrics.outcome == "not_apartment".
    """
    agent = ApartmentAgent(api_key=_api_key())
    data, metrics = await agent.scrape("https://www.viewpointbrighthaven.com/", headless=True)

    assert metrics.outcome == "not_apartment", (
        f"Expected not_apartment for affordable housing site, got {metrics.outcome!r}"
    )
    # data may be None or have 0 plans — either is acceptable
    if data is not None:
        assert len(data.floor_plans) == 0
