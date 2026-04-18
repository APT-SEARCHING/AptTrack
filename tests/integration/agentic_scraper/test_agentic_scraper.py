"""Tests for the agentic apartment scraper.

Unit tests (no marker) mock all network and browser I/O — they run anywhere.
Integration tests (@pytest.mark.integration) require:
  - MINIMAX_API_KEY env var
  - A live internet connection
  - `playwright install chromium` to have been run

Run unit tests only:
    pytest tests/integration/agentic_scraper/ -m "not integration"

Run integration tests:
    MINIMAX_API_KEY=sk-... pytest tests/integration/agentic_scraper/ -m integration -v -s
"""

import json
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from dotenv import load_dotenv

from .agent import ApartmentAgent
from .browser_tools import BrowserSession
from .models import ApartmentData, FloorPlan

# Load .env so MINIMAX_API_KEY is available for integration tests
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")


# ---------------------------------------------------------------------------
# Helpers to build mock LLM responses
# ---------------------------------------------------------------------------


def _tool_call_response(tool_name: str, tool_args: dict, call_id: str = "call_1") -> MagicMock:
    """Build a mock chat-completion response that issues one tool call."""
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = tool_name
    tc.function.arguments = json.dumps(tool_args)

    msg = MagicMock()
    msg.content = None
    msg.tool_calls = [tc]

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "tool_calls"

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


def _stop_response(content: str = "Done.") -> MagicMock:
    """Build a mock response with no tool calls (agent chose to stop)."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None

    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = "stop"

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = None
    return resp


# ---------------------------------------------------------------------------
# Fake browser session for unit tests
# ---------------------------------------------------------------------------

FAKE_PAGE_STATE = {
    "url": "https://example-apts.com/floorplans",
    "text": (
        "Example Apartments\n"
        "123 Main St, San Jose, CA 95101\n"
        "(408) 555-0100\n\n"
        "Studio — 450 sq ft — $1,800/mo — Available Now\n"
        "1 Bed / 1 Bath — 650 sq ft — $2,200/mo — Available Now\n"
        "2 Bed / 2 Bath — 950 sq ft — $3,100 - $3,400/mo — Available Jun 2025\n"
    ),
    "links": [
        {"text": "Floor Plans", "href": "/floorplans"},
        {"text": "Contact Us", "href": "/contact"},
    ],
    "buttons": ["Studio", "1 Bedroom", "2 Bedroom"],
}


class FakeBrowserSession:
    """Drop-in replacement for BrowserSession that never touches the network."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    async def __aenter__(self) -> "FakeBrowserSession":
        return self

    async def __aexit__(self, *_) -> None:
        pass

    async def navigate_to(self, url: str) -> dict:
        return {**FAKE_PAGE_STATE, "url": url}

    async def read_iframe(self, keyword: str) -> dict:
        return {**FAKE_PAGE_STATE, "active_frame": f"https://fake-iframe.com/{keyword}"}

    async def extract_all_units(self) -> dict:
        return {
            "units": [
                {"unit_number": "A101", "plan_name": "Studio", "bedrooms": 0, "bathrooms": 1, "size_sqft": 450, "price": 1800, "availability": "Available Now"},
                {"unit_number": "B205", "plan_name": "1 Bed/1 Bath", "bedrooms": 1, "bathrooms": 1, "size_sqft": 650, "price": 2200, "availability": "Available Now"},
            ],
            "total": 2,
        }

    async def click_link(self, text_or_href: str) -> dict:
        return FAKE_PAGE_STATE

    async def click_button(self, text: str) -> dict:
        return FAKE_PAGE_STATE

    async def scroll_down(self) -> dict:
        return FAKE_PAGE_STATE


# ---------------------------------------------------------------------------
# Unit: model validation
# ---------------------------------------------------------------------------


