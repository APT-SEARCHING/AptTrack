"""Unit tests for GreystarAdapter."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "backend"))

from app.services.scraper_agent.platforms.greystar import (
    GreystarAdapter,
    _merge_prices_from_rendered,
    _parse_greystar_jsonld,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_jsonld_html(plans: list[dict], extra_fields: dict | None = None) -> str:
    """Build minimal HTML with a LodgingBusiness JSON-LD block."""
    lodging = {
        "@context": "https://schema.org",
        "@type": "LodgingBusiness",
        "identifier": "12342",
        "name": "Test Apartments",
        **(extra_fields or {}),
        "containsPlace": [
            {
                "@type": "Accommodation",
                "identifier": str(100 + i),
                "name": p["name"],
                "numberOfBedrooms": p.get("beds", 1),
                "numberOfBathroomsTotal": p.get("baths", 1),
            }
            for i, p in enumerate(plans)
        ],
    }
    return (
        f'<html><head>'
        f'<script type="application/ld+json">{json.dumps(lodging)}</script>'
        f'</head><body></body></html>'
    )


_SAMPLE_PLANS = [
    {"name": "A1", "beds": 1, "baths": 1},
    {"name": "B1", "beds": 2, "baths": 2},
    {"name": "E1", "beds": 0, "baths": 1},
]

_SAMPLE_HTML = _make_jsonld_html(_SAMPLE_PLANS)


# ---------------------------------------------------------------------------
# _parse_greystar_jsonld
# ---------------------------------------------------------------------------

def test_parse_jsonld_extracts_all_plans():
    units = _parse_greystar_jsonld(_SAMPLE_HTML)
    assert len(units) == 3
    names = {u["plan_name"] for u in units}
    assert names == {"A1", "B1", "E1"}


def test_parse_jsonld_beds_baths():
    units = _parse_greystar_jsonld(_SAMPLE_HTML)
    a1 = next(u for u in units if u["plan_name"] == "A1")
    assert a1["bedrooms"] == 1.0
    assert a1["bathrooms"] == 1.0

    e1 = next(u for u in units if u["plan_name"] == "E1")
    assert e1["bedrooms"] == 0.0  # studio


def test_parse_jsonld_price_and_sqft_are_none():
    units = _parse_greystar_jsonld(_SAMPLE_HTML)
    for u in units:
        assert u["price"] is None
        assert u["size_sqft"] is None


def test_parse_jsonld_returns_empty_when_no_script():
    assert _parse_greystar_jsonld("<html><body>no script</body></html>") == []


def test_parse_jsonld_returns_empty_on_wrong_type():
    html = '<html><head><script type="application/ld+json">{"@type":"Person"}</script></head></html>'
    assert _parse_greystar_jsonld(html) == []


def test_parse_jsonld_skips_non_accommodation_places():
    lodging = {
        "@context": "https://schema.org",
        "@type": "LodgingBusiness",
        "containsPlace": [
            {"@type": "Accommodation", "identifier": "1", "name": "A1",
             "numberOfBedrooms": 1, "numberOfBathroomsTotal": 1},
            {"@type": "Room", "name": "Conference Room"},   # should be skipped
        ],
    }
    html = f'<html><head><script type="application/ld+json">{json.dumps(lodging)}</script></head></html>'
    units = _parse_greystar_jsonld(html)
    assert len(units) == 1
    assert units[0]["plan_name"] == "A1"


def test_parse_jsonld_all_availability_available():
    units = _parse_greystar_jsonld(_SAMPLE_HTML)
    for u in units:
        assert u["availability"] == "available"


# ---------------------------------------------------------------------------
# _merge_prices_from_rendered
# ---------------------------------------------------------------------------

def _base_units() -> list[dict]:
    return [
        {"plan_name": "A1", "bedrooms": 1.0, "bathrooms": 1.0,
         "size_sqft": None, "price": None, "availability": "available"},
        {"plan_name": "B1", "bedrooms": 2.0, "bathrooms": 2.0,
         "size_sqft": None, "price": None, "availability": "available"},
    ]


def test_merge_prices_named_card_match():
    rendered = """
    <html><body>
      <div class="floorplan-card">
        <h3>A1</h3><p>$2,300/mo</p>
      </div>
      <div class="floorplan-card">
        <h3>B1</h3><p>$3,100/mo</p>
      </div>
    </body></html>
    """
    units = _merge_prices_from_rendered(_base_units(), rendered)
    a1 = next(u for u in units if u["plan_name"] == "A1")
    b1 = next(u for u in units if u["plan_name"] == "B1")
    assert a1["price"] == 2300.0
    assert b1["price"] == 3100.0


def test_merge_prices_range_uses_low_end():
    rendered = "<html><body>A1 $2,100 – $2,450/mo B1 $3,000/mo</body></html>"
    units = _merge_prices_from_rendered(_base_units(), rendered)
    a1 = next(u for u in units if u["plan_name"] == "A1")
    assert a1["price"] == 2100.0


def test_merge_prices_global_harvest_fallback():
    """When no plan name is found near a price, harvested prices are distributed in order."""
    rendered = "<html><body><p>From $2,200/mo</p><p>From $3,000/mo</p></body></html>"
    units = _merge_prices_from_rendered(_base_units(), rendered)
    prices = [u["price"] for u in units]
    assert prices[0] == 2200.0
    assert prices[1] == 3000.0


def test_merge_prices_ignores_out_of_range():
    rendered = "<html><body>A1 $50 deposit $2,500/mo</body></html>"
    units = _merge_prices_from_rendered(_base_units()[:1], rendered)
    assert units[0]["price"] == 2500.0


def test_merge_prices_no_prices_found_leaves_none():
    rendered = "<html><body>A1 Contact us for pricing</body></html>"
    units = _merge_prices_from_rendered(_base_units()[:1], rendered)
    assert units[0]["price"] is None


def test_merge_prices_sqft_stays_none():
    """Greystar does not expose sqft — size_sqft must remain None."""
    rendered = "<html><body>A1 $2,300/mo</body></html>"
    units = _merge_prices_from_rendered(_base_units()[:1], rendered)
    assert units[0]["size_sqft"] is None


# ---------------------------------------------------------------------------
# GreystarAdapter.detect
# ---------------------------------------------------------------------------

def test_detect_by_url():
    adapter = GreystarAdapter()
    assert adapter.detect(
        _SAMPLE_HTML,
        "https://www.greystar.com/properties/san-jose-ca/test/floorplans",
    ) is True


def test_detect_by_jsonld_any_url():
    adapter = GreystarAdapter()
    assert adapter.detect(_SAMPLE_HTML, "https://example.com/floorplans") is True


def test_detect_caches_static_units():
    adapter = GreystarAdapter()
    adapter.detect(_SAMPLE_HTML, "https://www.greystar.com/properties/test/floorplans")
    assert len(adapter._static_units) == 3


def test_detect_false_when_no_jsonld_and_wrong_url():
    adapter = GreystarAdapter()
    assert adapter.detect("<html><body>just html</body></html>", "https://notgreystar.com/") is False


def test_detect_false_when_empty_html():
    adapter = GreystarAdapter()
    assert adapter.detect("", "https://notgreystar.com/") is False


# ---------------------------------------------------------------------------
# GreystarAdapter.extract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_returns_static_plans_when_playwright_fails():
    """Even if Playwright navigation errors, JSON-LD plans are returned."""
    adapter = GreystarAdapter()
    adapter.detect(_SAMPLE_HTML, "https://www.greystar.com/properties/test/floorplans")

    mock_browser = MagicMock()
    mock_browser.navigate_to = AsyncMock(return_value={"error": "connection refused"})

    units = await adapter.extract(
        _SAMPLE_HTML,
        "https://www.greystar.com/properties/test/floorplans",
        browser=mock_browser,
    )
    assert len(units) == 3
    assert all(u["price"] is None for u in units)


@pytest.mark.asyncio
async def test_extract_merges_prices_from_playwright():
    adapter = GreystarAdapter()
    adapter.detect(_SAMPLE_HTML, "https://www.greystar.com/properties/test/floorplans")

    rendered_html = """
    <html><body>
      <div>A1</div><div>$2,300/mo</div>
      <div>B1</div><div>$3,100/mo</div>
      <div>E1</div><div>$1,900/mo</div>
    </body></html>
    """

    mock_page = MagicMock()
    mock_page.wait_for_function = AsyncMock()
    mock_page.content = AsyncMock(return_value=rendered_html)

    mock_browser = MagicMock()
    mock_browser.navigate_to = AsyncMock(return_value={"url": "https://www.greystar.com/..."})
    mock_browser.page = mock_page

    with patch("asyncio.sleep", new_callable=AsyncMock):
        units = await adapter.extract(
            _SAMPLE_HTML,
            "https://www.greystar.com/properties/test/floorplans",
            browser=mock_browser,
        )

    assert len(units) == 3
    priced = [u for u in units if u["price"] is not None]
    assert len(priced) == 3


@pytest.mark.asyncio
async def test_extract_returns_empty_when_no_static_units_and_no_jsonld():
    adapter = GreystarAdapter()
    # detect() never called — _static_units is empty, html has no JSON-LD
    units = await adapter.extract(
        "<html><body></body></html>",
        "https://www.greystar.com/properties/test/floorplans",
        browser=MagicMock(),
    )
    assert units == []
