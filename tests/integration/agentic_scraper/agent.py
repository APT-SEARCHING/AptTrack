"""Minimax-powered agentic apartment scraper.

The agent controls a real browser via ``BrowserSession`` and uses
MiniMax-M2.5 function-calling to decide which actions to take until it
has collected floor-plan and pricing data, at which point it calls
``submit_findings`` to terminate the loop.
"""

import asyncio
import json
import logging
import os
from typing import Optional, Type

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .browser_tools import BrowserSession
from .models import ApartmentData

load_dotenv()

MODEL = "MiniMax-M2.5"
BASE_URL = "https://api.minimax.io/v1"
MAX_ITERATIONS = 35

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert apartment research agent. Your job is to visit an apartment complex website and extract detailed rental information.

Use the browser tools to navigate the site and find:
- Apartment complex name and address
- Every available floor plan type (Studio, 1BR, 2BR, 3BR, …)
- Monthly rent for each plan (min and max if a range is shown)
- Square footage for each plan
- Current availability

Navigation strategy:
1. Navigate to the provided URL first.
2. Look for links or buttons labelled "Floor Plans", "Availability", "Apartments", "Pricing", or "Rent" and click them.
3. If the page state lists "iframes", call read_iframe with a keyword from the iframe URL (e.g. "sightmap", "entrata", "yardi"). The iframe often contains the real per-unit pricing data.
4. Inside a SightMap iframe (URL contains "sightmap") or any iframe with unit listings:
   a. Immediately call extract_all_units — it automatically cycles through every floor with available homes and returns a structured unit list.
   b. Use that unit list to populate floor_plans in submit_findings (one entry per unit, with unit_number filled in).
   c. Do NOT manually click bedroom/sqft/price filter buttons.
5. If there is no iframe, look for per-plan "View Available Units" or "See Units" buttons and click them.
6. Scroll down to see all plans/units — many pages load content lazily.
7. submit_findings as soon as you have unit data — do not keep exploring once you have prices.

Rules:
- Do not navigate away from the apartment complex domain.
- Prefer pages whose URL contains "floor", "plan", "availab", or "pricing".

CRITICAL — price extraction rules:
- A PRICE RANGE FILTER / SLIDER (e.g., "Price $1,500 to $5,000", a "$X — $Y" slider control, or
  "Prices from $X") is a search filter for the visitor. It is NOT the rent for any specific plan.
  NEVER use these slider/filter values as a plan's min_price or max_price.
- Only record a price when a specific dollar amount is shown directly on a floor plan card, unit
  row, or unit detail panel, clearly tied to that specific plan or unit.
- If a plan card shows "Contact for pricing", "Call for details", "Waitlist", or no dollar amount
  at all, set min_price and max_price to null for that plan.
- Do NOT invent or interpolate prices. If you cannot find a price for a plan/unit, leave it null.
- When a price looks like "$1,500 - $2,000", set min_price=1500 and max_price=2000.
- When only one price is shown, set both min_price and max_price to that value.
- Bedroom count is 0 for studios.

Per-unit vs plan-level pricing:
- If the site shows individual unit numbers (e.g., "Unit E316", "HOME W302", "Apt 4B"), create one
  FloorPlan entry per unit and populate unit_number with the unit identifier.
- If the site only shows a range for a plan type (e.g., "Studio: from $2,800/mo"), create one
  FloorPlan entry for the plan type with unit_number=null and min_price=max_price=that figure.