class TestModels:
    def test_floor_plan_minimal(self):
        plan = FloorPlan(name="Studio")
        assert plan.name == "Studio"
        assert plan.bedrooms is None
        assert plan.min_price is None

    def test_floor_plan_full(self):
        plan = FloorPlan(
            name="1 Bed/1 Bath",
            bedrooms=1,
            bathrooms=1,
            size_sqft=650,
            min_price=2200,
            max_price=2400,
            availability="Available Now",
        )
        assert plan.bedrooms == 1
        assert plan.min_price == 2200

    def test_apartment_data_defaults(self):
        apt = ApartmentData(name="Example Apts")
        assert apt.floor_plans == []
        assert apt.address is None

    def test_apartment_data_with_plans(self):
        apt = ApartmentData(
            name="Example Apts",
            address="123 Main St",
            floor_plans=[
                FloorPlan(name="Studio", min_price=1800),
                FloorPlan(name="1BR", min_price=2200, max_price=2400),
            ],
        )
        assert len(apt.floor_plans) == 2
        assert apt.floor_plans[0].min_price == 1800


# ---------------------------------------------------------------------------
# Unit: agent — single iteration submit
# ---------------------------------------------------------------------------


class TestAgentUnit:
    @pytest.mark.asyncio
    async def test_agent_calls_submit_on_first_response(self):
        """Agent calls submit_findings immediately and returns ApartmentData."""
        submit_args = {
            "name": "Example Apartments",
            "address": "123 Main St",
            "floor_plans": [
                {"name": "Studio", "bedrooms": 0, "size_sqft": 450, "min_price": 1800, "max_price": 1800},
                {"name": "1 Bed/1 Bath", "bedrooms": 1, "size_sqft": 650, "min_price": 2200, "max_price": 2200},
            ],
        }
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_tool_call_response("submit_findings", submit_args)
        )

        agent = ApartmentAgent(_client=mock_client, _browser_class=FakeBrowserSession)
        result, _ = await agent.scrape("https://example-apts.com")

        assert result is not None
        assert result.name == "Example Apartments"
        assert len(result.floor_plans) == 2
        assert result.floor_plans[0].min_price == 1800

    @pytest.mark.asyncio
    async def test_agent_navigates_then_submits(self):
        """Agent calls navigate_to first, then submit_findings."""
        submit_args = {
            "name": "Miro Apartments",
            "address": "160 W Santa Clara St",
            "floor_plans": [
                {"name": "Studio", "bedrooms": 0, "min_price": 2500},
                {"name": "1BR", "bedrooms": 1, "min_price": 3100},
            ],
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _tool_call_response("navigate_to", {"url": "https://example.com/floorplans"}, call_id="call_1"),
                _tool_call_response("submit_findings", submit_args, call_id="call_2"),
            ]
        )

        agent = ApartmentAgent(_client=mock_client, _browser_class=FakeBrowserSession)
        result, _ = await agent.scrape("https://example.com")

        assert result is not None
        assert result.name == "Miro Apartments"
        assert len(result.floor_plans) == 2
        # navigate_to was called once
        assert mock_client.chat.completions.create.call_count == 2

    @pytest.mark.asyncio
    async def test_agent_full_navigation_flow(self):
        """Agent navigates, clicks a link, scrolls, then submits."""
        submit_args = {
            "name": "Diridon West",
            "floor_plans": [
                {"name": "Studio", "min_price": 2300},
                {"name": "1 Bed", "min_price": 2800},
                {"name": "2 Bed", "min_price": 3500},
            ],
        }
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _tool_call_response("navigate_to", {"url": "https://diridonwest.com"}, "c1"),
                _tool_call_response("click_link", {"text_or_href": "Floor Plans"}, "c2"),
                _tool_call_response("scroll_down", {}, "c3"),
                _tool_call_response("submit_findings", submit_args, "c4"),
            ]
        )

        agent = ApartmentAgent(_client=mock_client, _browser_class=FakeBrowserSession)
        result, _ = await agent.scrape("https://diridonwest.com")

        assert result is not None
        assert result.name == "Diridon West"
        assert len(result.floor_plans) == 3

    @pytest.mark.asyncio
    async def test_agent_returns_none_when_no_submit(self):
        """Agent exhausts iterations without calling submit_findings → returns None."""
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_stop_response("I could not find any pricing information.")
        )

        agent = ApartmentAgent(_client=mock_client, _browser_class=FakeBrowserSession)
        result, _ = await agent.scrape("https://example.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_agent_handles_malformed_submit_args_gracefully(self):
        """submit_findings with missing required field logs warning and returns None."""
        # 'name' is required by ApartmentData; omit it to trigger validation error
        bad_args = {"floor_plans": [{"name": "Studio"}]}
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_tool_call_response("submit_findings", bad_args)
        )

        agent = ApartmentAgent(_client=mock_client, _browser_class=FakeBrowserSession)
        result, _ = await agent.scrape("https://example.com")

        # Pydantic validation fails — agent returns None rather than crashing
        assert result is None

    @pytest.mark.asyncio
    async def test_agent_handles_unknown_tool_gracefully(self):
        """Unknown tool name is handled without raising an exception."""
        submit_args = {"name": "Example", "floor_plans": [{"name": "1BR", "min_price": 2000}]}
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[
                _tool_call_response("fly_to_moon", {"destination": "moon"}, "c1"),
                _tool_call_response("submit_findings", submit_args, "c2"),
            ]
        )

        agent = ApartmentAgent(_client=mock_client, _browser_class=FakeBrowserSession)
        result, _ = await agent.scrape("https://example.com")

        assert result is not None
        assert result.name == "Example"


