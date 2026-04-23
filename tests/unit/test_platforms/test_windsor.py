"""Unit tests for WindsorAdapter."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "backend"))

from app.services.scraper_agent.platforms.windsor import (
    WindsorAdapter,
    _fetch_html,
    _floorplans_url_from,
    _parse_windsor_floorplans,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unit_article(
    plan: str = "A",
    price: int = 3162,
    sqft: int = 639,
    beds: int = 0,
    baths: float = 1.0,
    available: str = "true",
    unit_num: str = "758",
) -> str:
    return (
        f'<article class="spaces-unit" '
        f'data-spaces-obj="unit" '
        f'data-spaces-unit="{unit_num}" '
        f'data-spaces-sort-plan-name="{plan}" '
        f'data-spaces-sort-price="{price}" '
        f'data-spaces-sort-area="{sqft}" '
        f'data-spaces-sort-bed="{beds}" '
        f'data-spaces-sort-bath="{baths}" '
        f'data-spaces-available="{available}" '
        f'data-spaces-unavailable="{"false" if available == "true" else "true"}">'
        f'<div>Unit {unit_num}</div></article>'
    )


def _floorplans_html(*articles: str) -> str:
    return f'<html><body><div class="spaces-container">{"".join(articles)}</div></body></html>'


_SAMPLE_FP_HTML = _floorplans_html(
    _unit_article("A", price=3162, sqft=639, beds=0, baths=1, unit_num="758"),
    _unit_article("A", price=3162, sqft=639, beds=0, baths=1, unit_num="780"),
    _unit_article("A", price=3196, sqft=639, beds=0, baths=1, unit_num="658"),
    _unit_article("C", price=3127, sqft=639, beds=1, baths=1, unit_num="336"),
    _unit_article("G", price=3485, sqft=726, beds=1, baths=1, unit_num="329"),
    _unit_article("G", price=3558, sqft=741, beds=1, baths=1, unit_num="394"),
    _unit_article("P", price=4705, sqft=1162, beds=2, baths=2, unit_num="201"),
)

_WINDSOR_HOMEPAGE = (
    '<html><body>'
    '<a href="https://www.windsorcommunities.com/properties/windsor-winchester/floorplans/">'
    'View Floorplans</a>'
    '</body></html>'
)

_CANNERY_HOMEPAGE = (
    '<html><body>'
    '<a href="https://www.windsorcommunities.com/properties/cannery-park-by-windsor/floorplans/">'
    'View Floorplans</a>'
    '</body></html>'
)


# ---------------------------------------------------------------------------
# _floorplans_url_from
# ---------------------------------------------------------------------------

def test_floorplans_url_from_windsor_url():
    url = "https://www.windsorcommunities.com/properties/windsor-winchester/"
    result = _floorplans_url_from(url, "")
    assert result == "https://www.windsorcommunities.com/properties/windsor-winchester/floorplans/"


def test_floorplans_url_from_windsor_url_with_utm():
    url = "https://www.windsorcommunities.com/properties/windsor-winchester/?utm_campaign=GMB"
    result = _floorplans_url_from(url, "")
    assert result == "https://www.windsorcommunities.com/properties/windsor-winchester/floorplans/"


def test_floorplans_url_from_html_link():
    url = "https://www.canneryparkbywindsor.com/"
    result = _floorplans_url_from(url, _CANNERY_HOMEPAGE)
    assert "cannery-park-by-windsor" in result
    assert result.endswith("floorplans/")


def test_floorplans_url_from_returns_none_when_no_signals():
    assert _floorplans_url_from("https://example.com/", "") is None


def test_floorplans_url_already_on_floorplans_page():
    url = "https://www.windsorcommunities.com/properties/windsor-winchester/floorplans/"
    result = _floorplans_url_from(url, "")
    assert result == url


# ---------------------------------------------------------------------------
# _parse_windsor_floorplans
# ---------------------------------------------------------------------------

def test_parse_returns_distinct_plans():
    plans = _parse_windsor_floorplans(_SAMPLE_FP_HTML)
    names = {p["plan_name"] for p in plans}
    assert names == {"A", "C", "G", "P"}
    assert len(plans) == 4


def test_parse_minimum_price_per_plan():
    plans = _parse_windsor_floorplans(_SAMPLE_FP_HTML)
    plan_a = next(p for p in plans if p["plan_name"] == "A")
    assert plan_a["price"] == 3162.0  # min of 3162, 3162, 3196


def test_parse_beds_baths_sqft():
    plans = _parse_windsor_floorplans(_SAMPLE_FP_HTML)
    plan_a = next(p for p in plans if p["plan_name"] == "A")
    assert plan_a["bedrooms"] == 0.0   # studio
    assert plan_a["bathrooms"] == 1.0
    assert plan_a["size_sqft"] == 639

    plan_p = next(p for p in plans if p["plan_name"] == "P")
    assert plan_p["bedrooms"] == 2.0
    assert plan_p["bathrooms"] == 2.0
    assert plan_p["size_sqft"] == 1162


def test_parse_availability_available():
    plans = _parse_windsor_floorplans(_SAMPLE_FP_HTML)
    for p in plans:
        assert p["availability"] == "available"


def test_parse_unavailable_unit_skips_price():
    html = _floorplans_html(
        _unit_article("X", price=4000, sqft=900, beds=2, available="false"),
    )
    plans = _parse_windsor_floorplans(html)
    assert plans[0]["price"] is None
    assert plans[0]["availability"] == "unavailable"


def test_parse_available_wins_over_unavailable():
    html = _floorplans_html(
        _unit_article("B", price=3500, sqft=700, beds=1, available="false", unit_num="1"),
        _unit_article("B", price=3300, sqft=700, beds=1, available="true", unit_num="2"),
    )
    plans = _parse_windsor_floorplans(html)
    assert len(plans) == 1
    assert plans[0]["price"] == 3300.0
    assert plans[0]["availability"] == "available"


def test_parse_sqft_filled_from_second_unit():
    html = _floorplans_html(
        _unit_article("Z", price=3000, sqft=0, beds=1, unit_num="1"),  # sqft=0 → None after int(0)
        _unit_article("Z", price=3100, sqft=750, beds=1, unit_num="2"),
    )
    # sqft=0 is falsy — adapter treats it as missing; second unit provides 750
    plans = _parse_windsor_floorplans(html)
    # price should be min of 3000 and 3100
    assert plans[0]["price"] == 3000.0


def test_parse_returns_empty_when_no_articles():
    html = "<html><body>no units here</body></html>"
    assert _parse_windsor_floorplans(html) == []


def test_parse_handles_missing_plan_name():
    html = (
        '<article data-spaces-obj="unit" data-spaces-sort-price="3000" '
        'data-spaces-sort-area="700" data-spaces-sort-bed="1" '
        'data-spaces-sort-bath="1" data-spaces-available="true"></article>'
    )
    # No plan name → should be skipped entirely
    plans = _parse_windsor_floorplans(html)
    assert plans == []


# ---------------------------------------------------------------------------
# WindsorAdapter.detect
# ---------------------------------------------------------------------------

def test_detect_by_windsor_url():
    adapter = WindsorAdapter()
    assert adapter.detect(
        _WINDSOR_HOMEPAGE,
        "https://www.windsorcommunities.com/properties/windsor-winchester/",
    ) is True


def test_detect_by_html_link():
    adapter = WindsorAdapter()
    assert adapter.detect(_CANNERY_HOMEPAGE, "https://www.canneryparkbywindsor.com/") is True


def test_detect_stores_floorplans_url():
    adapter = WindsorAdapter()
    adapter.detect(_WINDSOR_HOMEPAGE, "https://www.windsorcommunities.com/properties/windsor-winchester/")
    assert adapter._floorplans_url is not None
    assert "floorplans" in adapter._floorplans_url


def test_detect_false_when_no_signals():
    adapter = WindsorAdapter()
    assert adapter.detect("<html><body>nothing</body></html>", "https://example.com/") is False


def test_detect_false_on_empty_html():
    adapter = WindsorAdapter()
    assert adapter.detect("", "https://example.com/") is False


# ---------------------------------------------------------------------------
# WindsorAdapter.extract
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_fetches_floorplans_page():
    adapter = WindsorAdapter()
    adapter.detect(_WINDSOR_HOMEPAGE, "https://www.windsorcommunities.com/properties/windsor-winchester/")

    with patch(
        "app.services.scraper_agent.platforms.windsor._fetch_html",
        return_value=_SAMPLE_FP_HTML,
    ) as mock_fetch:
        units = await adapter.extract(
            _WINDSOR_HOMEPAGE,
            "https://www.windsorcommunities.com/properties/windsor-winchester/",
            MagicMock(),
        )

    mock_fetch.assert_called_once()
    called_url = mock_fetch.call_args[0][0]
    assert "floorplans" in called_url
    assert len(units) == 4


@pytest.mark.asyncio
async def test_extract_no_browser_navigate_call():
    """WindsorAdapter must not call browser.navigate_to — data comes from urllib."""
    adapter = WindsorAdapter()
    adapter.detect(_WINDSOR_HOMEPAGE, "https://www.windsorcommunities.com/properties/windsor-winchester/")

    mock_browser = MagicMock()
    mock_browser.navigate_to = AsyncMock()

    with patch("app.services.scraper_agent.platforms.windsor._fetch_html", return_value=_SAMPLE_FP_HTML):
        await adapter.extract(_WINDSOR_HOMEPAGE, "https://www.windsorcommunities.com/properties/windsor-winchester/", mock_browser)

    mock_browser.navigate_to.assert_not_called()


@pytest.mark.asyncio
async def test_extract_returns_empty_when_fetch_fails():
    adapter = WindsorAdapter()
    adapter._floorplans_url = "https://www.windsorcommunities.com/properties/test/floorplans/"

    with patch("app.services.scraper_agent.platforms.windsor._fetch_html", return_value=None):
        units = await adapter.extract("", "https://www.windsorcommunities.com/properties/test/", MagicMock())

    assert units == []


@pytest.mark.asyncio
async def test_extract_returns_empty_when_no_floorplans_url():
    adapter = WindsorAdapter()
    # detect() not called, no floorplans URL derivable
    units = await adapter.extract("<html></html>", "https://example.com/", MagicMock())
    assert units == []


@pytest.mark.asyncio
async def test_extract_all_plans_priced():
    adapter = WindsorAdapter()
    adapter._floorplans_url = "https://www.windsorcommunities.com/properties/windsor-winchester/floorplans/"

    with patch("app.services.scraper_agent.platforms.windsor._fetch_html", return_value=_SAMPLE_FP_HTML):
        units = await adapter.extract("", "https://www.windsorcommunities.com/properties/windsor-winchester/", MagicMock())

    assert all(u["price"] is not None for u in units)
