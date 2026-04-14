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
        result = await agent.scrape("https://example-apts.com")

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
        result = await agent.scrape("https://example.com")

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
        result = await agent.scrape("https://diridonwest.com")

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
        result = await agent.scrape("https://example.com")

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
        result = await agent.scrape("https://example.com")

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
        result = await agent.scrape("https://example.com")

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