# ---------------------------------------------------------------------------
# Unit: browser tools (no network)
# ---------------------------------------------------------------------------


class TestBrowserToolsUnit:
    def test_fake_browser_navigate_returns_dict(self):
        """FakeBrowserSession.navigate_to returns expected keys."""
        import asyncio

        async def _run():
            async with FakeBrowserSession() as b:
                state = await b.navigate_to("https://x.com")
            return state

        state = asyncio.get_event_loop().run_until_complete(_run())
        assert "url" in state
        assert "text" in state
        assert "links" in state
        assert "buttons" in state

    def test_floor_plan_price_parsing(self):
        """Verify price min/max logic on the model layer."""
        plan = FloorPlan(name="2BR", min_price=3100, max_price=3400)
        assert plan.min_price < plan.max_price

    def test_studio_bedroom_count(self):
        plan = FloorPlan(name="Studio", bedrooms=0)
        assert plan.bedrooms == 0

    def test_floor_plan_external_url_defaults_to_none(self):
        """external_url is optional and defaults to None."""
        plan = FloorPlan(name="Studio")
        assert plan.external_url is None

    def test_floor_plan_external_url_preserved(self):
        """external_url is stored when provided."""
        plan = FloorPlan(name="Plan A", external_url="https://example.com/plans?id=A1")
        assert plan.external_url == "https://example.com/plans?id=A1"

    @pytest.mark.asyncio
    async def test_agent_passes_external_url_through(self):
        """Agent returns external_url from submit_findings in the FloorPlan."""
        submit_args = {
            "name": "Deep Link Apts",
            "floor_plans": [
                {
                    "name": "Studio S1",
                    "bedrooms": 0,
                    "min_price": 2100,
                    "max_price": 2100,
                    "external_url": "https://deeplinkapts.com/floor-plans?id=S1",
                },
                {
                    "name": "1BR A1",
                    "bedrooms": 1,
                    "min_price": 2800,
                    "max_price": 2800,
                    # no external_url — should be None
                },
            ],
        }
        mock_client = MagicMock()
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_tool_call_response("submit_findings", submit_args)
        )

        agent = ApartmentAgent(_client=mock_client, _browser_class=FakeBrowserSession)
        result, _ = await agent.scrape("https://deeplinkapts.com")

        assert result is not None
        assert result.floor_plans[0].external_url == "https://deeplinkapts.com/floor-plans?id=S1"
        assert result.floor_plans[1].external_url is None


# ---------------------------------------------------------------------------
# Unit: Jonah Digital parser
# ---------------------------------------------------------------------------

_JD_LISTING_HTML = """
<html><body>
  <a class="jd-fp-floorplan-card jd-fp-floorplan-card--preload" href="/floorplans/a01/">Plan A</a>
  <a class="jd-fp-floorplan-card jd-fp-floorplan-card--preload" href="/floorplans/b01/">Plan B</a>
  <a href="/about/">About</a>
</body></html>
"""

