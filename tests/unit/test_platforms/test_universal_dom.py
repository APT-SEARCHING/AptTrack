"""Unit tests for UniversalDOMExtractor."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "backend"))

from app.services.scraper_agent.platforms.universal_dom import (
    UniversalDOMExtractor,
    _find_best_card_group,
    _has_plan_signals,
    _parse_card,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "universal_dom"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(filename: str) -> str:
    return (FIXTURES / filename).read_text()


def _mock_browser() -> MagicMock:
    b = MagicMock()
    b.navigate = AsyncMock()
    return b


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# _has_plan_signals
# ---------------------------------------------------------------------------

def test_signals_all_four():
    text = "Plan A1 — 1 Bed — 1 Bath — 650 sq ft — $2,695/mo"
    assert _has_plan_signals(text) == 4


def test_signals_studio():
    text = "Studio — 1 Bath — 440 sq. ft. — $2,195"
    assert _has_plan_signals(text) == 4


def test_signals_beds_only():
    text = "1 Bedroom with nice views"
    assert _has_plan_signals(text) == 1


def test_signals_none():
    text = "Click here to apply now. Equal Housing Opportunity."
    assert _has_plan_signals(text) == 0


# ---------------------------------------------------------------------------
# _parse_card
# ---------------------------------------------------------------------------

def test_parse_card_standard():
    from bs4 import BeautifulSoup
    html = """
    <div class="plan-card">
      <h3>Plan A2</h3>
      <span>1 Bed</span>
      <span>1 Bath</span>
      <span>680 sq. ft.</span>
      <span>$2,795/mo</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    u = _parse_card(card)
    assert u["plan_name"] == "Plan A2"
    assert u["bedrooms"] == 1.0
    assert u["bathrooms"] == 1.0
    assert u["size_sqft"] == 680
    assert u["price"] == 2795.0


def test_parse_card_studio():
    from bs4 import BeautifulSoup
    html = """
    <div class="plan-card">
      <h3>Studio S1</h3>
      <span>Studio</span>
      <span>1 Bath</span>
      <span>440 sq. ft.</span>
      <span>$2,195/mo</span>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    card = soup.find("div")
    u = _parse_card(card)
    assert u["bedrooms"] == 0.0
    assert u["price"] == 2195.0


def test_parse_card_plan_name_from_h3():
    from bs4 import BeautifulSoup
    html = """
    <div class="plan-card">
      <h3>Plan A2</h3>
      <p>1 Bed 1 Bath 680 sq ft $2,795</p>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    u = _parse_card(soup.find("div"))
    assert u.get("plan_name") == "Plan A2"


def test_parse_card_sqft_with_comma():
    from bs4 import BeautifulSoup
    html = """
    <div class="plan-card">
      <h3>Plan B2</h3>
      <p>2 Beds 2 Baths 1,050 sq. ft. $3,650/mo</p>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    u = _parse_card(soup.find("div"))
    assert u["size_sqft"] == 1050


# ---------------------------------------------------------------------------
# Price range bounds
# ---------------------------------------------------------------------------

def test_price_too_low_rejected():
    from bs4 import BeautifulSoup
    html = """
    <div class="plan-card">
      <h3>Plan X</h3>
      <p>1 Bed 1 Bath 650 sq ft $99/mo</p>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    u = _parse_card(soup.find("div"))
    assert "price" not in u


def test_price_too_high_rejected():
    from bs4 import BeautifulSoup
    html = """
    <div class="plan-card">
      <h3>Plan X</h3>
      <p>1 Bed 1 Bath 650 sq ft $30,000/mo</p>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    u = _parse_card(soup.find("div"))
    assert "price" not in u


def test_price_at_boundary_accepted():
    from bs4 import BeautifulSoup
    html = """
    <div class="plan-card">
      <h3>Plan X</h3>
      <p>1 Bed 1 Bath 650 sq ft $25,000/mo</p>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    u = _parse_card(soup.find("div"))
    assert u.get("price") == 25000.0


# ---------------------------------------------------------------------------
# detect() and extract() — fixture-based
# ---------------------------------------------------------------------------

