"""Unit tests for scraper_agent/fetch.py."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.scraper_agent.fetch import (
    fetch_static,
    has_sufficient_plan_signals,
    is_cloudflare_challenge,
)


# ---------------------------------------------------------------------------
# is_cloudflare_challenge
# ---------------------------------------------------------------------------

class TestIsCloudflareChallenge:
    def test_known_cf_pattern(self):
        html = (
            "<html><head><title>Just a moment...</title></head>"
            "<body>Please wait while we verify cloudflare challenge</body></html>"
        )
        assert is_cloudflare_challenge(html) is True

    def test_cf_chl_marker(self):
        html = "<html><body>cf-chl-widget-x1 some content</body></html>"
        assert is_cloudflare_challenge(html) is True

    def test_cf_bm_cookie_marker(self):
        html = "<html><body>set-cookie: __cf_bm=abc123</body></html>"
        assert is_cloudflare_challenge(html) is True

    def test_normal_apartment_html_false(self):
        html = (
            "<html><head><title>Luxury Apartments San Mateo</title></head>"
            "<body><h1>Floor Plans</h1><p>Studio from $2,500/mo</p></body></html>" * 10
        )
        assert is_cloudflare_challenge(html) is False

    def test_large_html_false(self):
        # Large HTML should return False even if it contains CF markers
        html = "cloudflare __cf_bm just a moment " * 1000
        assert len(html) > 20_000
        assert is_cloudflare_challenge(html) is False

    def test_empty_string_false(self):
        assert is_cloudflare_challenge("") is False

    def test_none_like_empty_false(self):
        assert is_cloudflare_challenge("") is False


# ---------------------------------------------------------------------------
# fetch_static
# ---------------------------------------------------------------------------

class TestFetchStatic:
    def test_returns_html_on_success(self):
        fake_html = "<html><body>Floor Plans</body></html>"

        mock_response = AsyncMock()
        mock_response.text = AsyncMock(return_value=fake_html)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.scraper_agent.fetch.aiohttp.ClientSession",
                   return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_static("https://example.com/floorplans")
            )

        assert result == fake_html

    def test_returns_empty_on_timeout(self):
        import aiohttp as _aiohttp

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=asyncio.TimeoutError())
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.scraper_agent.fetch.aiohttp.ClientSession",
                   return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_static("https://example.com/floorplans")
            )

        assert result == ""

    def test_returns_empty_on_connection_error(self):
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=OSError("connection refused"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.scraper_agent.fetch.aiohttp.ClientSession",
                   return_value=mock_session):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_static("https://example.com/floorplans")
            )

        assert result == ""


# ---------------------------------------------------------------------------
# has_sufficient_plan_signals
# ---------------------------------------------------------------------------

class TestHasSufficientPlanSignals:
    def test_empty_string_false(self):
        assert has_sufficient_plan_signals("") is False

    def test_small_html_false(self):
        assert has_sufficient_plan_signals("<html><body>short</body></html>") is False

    def test_rentcafe_cdn_signal_true(self):
        html = ("x" * 5_001) + 'src="https://cdngeneralmvc.rentcafe.com/js/app.js"'
        assert has_sufficient_plan_signals(html) is True

    def test_rentcafe_api_signal_true(self):
        html = ("x" * 5_001) + "api.rentcafe.com/api/floorplans"
        assert has_sufficient_plan_signals(html) is True

    def test_jonah_digital_signal_true(self):
        html = ("x" * 5_001) + 'class="jd-fp-floorplan-card"'
        assert has_sufficient_plan_signals(html) is True

    def test_fatwin_signal_true(self):
        html = ("x" * 5_001) + "fatwin.com/widget"
        assert has_sufficient_plan_signals(html) is True

    def test_href_hint_true(self):
        html = ("x" * 5_001) + '<a href="/floorplans/studio-a1/">Studio A1</a>'
        assert has_sufficient_plan_signals(html) is True

    def test_bed_dollar_inline_true(self):
        html = ("x" * 5_001) + "$3,200 /mo 2 bed apartment"
        assert has_sufficient_plan_signals(html) is True

    def test_marketing_copy_only_false(self):
        html = (
            "<html><body>"
            + "Experience luxury living. Our community offers resort-style amenities. "
            * 200
            + "</body></html>"
        )
        assert has_sufficient_plan_signals(html) is False


# ---------------------------------------------------------------------------
# fetch_rendered — mock Playwright page
# ---------------------------------------------------------------------------

class TestFetchRendered:
    def test_wait_for_function_called_before_content(self):
        """wait_for_function must be awaited before page.content() is called."""
        from app.services.scraper_agent.fetch import fetch_rendered

        call_order: list[str] = []

        mock_page = MagicMock()
        mock_page.goto = AsyncMock(side_effect=lambda *a, **kw: call_order.append("goto"))
        mock_page.wait_for_function = AsyncMock(
            side_effect=lambda *a, **kw: call_order.append("wait_for_function")
        )
        mock_page.content = AsyncMock(
            side_effect=lambda: call_order.append("content") or "<html>rendered</html>"
        )

        mock_browser = MagicMock()
        mock_browser.page = mock_page

        async def _noop(*a, **kw): pass
        with patch("asyncio.sleep", side_effect=_noop):
            result = asyncio.get_event_loop().run_until_complete(
                fetch_rendered("https://example.com/floorplans", mock_browser)
            )

        assert "goto" in call_order
        assert "wait_for_function" in call_order
        assert "content" in call_order
        # wait_for_function must come before content
        assert call_order.index("wait_for_function") < call_order.index("content")

    def test_returns_empty_on_goto_error(self):
        from app.services.scraper_agent.fetch import fetch_rendered

        mock_page = MagicMock()
        mock_page.goto = AsyncMock(side_effect=Exception("Timeout"))
        mock_browser = MagicMock()
        mock_browser.page = mock_page

        result = asyncio.get_event_loop().run_until_complete(
            fetch_rendered("https://example.com/floorplans", mock_browser)
        )
        assert result == ""