_JD_DETAIL_WITH_PRICE = """
<html><body>
  <h1>Plan A</h1>
  <p>1 Bedroom | 669 sq. ft.</p>
  <p>Starting at $2,675/mo</p>
</body></html>
"""

_JD_DETAIL_NO_PRICE = """
<html><body>
  <h1>Plan B</h1>
  <p>Studio | 543 sq. ft.</p>
  <p>Contact Us for Pricing</p>
</body></html>
"""

_JD_DETAIL_RANGE_PRICE = """
<html><body>
  <h1>Peak Meadow</h1>
  <p>2 Bedrooms | 702 sq. ft.</p>
  <p>$3,936 - $4,141/mo</p>
</body></html>
"""


class TestJonahDigital:
    """Unit tests for the Jonah Digital static-HTML parser."""

    def test_is_jonah_digital_positive(self):
        from browser_tools import _is_jonah_digital
        assert _is_jonah_digital(_JD_LISTING_HTML) is True

    def test_is_jonah_digital_negative(self):
        from browser_tools import _is_jonah_digital
        assert _is_jonah_digital("<html><body><p>Hello</p></body></html>") is False

    def test_extract_hrefs_absolute(self):
        from browser_tools import _extract_jonah_digital_hrefs
        hrefs = _extract_jonah_digital_hrefs(_JD_LISTING_HTML, "https://legacyhayward.com/floor-plans/")
        assert len(hrefs) == 2
        assert "https://legacyhayward.com/floorplans/a01/" in hrefs
        assert "https://legacyhayward.com/floorplans/b01/" in hrefs
        # Non-JD link excluded
        assert not any("about" in h for h in hrefs)

    def test_extract_hrefs_deduplication(self):
        from browser_tools import _extract_jonah_digital_hrefs
        html = """
        <a class="jd-fp-floorplan-card" href="/floorplans/a01/"></a>
        <a class="jd-fp-floorplan-card" href="/floorplans/a01/"></a>
        """
        hrefs = _extract_jonah_digital_hrefs(html, "https://example.com")
        assert len(hrefs) == 1

    def test_extract_hrefs_template_embedded(self):
        """Regex fallback catches hrefs inside <template> elements that BS4 ignores."""
        from browser_tools import _extract_jonah_digital_hrefs
        # Simulate Jonah Digital pattern: href before class
        html = (
            '<template><a href="/floorplans/a01/" '
            'class="jd-fp-floorplan-card jd-fp-floorplan-card--preload"></a></template>'
        )
        hrefs = _extract_jonah_digital_hrefs(html, "https://legacyhayward.com/")
        assert len(hrefs) == 1
        assert hrefs[0] == "https://legacyhayward.com/floorplans/a01/"

    def test_parse_detail_with_price(self):
        from browser_tools import _parse_jonah_digital_detail
        unit = _parse_jonah_digital_detail(_JD_DETAIL_WITH_PRICE, "https://example.com/floorplans/a01/")
        assert unit is not None
        assert unit["plan_name"] == "Plan A"
        assert unit["bedrooms"] == 1.0
        assert unit["size_sqft"] == 669.0
        assert unit["price"] == 2675.0

    def test_parse_detail_no_price(self):
        from browser_tools import _parse_jonah_digital_detail
        unit = _parse_jonah_digital_detail(_JD_DETAIL_NO_PRICE, "https://example.com/floorplans/b01/")
        assert unit is not None
        assert unit["plan_name"] == "Plan B"
        assert unit["bedrooms"] == 0.0
        assert unit["size_sqft"] == 543.0
        assert unit["price"] is None  # "Contact Us" — no price extracted

    def test_parse_detail_range_price_takes_low(self):
        from browser_tools import _parse_jonah_digital_detail
        unit = _parse_jonah_digital_detail(_JD_DETAIL_RANGE_PRICE, "https://example.com/floorplans/peak-meadow/")
        assert unit is not None
        assert unit["plan_name"] == "Peak Meadow"
        assert unit["bedrooms"] == 2.0
        assert unit["size_sqft"] == 702.0
        assert unit["price"] == 3936.0  # lower bound of range

    def test_parse_detail_slug_fallback_name(self):
        from browser_tools import _parse_jonah_digital_detail
        html = "<html><body><p>1 Bedroom | 600 sq. ft. | $2,000/mo</p></body></html>"
        unit = _parse_jonah_digital_detail(html, "https://example.com/floorplans/my-plan-slug/")
        assert unit["plan_name"] == "my-plan-slug"


