"""Unit tests for GenericDetailPageAdapter."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "backend"))

from app.services.scraper_agent.platforms.generic_detail import (
    GenericDetailPageAdapter,
    _extract_generic_hrefs,
    _parse_generic_detail,
)


# ---------------------------------------------------------------------------
# _extract_generic_hrefs
# ---------------------------------------------------------------------------

def test_extract_hrefs_floorplans_slug():
    html = """
    <html><body>
      <a href="/floorplans/studio/">Studio</a>
      <a href="/floorplans/one-bed/">1 Bed</a>
      <a href="/about/">About</a>
    </body></html>
    """
    hrefs = _extract_generic_hrefs(html, "https://example.com/")
    assert hrefs == [
        "https://example.com/floorplans/studio/",
        "https://example.com/floorplans/one-bed/",
    ]


def test_extract_hrefs_plans_slug():
    html = """
    <html><body>
      <a href="/plans/a1/">A1</a>
      <a href="/plans/b2/">B2</a>
    </body></html>
    """
    hrefs = _extract_generic_hrefs(html, "https://example.com/")
    assert len(hrefs) == 2
    assert "https://example.com/plans/a1/" in hrefs


def test_extract_hrefs_residences_slug():
    html = """
    <html><body>
      <a href="/residences/penthouse-a/">Penthouse A</a>
      <a href="/residences/garden-suite/">Garden Suite</a>
    </body></html>
    """
    hrefs = _extract_generic_hrefs(html, "https://example.com/")
    assert len(hrefs) == 2


def test_extract_hrefs_plan_subpath():
    """Matches /apartments/lincoln/plan-a1/ style."""
    html = """
    <html><body>
      <a href="/apartments/lincoln/plan-a1/">Plan A1</a>
      <a href="/apartments/lincoln/plan-b2/">Plan B2</a>
      <a href="/apartments/lincoln/">Lincoln</a>
    </body></html>
    """
    hrefs = _extract_generic_hrefs(html, "https://example.com/")
    assert len(hrefs) == 2
    assert all("plan-" in h for h in hrefs)


def test_extract_hrefs_ignores_bare_listing_page():
    """Bare /floorplans/ or /plans/ with no slug must NOT match."""
    html = """
    <html><body>
      <a href="/floorplans/">Floor Plans</a>
      <a href="/plans/">Plans</a>
    </body></html>
    """
    hrefs = _extract_generic_hrefs(html, "https://example.com/")
    assert hrefs == []


def test_extract_hrefs_ignores_tel_mailto():
    html = """
    <html><body>
      <a href="tel:(555) 123-4567">Call</a>
      <a href="mailto:info@example.com">Email</a>
      <a href="/plans/studio/">Studio</a>
    </body></html>
    """
    hrefs = _extract_generic_hrefs(html, "https://example.com/")
    assert hrefs == ["https://example.com/plans/studio/"]


def test_extract_hrefs_deduplicates():
    html = """
    <html><body>
      <a href="/floorplans/studio/">Studio</a>
      <a href="/floorplans/studio/">Studio again</a>
    </body></html>
    """
    hrefs = _extract_generic_hrefs(html, "https://example.com/")
    assert len(hrefs) == 1


# ---------------------------------------------------------------------------
# _parse_generic_detail
# ---------------------------------------------------------------------------

def test_parse_name_from_h1():
    html = """
    <html><head><title>Studio | Example Apts</title></head>
    <body>
      <h1>Studio A</h1>
      <p>1 Bath | 420 sq ft</p>
      <p>From $2,100/mo</p>
    </body></html>
    """
    unit = _parse_generic_detail(html, "https://example.com/floorplans/studio-a/")
    assert unit["plan_name"] == "Studio A"


def test_parse_name_from_title_when_no_h1():
    html = """
    <html><head><title>Plan B2 | Example Apts</title></head>
    <body>
      <p>1 Bedroom | 1 Bath | 650 SF</p>
    </body></html>
    """
    unit = _parse_generic_detail(html, "https://example.com/floorplans/b2/")
    assert unit["plan_name"] == "Plan B2"


def test_parse_name_falls_back_to_slug():
    html = "<html><head><title></title></head><body></body></html>"
    unit = _parse_generic_detail(html, "https://example.com/floorplans/corner-suite/")
    assert unit["plan_name"] == "corner-suite"


def test_parse_name_blacklist_skips_ui_verb_h1():
    """An h1 of 'Tour Now' must be skipped; title segment used instead."""
    html = """
    <html><head><title>Plan A1 | Example Apts</title></head>
    <body>
      <h1>Tour Now</h1>
      <p>1 Bedroom | 1 Bath | 650 SF</p>
    </body></html>
    """
    unit = _parse_generic_detail(html, "https://example.com/floorplans/a1/")
    assert unit["plan_name"] == "Plan A1"


def test_parse_beds_bedroom():
    html = "<html><body><p>2 Bedroom | 2 Bath | 1,050 sq ft</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["bedrooms"] == 2.0


def test_parse_beds_studio():
    html = "<html><body><p>Studio | 1 Bath | 420 sq ft | $2,100</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["bedrooms"] == 0.0


def test_parse_sqft_sq_ft():
    html = "<html><body><p>1 Bedroom | 650 sq ft | $2,800</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["size_sqft"] == 650.0


def test_parse_sqft_SF_notation():
    """FatWin-style 'NNN SF' notation."""
    html = "<html><body><p>1 Bedroom | 1 Bath | 571 SF</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["size_sqft"] == 571.0


def test_parse_sqft_with_comma():
    html = "<html><body><p>2 Bedroom | 1,050 sq. ft.</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["size_sqft"] == 1050.0


def test_parse_price_standard():
    html = "<html><body><p>From $2,300/month</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["price"] == 2300.0


def test_parse_price_range_uses_low_end():
    html = "<html><body><p>$2,100 – $2,450/mo</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["price"] == 2100.0


def test_parse_price_none_when_contact_only():
    html = "<html><body><p>Please contact us for pricing details.</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["price"] is None


def test_parse_price_ignores_out_of_range():
    """Prices outside $500–$20,000 (e.g. deposit, year, square footage) must be ignored."""
    html = "<html><body><p>$100 application fee. Deposit $300. Rent from $2,500/mo.</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["price"] == 2500.0


def test_parse_availability_always_available():
    html = "<html><body><p>1 Bedroom, $2,000/mo</p></body></html>"
    unit = _parse_generic_detail(html, "https://x.com/plans/x/")
    assert unit["availability"] == "available"


# ---------------------------------------------------------------------------
# GenericDetailPageAdapter (detect + extract integration)
# ---------------------------------------------------------------------------

def test_adapter_detect_true_when_sufficient_hrefs():
    html = """
    <html><body>
      <a href="/floorplans/a1/">A1</a>
      <a href="/floorplans/b2/">B2</a>
    </body></html>
    """
    adapter = GenericDetailPageAdapter()
    assert adapter.detect(html, "https://example.com/") is True
    assert len(adapter._hrefs) == 2


def test_adapter_detect_false_when_below_minimum():
    """Only one matching href — should not fire."""
    html = """
    <html><body>
      <a href="/floorplans/a1/">A1</a>
      <a href="/about/">About</a>
    </body></html>
    """
    adapter = GenericDetailPageAdapter()
    assert adapter.detect(html, "https://example.com/") is False


def test_adapter_detect_false_when_empty_html():
    adapter = GenericDetailPageAdapter()
    assert adapter.detect("", "https://example.com/") is False


@pytest.mark.asyncio
async def test_adapter_extract_fetches_and_parses():
    """extract() fetches hrefs cached from detect() and returns parsed units."""
    html_listing = """
    <html><body>
      <a href="/floorplans/studio/">Studio</a>
      <a href="/floorplans/one-bed/">1 Bed</a>
    </body></html>
    """

    detail_pages = {
        "https://example.com/floorplans/studio/": (
            "<html><head><title>Studio | Example</title></head>"
            "<body><h1>Studio S1</h1><p>Studio | 1 Bath | 420 sq ft | $2,100/mo</p></body></html>"
        ),
        "https://example.com/floorplans/one-bed/": (
            "<html><head><title>1 Bed | Example</title></head>"
            "<body><h1>One Bedroom A1</h1><p>1 Bedroom | 1 Bath | 650 sq ft | $2,800/mo</p></body></html>"
        ),
    }

    class _MockResponse:
        def __init__(self, url):
            self.status = 200
            self._url = url

        async def text(self, errors=None):
            return detail_pages[self._url]

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    class _MockSession:
        def get(self, url, **kwargs):
            return _MockResponse(url)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    adapter = GenericDetailPageAdapter()
    adapter.detect(html_listing, "https://example.com/")

    with patch(
        "app.services.scraper_agent.platforms.generic_detail.aiohttp.ClientSession",
        return_value=_MockSession(),
    ):
        units = await adapter.extract(html_listing, "https://example.com/", browser=MagicMock())

    assert len(units) == 2
    names = {u["plan_name"] for u in units}
    assert "Studio S1" in names
    assert "One Bedroom A1" in names

    studio = next(u for u in units if u["plan_name"] == "Studio S1")
    assert studio["bedrooms"] == 0.0
    assert studio["size_sqft"] == 420.0
    assert studio["price"] == 2100.0
