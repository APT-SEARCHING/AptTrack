"""Unit tests for AvalonBayAdapter."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "backend"))

from app.services.scraper_agent.platforms.avalonbay import (
    AvalonBayAdapter,
    _parse_avalon_global_content,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_html(units: list[dict], community_id: str = "AVB-CA999") -> str:
    """Build minimal HTML with Fusion.globalContent."""
    content = {
        "communityId": community_id,
        "name": "Test Avalon",
        "units": units,
    }
    blob = json.dumps(content)
    return (
        f'<html><head>'
        f'<script type="application/javascript">'
        f'window.Fusion=window.Fusion||{{}};Fusion.arcSite="avalon-communities";'
        f'Fusion.globalContent={blob};Fusion.globalContentConfig={{}};'
        f'</script></head><body></body></html>'
    )


def _unit(
    plan_name: str = "A1",
    beds: int = 1,
    baths: int = 1,
    sqft: int = 800,
    price: int = 2500,
    status: str = "VacantAvailable",
    floor: str = "2",
) -> dict:
    return {
        "unitId": f"AVB-CA999-{plan_name}-001",
        "communityId": "AVB-CA999",
        "floorPlan": {"name": plan_name},
        "bedroomNumber": beds,
        "bathroomNumber": baths,
        "squareFeet": sqft,
        "floorNumber": floor,
        "unitStatus": status,
        "startingAtPricesUnfurnished": {
            "prices": {
                "price": price,
                "netEffectivePrice": price,
                "totalPrice": price + 70,
            }
        },
    }


_SAMPLE_HTML = _make_html([
    _unit("796", beds=1, baths=1, sqft=796, price=2820),
    _unit("808", beds=1, baths=1, sqft=808, price=2864),
    _unit("808", beds=1, baths=1, sqft=808, price=2900, floor="3"),  # same plan, higher price
    _unit("1131", beds=2, baths=2, sqft=1131, price=3500),
])


# ---------------------------------------------------------------------------
# _parse_avalon_global_content
# ---------------------------------------------------------------------------

def test_parse_returns_all_units():
    # _SAMPLE_HTML has 4 raw units: 796×1, 808×2, 1131×1
    units = _parse_avalon_global_content(_SAMPLE_HTML)
    names = {u["plan_name"] for u in units}
    assert names == {"796", "808", "1131"}
    assert len(units) == 4


def test_parse_correct_beds_baths_sqft():
    units = _parse_avalon_global_content(_SAMPLE_HTML)
    u808 = next(u for u in units if u["plan_name"] == "808")
    assert u808["bedrooms"] == 1.0
    assert u808["bathrooms"] == 1.0
    assert u808["size_sqft"] == 808


def test_parse_keeps_per_unit_prices():
    """Two units for plan '808' appear as two separate entries with individual prices."""
    units = _parse_avalon_global_content(_SAMPLE_HTML)
    u808_all = [u for u in units if u["plan_name"] == "808"]
    assert len(u808_all) == 2
    prices = sorted(u["price"] for u in u808_all)
    assert prices == [2864.0, 2900.0]


def test_parse_studio_zero_beds():
    html = _make_html([_unit("S1", beds=0, baths=1, sqft=371, price=2100)])
    units = _parse_avalon_global_content(html)
    assert units[0]["bedrooms"] == 0.0


def test_parse_availability_available():
    units = _parse_avalon_global_content(_SAMPLE_HTML)
    for u in units:
        assert u["availability"].startswith("Available")


def test_parse_unavailable_unit_skips_price():
    html = _make_html([_unit("C1", status="Occupied", price=0)])
    units = _parse_avalon_global_content(html)
    assert units[0]["price"] is None
    assert units[0]["availability"] == "unavailable"


def test_parse_occupied_and_available_both_returned():
    """Per-unit: one occupied + one available unit of same plan → two separate entries."""
    html = _make_html([
        _unit("A1", status="Occupied", price=0),
        _unit("A1", status="VacantAvailable", price=2500),
    ])
    units = _parse_avalon_global_content(html)
    assert len(units) == 2
    avail = [u for u in units if u["availability"] != "unavailable"]
    unavail = [u for u in units if u["availability"] == "unavailable"]
    assert len(avail) == 1
    assert avail[0]["price"] == 2500.0
    assert len(unavail) == 1
    assert unavail[0]["price"] is None


def test_parse_returns_empty_when_no_fusion_blob():
    html = "<html><body>nothing here</body></html>"
    assert _parse_avalon_global_content(html) == []


def test_parse_returns_empty_when_units_is_empty_list():
    html = _make_html([])
    assert _parse_avalon_global_content(html) == []


def test_parse_handles_missing_price_gracefully():
    u = _unit("A1", price=0)
    u["startingAtPricesUnfurnished"] = {}
    html = _make_html([u])
    units = _parse_avalon_global_content(html)
    assert units[0]["price"] is None


def test_parse_handles_none_pricing_field():
    u = _unit("A1")
    u["startingAtPricesUnfurnished"] = None
    html = _make_html([u])
    units = _parse_avalon_global_content(html)
    assert units[0]["price"] is None


def test_parse_missing_sqft_stays_none():
    u = _unit("A1")
    u["squareFeet"] = None
    html = _make_html([u])
    units = _parse_avalon_global_content(html)
    assert units[0]["size_sqft"] is None


def test_parse_sqft_per_unit():
    """Per-unit: each unit keeps its own sqft; missing sqft stays None."""
    u1 = _unit("A1")
    u1["squareFeet"] = None
    u2 = _unit("A1", sqft=800, price=2600)
    html = _make_html([u1, u2])
    units = _parse_avalon_global_content(html)
    assert len(units) == 2
    sqfts = {u["size_sqft"] for u in units}
    assert sqfts == {None, 800}


def test_parse_malformed_json_returns_empty():
    html = (
        '<script type="application/javascript">'
        'Fusion.globalContent={broken json;Fusion.next={};'
        '</script>'
    )
    assert _parse_avalon_global_content(html) == []


# ---------------------------------------------------------------------------
# AvalonBayAdapter.detect
# ---------------------------------------------------------------------------

def test_detect_by_url():
    adapter = AvalonBayAdapter()
    assert adapter.detect(_SAMPLE_HTML, "https://www.avaloncommunities.com/ca/test") is True


def test_detect_by_fusion_blob_any_url():
    adapter = AvalonBayAdapter()
    assert adapter.detect(_SAMPLE_HTML, "https://someother.com/") is True


def test_detect_false_on_no_fusion_and_wrong_url():
    adapter = AvalonBayAdapter()
    html = "<html><body>nothing</body></html>"
    assert adapter.detect(html, "https://example.com/") is False


def test_detect_caches_units():
    adapter = AvalonBayAdapter()
    adapter.detect(_SAMPLE_HTML, "https://www.avaloncommunities.com/ca/test")
    assert len(adapter._units) == 4  # 796×1, 808×2, 1131×1


def test_detect_false_when_fusion_blob_has_empty_units():
    """Fusion blob present but zero units → do not claim a match via HTML detection."""
    html = _make_html([])
    adapter = AvalonBayAdapter()
    # URL-based detection still fires
    assert adapter.detect(html, "https://www.avaloncommunities.com/ca/test") is True
    # But HTML-only detection should not fire
    adapter2 = AvalonBayAdapter()
    assert adapter2.detect(html, "https://other.com/") is False


# ---------------------------------------------------------------------------
# AvalonBayAdapter.extract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_returns_plans_no_browser_call():
    """extract() must not call browser — data is already in static HTML."""
    adapter = AvalonBayAdapter()
    adapter.detect(_SAMPLE_HTML, "https://www.avaloncommunities.com/ca/test")

    mock_browser = MagicMock()
    mock_browser.navigate_to = AsyncMock()

    units = await adapter.extract(_SAMPLE_HTML, "https://www.avaloncommunities.com/ca/test", mock_browser)

    assert len(units) == 4  # 796×1, 808×2, 1131×1
    mock_browser.navigate_to.assert_not_called()


@pytest.mark.asyncio
async def test_extract_all_plans_priced():
    adapter = AvalonBayAdapter()
    adapter.detect(_SAMPLE_HTML, "https://www.avaloncommunities.com/ca/test")

    units = await adapter.extract(_SAMPLE_HTML, "https://www.avaloncommunities.com/ca/test", MagicMock())
    assert all(u["price"] is not None for u in units)


@pytest.mark.asyncio
async def test_extract_reparsed_when_detect_not_called():
    """extract() falls back to parsing html argument if detect() wasn't called."""
    adapter = AvalonBayAdapter()  # detect() NOT called
    units = await adapter.extract(_SAMPLE_HTML, "https://www.avaloncommunities.com/ca/test", MagicMock())
    assert len(units) == 4  # 796×1, 808×2, 1131×1


@pytest.mark.asyncio
async def test_extract_empty_when_no_data():
    adapter = AvalonBayAdapter()
    units = await adapter.extract("<html></html>", "https://www.avaloncommunities.com/ca/test", MagicMock())
    assert units == []