# ---------------------------------------------------------------------------
# Unit: path cache — key format and migration
# ---------------------------------------------------------------------------


class TestPathCache:
    """Tests for path_cache._url_key, _legacy_key, and migration logic.

    All tests use a temporary directory so the real path_cache/ folder is
    never touched.
    """

    def _make_module(self, tmp_path):
        """Return the path_cache module with CACHE_DIR redirected to tmp_path."""
        from tests.integration.agentic_scraper import path_cache as pc
        import importlib, types

        # Build an isolated copy of the module with a patched CACHE_DIR
        mod = types.ModuleType("path_cache_under_test")
        mod.__dict__.update({k: v for k, v in pc.__dict__.items()})
        mod.CACHE_DIR = tmp_path
        # Re-bind module-level functions to use the patched CACHE_DIR
        import functools
        for name in ("load_path", "save_path", "invalidate_path"):
            orig = getattr(pc, name)
            # Rebind by injecting CACHE_DIR via closure replacement is complex;
            # instead patch the module attribute directly and restore after each test.
        return pc  # caller patches pc.CACHE_DIR directly

    # -- Key format ----------------------------------------------------------

    def test_url_key_simple_path(self):
        from hashlib import md5
        from tests.integration.agentic_scraper.path_cache import _url_key
        key = _url_key("https://www.rentmiro.com/floorplans")
        domain_part, hash_part = key.split("__")
        assert domain_part == "www_rentmiro_com"
        assert hash_part == md5(b"/floorplans").hexdigest()[:8]

    def test_url_key_strips_query_string(self):
        from tests.integration.agentic_scraper.path_cache import _url_key
        assert _url_key("https://example.com/fp?tab=1") == _url_key("https://example.com/fp")

    def test_url_key_different_paths_on_same_domain_differ(self):
        from tests.integration.agentic_scraper.path_cache import _url_key
        key_pa = _url_key("https://www.themarc-pa.com/apartments/ca/palo-alto/floor-plans")
        key_mv = _url_key("https://www.themarc-pa.com/apartments/ca/mountain-view/floor-plans")
        assert key_pa != key_mv
        # Both share the same domain prefix
        assert key_pa.split("__")[0] == key_mv.split("__")[0]

    def test_url_key_same_path_same_key(self):
        from tests.integration.agentic_scraper.path_cache import _url_key
        assert (
            _url_key("https://www.rentmiro.com/floorplans")
            == _url_key("https://www.rentmiro.com/floorplans")
        )

    def test_legacy_key_domain_only(self):
        from tests.integration.agentic_scraper.path_cache import _legacy_key
        assert _legacy_key("https://www.rentmiro.com/floorplans") == "www_rentmiro_com"

    # -- save / load round-trip (new format) ---------------------------------

    def test_save_and_load_new_format(self, tmp_path, monkeypatch):
        from tests.integration.agentic_scraper import path_cache as pc
        monkeypatch.setattr(pc, "CACHE_DIR", tmp_path)

        url = "https://www.rentmiro.com/floorplans"
        steps = [
            {"action": "navigate_to", "url": url},
            {"action": "extract_all_units", "_eau_units": 3},
        ]
        pc.save_path(url, steps, "Miro Apartments")

        key = pc._url_key(url)
        assert (tmp_path / f"{key}.json").exists()

        entry = pc.load_path(url)
        assert entry is not None
        assert entry["url"] == url
        assert entry["apartment_name"] == "Miro Apartments"
        # _eau_units internal key must be stripped
        assert all("_eau_units" not in s for s in entry["steps"])

    def test_load_returns_none_when_missing(self, tmp_path, monkeypatch):
        from tests.integration.agentic_scraper import path_cache as pc
        monkeypatch.setattr(pc, "CACHE_DIR", tmp_path)
        assert pc.load_path("https://nowhere.example.com/fp") is None

    # -- migration -----------------------------------------------------------

    def test_load_migrates_legacy_file(self, tmp_path, monkeypatch):
        """load_path finds a v1 file, writes v2, deletes v1, returns entry."""
        import json
        from datetime import datetime, timezone
        from tests.integration.agentic_scraper import path_cache as pc
        monkeypatch.setattr(pc, "CACHE_DIR", tmp_path)

        url = "https://www.rentmiro.com/floorplans"
        legacy_key = pc._legacy_key(url)
        new_key = pc._url_key(url)

        # Write a v1-format file
        entry = {
            "url": url,
            "domain": legacy_key,
            "steps": [{"action": "navigate_to", "url": url}],
            "apartment_name": "Miro",
            "last_success": datetime.now(timezone.utc).isoformat(),
            "success_count": 1,
        }
        (tmp_path / f"{legacy_key}.json").write_text(json.dumps(entry))

        result = pc.load_path(url)

        assert result is not None
        assert result["url"] == url
        # v2 file written
        assert (tmp_path / f"{new_key}.json").exists()
        # v1 file deleted
        assert not (tmp_path / f"{legacy_key}.json").exists()

    def test_load_migration_collision_guard(self, tmp_path, monkeypatch):
        """load_path skips migration when the legacy file belongs to a different URL."""
        import json
        from datetime import datetime, timezone
        from tests.integration.agentic_scraper import path_cache as pc
        monkeypatch.setattr(pc, "CACHE_DIR", tmp_path)

        url_a = "https://www.themarc-pa.com/apartments/ca/palo-alto/floor-plans"
        url_b = "https://www.themarc-pa.com/apartments/ca/mountain-view/floor-plans"

        # v1 file written for url_a
        legacy_key = pc._legacy_key(url_a)  # same as _legacy_key(url_b) — that's the bug
        assert legacy_key == pc._legacy_key(url_b)
        entry = {
            "url": url_a,
            "domain": legacy_key,
            "steps": [{"action": "navigate_to", "url": url_a}],
            "apartment_name": "The Marc PA",
            "last_success": datetime.now(timezone.utc).isoformat(),
            "success_count": 1,
        }
        (tmp_path / f"{legacy_key}.json").write_text(json.dumps(entry))

        # Requesting url_b should NOT return url_a's entry
        result = pc.load_path(url_b)
        assert result is None
        # Legacy file must NOT be migrated or deleted
        assert (tmp_path / f"{legacy_key}.json").exists()

    # -- invalidate ----------------------------------------------------------

    def test_invalidate_removes_new_format(self, tmp_path, monkeypatch):
        import json
        from datetime import datetime, timezone
        from tests.integration.agentic_scraper import path_cache as pc
        monkeypatch.setattr(pc, "CACHE_DIR", tmp_path)

        url = "https://www.rentmiro.com/floorplans"
        key = pc._url_key(url)
        entry = {"url": url, "steps": [], "last_success": datetime.now(timezone.utc).isoformat()}
        (tmp_path / f"{key}.json").write_text(json.dumps(entry))

        pc.invalidate_path(url)
        assert not (tmp_path / f"{key}.json").exists()

    def test_invalidate_removes_legacy_format(self, tmp_path, monkeypatch):
        import json
        from datetime import datetime, timezone
        from tests.integration.agentic_scraper import path_cache as pc
        monkeypatch.setattr(pc, "CACHE_DIR", tmp_path)

        url = "https://www.rentmiro.com/floorplans"
        legacy_key = pc._legacy_key(url)
        entry = {"url": url, "steps": [], "last_success": datetime.now(timezone.utc).isoformat()}
        (tmp_path / f"{legacy_key}.json").write_text(json.dumps(entry))

        pc.invalidate_path(url)
        assert not (tmp_path / f"{legacy_key}.json").exists()

    def test_invalidate_legacy_collision_safe(self, tmp_path, monkeypatch):
        """invalidate_path must NOT delete a legacy file that belongs to a different URL."""
        import json
        from datetime import datetime, timezone
        from tests.integration.agentic_scraper import path_cache as pc
        monkeypatch.setattr(pc, "CACHE_DIR", tmp_path)

        url_a = "https://www.themarc-pa.com/apartments/ca/palo-alto/floor-plans"
        url_b = "https://www.themarc-pa.com/apartments/ca/mountain-view/floor-plans"
        legacy_key = pc._legacy_key(url_a)  # == _legacy_key(url_b)

        entry = {"url": url_a, "steps": [], "last_success": datetime.now(timezone.utc).isoformat()}
        (tmp_path / f"{legacy_key}.json").write_text(json.dumps(entry))

        # Invalidating url_b must leave url_a's legacy file intact
        pc.invalidate_path(url_b)
        assert (tmp_path / f"{legacy_key}.json").exists()