def test_detect_finds_card_group():
    html = _load("site_with_9_plans_cards.html")
    adapter = UniversalDOMExtractor()
    assert adapter.detect(html, "https://www.theskylyne.com/floor-plans/") is True


def test_extract_returns_at_least_6_units():
    html = _load("site_with_9_plans_cards.html")
    adapter = UniversalDOMExtractor()
    adapter.detect(html, "https://www.theskylyne.com/floor-plans/")
    units = _run(adapter.extract(html, "https://www.theskylyne.com/floor-plans/", _mock_browser()))
    assert len(units) >= 6
    for u in units:
        assert u.get("bedrooms") is not None
        assert u.get("price") is not None


def test_detect_rejects_nav_menu():
    html = _load("site_no_cards_nav_only.html")
    adapter = UniversalDOMExtractor()
    assert adapter.detect(html, "https://example.com/") is False


def test_detect_rejects_empty_html():
    adapter = UniversalDOMExtractor()
    assert adapter.detect("", "https://example.com/") is False


def test_detect_rejects_short_html():
    adapter = UniversalDOMExtractor()
    assert adapter.detect("<html><body>hi</body></html>", "https://example.com/") is False


# ---------------------------------------------------------------------------
# Registry ordering: jonah_digital wins over universal_dom
# ---------------------------------------------------------------------------

def test_jonah_site_specific_adapter_wins():
    """When a Jonah Digital site is encountered, jonah_digital wins — NOT universal_dom.

    try_platforms short-circuits on the first adapter that both detects AND extracts.
    JonahDigitalAdapter is position 0; UniversalDOMExtractor is last.
    Since JonahDigitalAdapter.detect() returns True for the fixture, it fires first.
    Even though universal_dom.detect() would also return True (the cards have plan signals),
    universal_dom.extract() is never called.
    """
    from unittest.mock import patch

    import app.services.scraper_agent.platforms.registry as reg_module

    html = _load("jonah_digital_rendered.html")
    url = "https://www.theryden.com/floorplans"

    # Verify jonah_digital detects the fixture
    from app.services.scraper_agent.platforms.jonah_digital import JonahDigitalAdapter
    assert JonahDigitalAdapter().detect(html, url) is True

    # Verify universal_dom would ALSO detect it (so the ordering test is meaningful)
    assert UniversalDOMExtractor().detect(html, url) is True

    # Now verify that when jonah_digital extract() returns units, universal_dom is never called
    mock_units = [{"plan_name": "Studio S1", "bedrooms": 0, "price": 2250.0}]

    with patch.object(
        reg_module.get_registry()[0],  # JonahDigitalAdapter is first
        "extract",
        new=AsyncMock(return_value=mock_units),
    ):
        result = _run(reg_module.try_platforms(html, url, _mock_browser()))

    assert result is not None
    units, adapter_name = result
    assert adapter_name == "jonah_digital"
    assert units == mock_units


# ---------------------------------------------------------------------------
# Studio detection
# ---------------------------------------------------------------------------

def test_studio_detection_in_fixture():
    html = _load("site_with_9_plans_cards.html")
    adapter = UniversalDOMExtractor()
    units = _run(adapter.extract(html, "https://example.com/", _mock_browser()))
    studios = [u for u in units if u.get("bedrooms") == 0.0]
    assert len(studios) >= 1, "Expected at least one studio unit extracted"


# ---------------------------------------------------------------------------
# Integration test (live network) — skipped by default
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_skylyne_live():
    """Live scrape of Skylyne — universal_dom should extract ≥2 floor plans."""
    import asyncio

    import aiohttp

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    async def _fetch():
        async with aiohttp.ClientSession() as sess:
            async with sess.get(
                "https://www.theskylyne.com/floor-plans/",
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                return await r.text(errors="ignore")

    html = asyncio.get_event_loop().run_until_complete(_fetch())
    adapter = UniversalDOMExtractor()
    assert adapter.detect(html, "https://www.theskylyne.com/floor-plans/")
    units = _run(adapter.extract(html, "https://www.theskylyne.com/floor-plans/", _mock_browser()))
    assert len(units) >= 2, f"Expected ≥2 units from Skylyne live, got {len(units)}"