- Prefer per-unit data over plan-level ranges when both are available (e.g., after entering an
  iframe that lists individual units)."""

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI-compatible function-calling schema)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "navigate_to",
            "description": "Navigate to a URL and return the page text, links, and buttons.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Full URL to navigate to"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_link",
            "description": (
                "Click a link by its visible text or partial href. "
                "Examples: 'Floor Plans', 'floorplans', 'View Availability'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text_or_href": {
                        "type": "string",
                        "description": "Visible link text or href substring to match",
                    },
                },
                "required": ["text_or_href"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "click_button",
            "description": (
                "Click a button or ARIA tab by its visible text. "
                "Use this for bedroom-type tabs like 'Studio', '1 Bedroom', etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Button or tab label to match",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_down",
            "description": "Scroll down one viewport to reveal more content.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_all_units",
            "description": (
                "After entering an iframe with read_iframe, call this to automatically "
                "cycle through every floor/tab that has available units and return a "
                "structured list of all individual units with their prices. "
                "Use this immediately after read_iframe instead of manually clicking floors."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_iframe",
            "description": (
                "Switch into an embedded iframe and return its content. "
                "Use this when the page state lists iframes (e.g. sightmap, entrata, yardi). "
                "The iframe usually contains the real per-unit pricing data. "
                "After calling this, click_button / scroll_down operate inside the iframe."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "Substring of the iframe src URL to match, e.g. 'sightmap', 'entrata', 'yardi'",
                    },
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_findings",
            "description": (
                "Submit the final extracted apartment data. "
                "Call this when you have collected floor-plan and pricing information."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Apartment complex name",
                    },
                    "address": {
                        "type": "string",
                        "description": "Full street address",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Contact phone number",
                    },
                    "website": {
                        "type": "string",
                        "description": "Website URL that was scraped",
                    },
                    "floor_plans": {
                        "type": "array",
                        "description": "All floor plan configurations found",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Plan label (e.g. 'Studio', '1 Bed/1 Bath', 'Plan A3')",
                                },
                                "unit_number": {
                                    "type": "string",
                                    "description": "Specific unit identifier if shown (e.g. 'E316', '#201'). Omit for plan-level entries.",
                                },
                                "bedrooms": {
                                    "type": "number",
                                    "description": "Bedroom count (0 for studio)",
                                },
                                "bathrooms": {
                                    "type": "number",
                                    "description": "Bathroom count",
                                },
                                "size_sqft": {
                                    "type": "number",
                                    "description": "Square footage as a number",
                                },
                                "min_price": {
                                    "type": "number",
                                    "description": "Lowest monthly rent in USD (no $ sign)",
                                },
                                "max_price": {
                                    "type": "number",
                                    "description": "Highest monthly rent in USD (no $ sign)",
                                },
                                "availability": {
                                    "type": "string",
                                    "description": "'Available', 'Now', a date string, or 'Waitlist'",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                },
                "required": ["name", "floor_plans"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


def _sanitize(data: Optional[ApartmentData]) -> Optional[ApartmentData]:
    """Remove prices that look like they were copied from a global filter slider.

    A classic symptom: every plan that is NOT available gets the exact same
    (min_price, max_price) pair that matches the site-wide price range slider
    (e.g., all unavailable plans show $2,833–$7,195 while the one available
    plan shows a specific price like $3,614).  When we detect this pattern we
    null-out the repeated slider values, keeping only the distinct per-plan
    prices.
    """
    if data is None:
        return None

    plans = data.floor_plans
    if len(plans) < 2:
        return data

    # Collect (min, max) pairs that have actual prices
    from collections import Counter
    price_pairs = [
        (p.min_price, p.max_price)
        for p in plans
        if p.min_price is not None and p.max_price is not None
    ]
    if not price_pairs:
        return data

    counts = Counter(price_pairs)
    total_priced = len(price_pairs)

    # If one (min, max) pair covers >50 % of all priced plans AND there are
    # other distinct prices present, that dominant pair is almost certainly
    # the slider range rather than a real plan price.
    for pair, cnt in counts.items():
        if cnt / total_priced > 0.50 and len(counts) > 1:
            logger.warning(
                "Detected likely slider-range contamination: %s appears on %d/%d plans — nulling it out",
                pair, cnt, total_priced,
            )
            for p in plans:
                if (p.min_price, p.max_price) == pair:
                    p.min_price = None
                    p.max_price = None
            break  # only strip the single dominant pair

    return data


class ApartmentAgent:
    """Agentic apartment scraper powered by MiniMax-M2.5.

    Parameters
    ----------
    api_key:
        Minimax API key.  Falls back to ``MINIMAX_API_KEY`` env var.
    _client:
        Inject a pre-built ``AsyncOpenAI`` client (useful for testing).
    _browser_class:
        Inject a custom ``BrowserSession`` subclass (useful for testing).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        _client: Optional[AsyncOpenAI] = None,
        _browser_class: Optional[Type[BrowserSession]] = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        self._client = _client or AsyncOpenAI(base_url=BASE_URL, api_key=resolved_key)
        self._browser_class = _browser_class or BrowserSession

    async def _llm_call(self, messages: list) -> object:
        """Call the LLM with exponential-backoff retry on 5xx / overload errors."""
        import openai
        max_retries = 5
        delay = 5.0
        for attempt in range(max_retries):
            try:
                return await self._client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS,  # type: ignore[arg-type]
                    tool_choice="auto",
                )
            except (openai.InternalServerError, openai.APIStatusError) as exc:
                code = getattr(exc, "status_code", None)
                if attempt < max_retries - 1 and code in (429, 500, 502, 503, 529):
                    logger.warning(
                        "API error %s on attempt %d — retrying in %.0fs", code, attempt + 1, delay
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
                else:
                    raise

    async def scrape(self, url: str, headless: bool = True) -> Optional[ApartmentData]:
        """Run the agent loop and return extracted apartment data.

        Returns ``None`` if the agent exhausted its iteration budget without
        calling ``submit_findings``.
        """
        messages: list[dict] = [
            {
                "role": "user",
                "content": f"Extract apartment floor plan and pricing information from: {url}",
            }
        ]
        result: Optional[ApartmentData] = None

        async with self._browser_class(headless=headless) as browser:
            for iteration in range(MAX_ITERATIONS):
                logger.info("Agent iteration %d / %d", iteration + 1, MAX_ITERATIONS)

                response = await self._llm_call(
                    [{"role": "system", "content": SYSTEM_PROMPT}] + messages
                )

                choice = response.choices[0]
                assistant_msg = choice.message

                # Append assistant turn to conversation history
                assistant_dict: dict = {"role": "assistant"}
                if assistant_msg.content:
                    assistant_dict["content"] = assistant_msg.content
                if assistant_msg.tool_calls:
                    assistant_dict["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_msg.tool_calls
                    ]
                messages.append(assistant_dict)

                # Model decided it was done without calling a tool
                if not assistant_msg.tool_calls:
                    logger.info("Agent stopped with no tool call (finish_reason=%s)", choice.finish_reason)
                    break

                # Execute tool calls
                done = False
                for tc in assistant_msg.tool_calls:
                    name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    logger.info("Tool: %s  args=%s", name, args)

                    if name == "submit_findings":
                        try:
                            result = ApartmentData(**args)
                            logger.info(
                                "submit_findings called — %d plan(s) for %r",
                                len(result.floor_plans),
                                result.name,
                            )
                        except Exception as exc:
                            logger.warning("Failed to parse submit_findings payload: %s", exc)
                        tool_result: dict = {"status": "ok", "message": "Findings recorded."}
                        done = True

                    elif name == "extract_all_units":
                        tool_result = await browser.extract_all_units()
                    elif name == "navigate_to":
                        tool_result = await browser.navigate_to(args.get("url", ""))
                    elif name == "read_iframe":
                        tool_result = await browser.read_iframe(args.get("keyword", ""))
                    elif name == "click_link":
                        tool_result = await browser.click_link(args.get("text_or_href", ""))
                    elif name == "click_button":
                        tool_result = await browser.click_button(args.get("text", ""))
                    elif name == "scroll_down":
                        tool_result = await browser.scroll_down()
                    else:
                        tool_result = {"error": f"Unknown tool: {name!r}"}

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                        }
                    )

                if done:
                    break

        return _sanitize(result)