# ---------------------------------------------------------------------------
# Integration tests — real browser + real Minimax API
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAgentIntegration:
    """End-to-end tests that require MINIMAX_API_KEY and a live internet connection."""

    def _get_api_key(self) -> Optional[str]:
        import os
        return os.environ.get("MINIMAX_API_KEY")

    def _skip_if_no_key(self):
        key = self._get_api_key()
        if not key:
            pytest.skip("MINIMAX_API_KEY not set — skipping integration test")

    @pytest.mark.asyncio
    async def test_scrape_rentmiro(self):
        """Scrape Miro Apartments floor plan page and verify structured output."""
        self._skip_if_no_key()

        agent = ApartmentAgent(api_key=self._get_api_key())
        result = await agent.scrape("https://www.rentmiro.com/floorplans")

        # Basic structure checks
        assert result is not None, "Agent should return ApartmentData, not None"
        assert isinstance(result.name, str) and len(result.name) > 0, "Apartment name should be non-empty"
        assert len(result.floor_plans) > 0, "At least one floor plan must be extracted"

        # At least one plan should have a price
        plans_with_price = [p for p in result.floor_plans if p.min_price is not None]
        assert len(plans_with_price) > 0, "At least one plan should have a price"

        # All prices should be positive and in a reasonable range for San Jose
        for plan in plans_with_price:
            assert plan.min_price > 0, f"Price must be positive, got {plan.min_price} for {plan.name}"
            assert plan.min_price < 20_000, f"Price {plan.min_price} seems unreasonably high for {plan.name}"
            if plan.max_price is not None:
                assert plan.max_price >= plan.min_price, "max_price must be >= min_price"

        print(f"\n=== {result.name} ===")
        print(f"Address: {result.address}")
        for plan in result.floor_plans:
            price_str = f"${plan.min_price:,.0f}" if plan.min_price else "N/A"
            size_str = f"{plan.size_sqft:,.0f} sqft" if plan.size_sqft else "N/A"
            print(f"  {plan.name}: {price_str}  {size_str}  {plan.availability or ''}")

    @pytest.mark.asyncio
    async def test_scrape_diridon_west(self):
        """Scrape Diridon West floor plan page and verify structured output."""
        self._skip_if_no_key()

        agent = ApartmentAgent(api_key=self._get_api_key())
        result = await agent.scrape("https://diridonwest.com/floorplans/")

        assert result is not None, "Agent should return ApartmentData"
        assert len(result.floor_plans) > 0, "Should find at least one floor plan"

        plans_with_price = [p for p in result.floor_plans if p.min_price is not None]
        assert len(plans_with_price) > 0, "At least one plan should have a price"

        for plan in plans_with_price:
            assert plan.min_price > 0

        print(f"\n=== {result.name} ===")
        for plan in result.floor_plans:
            price_str = f"${plan.min_price:,.0f}" if plan.min_price else "N/A"
            print(f"  {plan.name}: {price_str}  {plan.availability or ''}")

    @pytest.mark.asyncio
    async def test_scrape_result_has_valid_schema(self):
        """Schema-level check: result must serialize to/from JSON without loss."""
        self._skip_if_no_key()

        agent = ApartmentAgent(api_key=self._get_api_key())
        result = await agent.scrape("https://www.rentmiro.com/floorplans")

        assert result is not None
        # Round-trip through JSON
        raw = result.model_dump_json()
        restored = ApartmentData.model_validate_json(raw)
        assert restored.name == result.name
        assert len(restored.floor_plans) == len(result.floor_plans)
