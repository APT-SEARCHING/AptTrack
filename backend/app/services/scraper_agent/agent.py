"""Minimax-powered agentic apartment scraper.

The agent controls a real browser via ``BrowserSession`` and uses
MiniMax-M2.5 function-calling to decide which actions to take until it
has collected floor-plan and pricing data, at which point it calls
``submit_findings`` to terminate the loop.

Token optimizations (Phase 1):
  1.1  History trimming   — keep only the last N tool results in full
  1.2  Reduced page state — halved caps, smart keyword-priority truncation
  1.3  Path caching       — replay cached browser paths without LLM calls
  1.4  Browser reuse      — share one Chromium instance across a batch
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Type

from dotenv import load_dotenv
from openai import AsyncOpenAI

from .browser_tools import BrowserSession
from .models import ApartmentData, FloorPlan
from .platforms.registry import try_platforms

load_dotenv()

# Adapters too generic to cache as a sticky hint — they're last-resort fallbacks
# that match many sites by HTML structure rather than platform-specific signals.
# Storing them as hints would prevent retrying specific adapters on the next
# scrape even if the platform's own signals have recovered.
HINT_EXCLUDED_ADAPTERS = frozenset({"universal_dom"})

MODEL = "MiniMax-M2.5"
BASE_URL = "https://api.minimax.io/v1"
MAX_ITERATIONS = 35

# MiniMax-M2.5 pricing (USD per token)
_INPUT_PRICE_PER_TOKEN  = 0.30 / 1_000_000
_OUTPUT_PRICE_PER_TOKEN = 1.10 / 1_000_000

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Observability
# ---------------------------------------------------------------------------

@dataclass
class CallMetrics:
    """Token usage for a single LLM call."""
    input_tokens: int
    output_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens  * _INPUT_PRICE_PER_TOKEN +
            self.output_tokens * _OUTPUT_PRICE_PER_TOKEN
        )


@dataclass
class ScrapeMetrics:
    """Aggregated observability data for one apartment scrape.

    ``outcome`` values
    ------------------
    ``"scraped"``            — full LLM ReAct loop ran
    ``"cache_hit"``          — path-cache replay, 0 LLM calls
    ``"content_unchanged"``  — content-hash short-circuit, 0 LLM, 0 browser
    """
    url: str
    calls: List[CallMetrics] = field(default_factory=list)
    iterations: int = 0
    elapsed_sec: float = 0.0
    cache_hit: bool = False    # True when data came from path cache (0 LLM calls)
    outcome: str = "scraped"   # see docstring for allowed values
    adapter_name: Optional[str] = None  # set when outcome == "platform_direct"

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    def summary(self) -> dict:
        return {
            "url": self.url,
            "outcome": self.outcome,
            "cache_hit": self.cache_hit,
            "iterations": self.iterations,
            "llm_calls": len(self.calls),
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.total_cost_usd, 5),
            "elapsed_sec": round(self.elapsed_sec, 1),
        }


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
7. After collecting floor plan prices, do a quick check (one click each, max) BEFORE submitting:
   a. Look for an "Amenities", "Features", or "Community" tab/link in the current page state.
      If found, navigate there and scan for amenity keywords to populate the amenities object.
   b. Look for a "Specials", "Deals", "Promotions", or "Move-In Specials" tab/link.
      If found, navigate there and capture any current offer in current_special.
   If neither tab is visible in the current page state, proceed to submit_findings immediately.
   Do NOT spend more than 2 extra navigation steps on amenities/specials combined.

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
- DEPOSIT VS RENT DISAMBIGUATION: when a plan card or unit listing shows MULTIPLE
  dollar amounts, identify which is which by reading the LABEL adjacent to each amount:

  RENT (use for min_price/max_price):
    * "$X /mo", "$X per month", "$X monthly"
    * "Base Rent: $X", "Monthly Rent: $X"
    * "$X" appearing on a floor-plan card alongside bedroom/sqft info, with no
      conflicting fee label

  NOT RENT (ignore for min_price/max_price):
    * "Deposit: $X", "Security Deposit $X", "Refundable Deposit $X", "Deposit Starting at $X"
    * "$X admin fee", "$X application fee", "Application: $X"
    * "$X pet fee", "$X parking fee", "$X amenity fee"
    * "Move-in: $X", "First month: $X"

  Worked examples:

  Page shows: "Deposit: $1,000   $3,000 per month"
    Correct: min_price=3000 (the amount labeled "per month")
    Wrong:   min_price=1000 (that is the deposit amount)

  Page shows: "1 Bed | 720 sqft | $500 admin fee | $2,500/mo"
    Correct: min_price=2500 (the amount labeled "/mo")
    Wrong:   min_price=500 (that is the admin fee)

  Page shows: "Studio · Deposit Starting at $500" (with NO rent amount visible)
    Correct: min_price=null (rent not shown; deposit is not rent)
    Wrong:   min_price=500 (do not substitute the deposit)

  Page shows: "$2,500" (single amount with no other context labels)
    If on a floor-plan card alongside bedroom/sqft info → treat as rent (min_price=2500)
    If in a sidebar, fees section, or "What's included" panel → set min_price=null
- Do NOT invent or interpolate prices. If you cannot find a price for a plan/unit, leave it null.
- When a price looks like "$1,500 - $2,000", set min_price=1500 and max_price=2000.
- When only one price is shown, set both min_price and max_price to that value.
- Bedroom count is 0 for studios.

CRITICAL — plan name rules:
- The plan `name` field must be the **specific plan label or code shown on the floor-plan card**,
  e.g. "S1", "S2-A/B", "A1", "B3", "Plan E", "Floorplan 2A". NOT just the generic bedroom type.
- The generic bedroom type ("Studio", "1 Bedroom") belongs in the `bedrooms` field as a number, NOT in `name`.
- If both a plan code AND a bedroom type are shown, ALWAYS use the code as `name`.
  Example: card shows "S2-A/B\nStudio\n1 bath\n531-537 sq. ft." → name="S2-A/B", bedrooms=0, bathrooms=1, size_sqft=534
  Example: card shows "A1\n1 Bedroom\n1 bath\n650 sq. ft." → name="A1", bedrooms=1, bathrooms=1, size_sqft=650
- Plan codes are typically 1-4 characters: letters, numbers, slashes, or hyphens (e.g. "S1", "A2", "B3-C", "2A/B").
  They appear as the heading or first line of a floor-plan card BEFORE the bedroom/bath description.
- If the site only shows a generic description with no code (e.g. "Studio 1 bath"), then use the
  description as-is (e.g. "Studio" or "1 Bed/1 Bath").

CRITICAL — square footage rules:
- Always capture sqft from plan cards. Formats vary: "537 sq. ft.", "537 sqft", "531-537 sq. ft.",
  "531 - 537 Sq. Ft." — all mean square footage.
- If a range is shown (e.g. "531-537"), use the midpoint rounded to nearest integer as size_sqft.
- Never leave size_sqft null if the page shows a number followed by "sq", "sqft", or "sq. ft.".

Per-unit vs plan-level pricing:
- If the site shows individual unit numbers (e.g., "Unit E316", "HOME W302", "Apt 4B"), create one
  FloorPlan entry per unit and populate unit_number with the unit identifier.
- If the site only shows a range for a plan type (e.g., "Studio: from $2,800/mo"), create one
  FloorPlan entry for the plan type with unit_number=null and min_price=max_price=that figure.
- Prefer per-unit data over plan-level ranges when both are available (e.g., after entering an
  iframe that lists individual units).

Per-plan deep links:
- If the site shows a unique URL, hash anchor, or query-string parameter for each floor plan or
  unit (e.g., '?floorplanId=S1', '#plan-studio-a', '/floor-plans/one-bedroom'), capture it in
  external_url for that floor_plans entry. Use an absolute URL when possible; a relative path is
  acceptable if the base URL is ambiguous.
- If a single URL applies to all plans on the page (e.g., the current page already shows all plans),
  leave external_url blank — we will fall back to the apartment-level source URL.
- Do NOT fabricate URLs. Only populate external_url if you observe a distinct link or anchor
  in the page state for that specific plan.

Per-unit compass direction:
- If a unit listing explicitly shows a compass direction (e.g., "N", "NE", "faces south",
  "southwest-facing"), record it in facing using standard abbreviations: N, S, E, W,
  NE, NW, SE, SW.
- If the page contains a floor plate or site plan rendered as SVG or structured HTML
  (common on SightMap), examine unit positions relative to any north indicator or
  orientation label. Infer compass direction from position (e.g., a unit on the
  north side of the building faces N or NE/NW depending on its corner).
- Do NOT infer direction from non-compass descriptions ("pool-facing", "garden view",
  "city view"). Leave facing blank for those.
- Do NOT fabricate. If compass direction cannot be determined from the page, leave blank.

Per-unit floor level:
- Record the floor number as an integer in floor_level.
- If the unit number encodes the floor (e.g., "305" → floor 3, "1204" → floor 12,
  "A305" → floor 3), extract the floor number from the leading digit(s).
- If the floor is stated explicitly ("3rd floor", "Floor 5"), use that number.
- If floor level cannot be determined, leave blank.

AMENITY RULES:
- Scan the full page text for amenity keywords and populate the amenities object accordingly.
  - 'pet-friendly', 'pets allowed', 'pets welcome', 'dogs welcome', 'cats allowed' → pets_allowed=true
  - 'no pets', 'no animals', 'pet-free' → pets_allowed=false
  - 'parking garage', 'parking available', 'assigned parking', 'covered parking', 'parking included' → has_parking=true
  - 'pool', 'swimming pool', 'resort pool', 'saltwater pool', 'rooftop pool' → has_pool=true
  - 'fitness center', 'fitness studio', 'gym', 'workout room', 'exercise room' → has_gym=true
  - 'dishwasher', 'in-unit dishwasher' → has_dishwasher=true
  - 'washer/dryer', 'washer and dryer', 'w/d in unit', 'in-unit laundry', 'full-size washer' → has_washer_dryer=true
  - 'air conditioning', 'central air', 'central AC', 'AC', 'A/C' → has_air_conditioning=true
- null means unknown (page didn't mention it). Only set false if the page explicitly says the amenity is NOT available.
- Amenities are complex-level, not per-unit — a single amenities object covers the whole property.

SPECIALS / PROMOTIONS RULES:
- Look for current move-in offers anywhere on the page: banners, callout boxes, header text, a "Specials" tab.
- Capture the offer verbatim (or a clean short summary) in current_special. Examples:
  - "$250 deposit on select homes" → current_special="$250 deposit on select homes"
  - "1 month free rent with 12-month lease" → current_special="1 month free rent with 12-month lease"
  - "Waived $500 admin fee — limited time" → current_special="Waived $500 admin fee — limited time"
  - "Look & Lease: move in within 48h for $99 deposit" → current_special="Look & Lease: $99 deposit if move-in within 48h"
- Keep it under 120 characters. Do not paraphrase pricing — copy the offer text directly.
- If no special or promotion is visible anywhere, set current_special=null.
- Do NOT fabricate specials. Only capture what is explicitly stated on the page."""

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
                                    "description": "Specific plan code shown on the card (e.g. 'S1', 'S2-A/B', 'A1', 'Plan A3'). Use the actual label, not the generic bedroom type like 'Studio' unless no code is shown.",
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
                                    "description": "Square footage as a number. If shown as a range (e.g. '531-537 sq. ft.'), use the midpoint (534). Never omit if sqft is visible on the page.",
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
                                "external_url": {
                                    "type": "string",
                                    "description": "URL or deep link to this specific plan if the site supports it (e.g. '?floorplanId=S1', '#plan-a3', '/plans/studio-s1'). Leave blank if one URL covers all plans.",
                                },
                                "floor_level": {
                                    "type": "number",
                                    "description": "Floor number this unit is on (integer, e.g. 3 for 3rd floor). Extract from unit number if inferable (e.g. '305' → 3).",
                                },
                                "facing": {
                                    "type": "string",
                                    "description": "Compass direction this unit faces: one of N, S, E, W, NE, NW, SE, SW. Only populate from explicit labels or floor plate position — never from descriptive labels like 'pool-facing'.",
                                },
                            },
                            "required": ["name"],
                        },
                    },
                    "amenities": {
                        "type": "object",
                        "description": (
                            "Amenity flags for the apartment complex. "
                            "Use null if the page doesn't mention an amenity, "
                            "false if explicitly not offered, true if offered."
                        ),
                        "properties": {
                            "pets_allowed": {"type": ["boolean", "null"]},
                            "has_parking": {"type": ["boolean", "null"]},
                            "has_pool": {"type": ["boolean", "null"]},
                            "has_gym": {"type": ["boolean", "null"]},
                            "has_dishwasher": {"type": ["boolean", "null"]},
                            "has_washer_dryer": {"type": ["boolean", "null"]},
                            "has_air_conditioning": {"type": ["boolean", "null"]},
                        },
                    },
                    "current_special": {
                        "type": ["string", "null"],
                        "description": (
                            "Any current move-in offer, deposit special, or discount as plain text. "
                            "e.g. '$250 deposit on select homes', '1 month free on 12-month leases', "
                            "'Waived admin fee this week'. null if no special found."
                        ),
                    },
                },
                "required": ["name", "floor_plans"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _derive_name_from_html(html: str, url: str) -> str:
    """Extract a human-readable apartment name from the homepage HTML.

    Strategy: <title> text before the first '|' and '-' separator, then
    fallback to <h1>, then the raw URL.  Used by platform adapters after
    a successful fast-path extraction to populate ApartmentData.name.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    title_tag = soup.find("title")
    if title_tag:
        name = title_tag.get_text(strip=True).split("|")[0].split("-")[0].strip()
        if name:
            return name
    h1 = soup.find("h1")
    if h1:
        name = h1.get_text(strip=True)
        if name:
            return name
    return url


def _sanitize(data: Optional[ApartmentData]) -> Optional[ApartmentData]:
    """Remove prices that look like they were copied from a global filter slider."""
    if data is None:
        return None
    plans = data.floor_plans
    if len(plans) < 2:
        return data

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
    for pair, cnt in counts.items():
        if cnt / total_priced > 0.50 and len(counts) > 1:
            logger.warning(
                "Detected slider-range contamination: %s on %d/%d plans — nulling",
                pair, cnt, total_priced,
            )
            for p in plans:
                if (p.min_price, p.max_price) == pair:
                    p.min_price = None
                    p.max_price = None
            break
    return data


def _parse_units_to_apartment_data(
    units: List[Dict[str, Any]], name: str, url: str
) -> Optional[ApartmentData]:
    """Convert ``extract_all_units`` output directly to :class:`ApartmentData`.

    Used during path-cache replay to produce structured data without any
    LLM call — the unit list is already deterministic.
    """
    if not units:
        return None
    floor_plans: List[FloorPlan] = []
    for u in units:
        price = u.get("price")
        fp = FloorPlan(
            name=u.get("plan_name") or "Unit",
            unit_number=u.get("unit_number"),
            bedrooms=u.get("bedrooms"),
            bathrooms=u.get("bathrooms"),
            size_sqft=float(u["size_sqft"]) if u.get("size_sqft") else None,
            min_price=float(price) if price else None,
            max_price=float(price) if price else None,
            availability=u.get("availability", "Available"),
        )
        floor_plans.append(fp)
    if not floor_plans:
        return None
    return ApartmentData(name=name, website=url, floor_plans=floor_plans)


class _NullContextManager:
    """Wrap an existing ``BrowserSession`` so ``async with`` doesn't close it.

    Used for browser reuse (1.4): the caller owns the lifecycle.
    """
    def __init__(self, browser: BrowserSession) -> None:
        self._browser = browser

    async def __aenter__(self) -> BrowserSession:
        return self._browser

    async def __aexit__(self, *_args: Any) -> None:
        pass  # do NOT close — the shared browser is owned by the caller


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class ApartmentAgent:
    """Agentic apartment scraper powered by MiniMax-M2.5.

    Parameters
    ----------
    api_key:
        MiniMax API key. Falls back to ``MINIMAX_API_KEY`` env var.
    _client:
        Inject a pre-built ``AsyncOpenAI`` client (useful for testing).
    _browser_class:
        Inject a custom ``BrowserSession`` subclass (useful for testing).
    _browser_instance:
        Pass a pre-started ``BrowserSession`` to reuse across multiple
        ``scrape()`` calls (browser-reuse optimisation, 1.4).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        _client: Optional[AsyncOpenAI] = None,
        _browser_class: Optional[Type[BrowserSession]] = None,
        _browser_instance: Optional[BrowserSession] = None,
    ) -> None:
        resolved_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        self._client = _client or AsyncOpenAI(base_url=BASE_URL, api_key=resolved_key)
        self._browser_class = _browser_class or BrowserSession
        self._browser_instance = _browser_instance  # optional shared browser (1.4)

    # ── History trimming (1.1) ───────────────────────────────────────────────

    def _trim_messages(self, messages: list, keep_last: int = 4) -> list:
        """Keep only the most recent *keep_last* tool results in full.

        Older tool results are replaced with a compact summary so the model
        retains context without re-reading full page dumps.  Saves 40-60% of
        cumulative input tokens on longer scrapes.
        """
        trimmed = []
        tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
        cutoff = tool_indices[-keep_last] if len(tool_indices) > keep_last else 0

        for i, msg in enumerate(messages):
            if i < cutoff and msg.get("role") == "tool":
                try:
                    content = json.loads(msg["content"])
                    summary: Dict[str, Any] = {
                        "url": content.get("url", content.get("active_frame", "")),
                        "_trimmed": True,
                        "buttons_count": len(content.get("buttons", [])),
                        "links_count": len(content.get("links", [])),
                    }
                except (json.JSONDecodeError, TypeError):
                    summary = {"_trimmed": True}
                trimmed.append({**msg, "content": json.dumps(summary)})
            else:
                trimmed.append(msg)
        return trimmed

    # ── LLM call with observability ─────────────────────────────────────────

    async def _llm_call(self, messages: list, metrics: "ScrapeMetrics") -> object:
        """Call the LLM with exponential-backoff retry on 5xx / overload errors.

        Appends a :class:`CallMetrics` entry to *metrics* on every successful call.
        """
        import openai
        max_retries = 5
        delay = 5.0
        for attempt in range(max_retries):
            try:
                response = await self._client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=TOOLS,  # type: ignore[arg-type]
                    tool_choice="auto",
                )
                usage = getattr(response, "usage", None)
                if usage:
                    call_m = CallMetrics(
                        input_tokens=getattr(usage, "prompt_tokens", 0),
                        output_tokens=getattr(usage, "completion_tokens", 0),
                    )
                    metrics.calls.append(call_m)
                    logger.debug(
                        "LLM call #%d — in=%d out=%d cost=$%.5f",
                        len(metrics.calls),
                        call_m.input_tokens,
                        call_m.output_tokens,
                        call_m.cost_usd,
                    )
                return response
            except (openai.InternalServerError, openai.APIStatusError) as exc:
                code = getattr(exc, "status_code", None)
                if attempt < max_retries - 1 and code in (429, 500, 502, 503, 529):
                    logger.warning(
                        "API error %s on attempt %d — retrying in %.0fs",
                        code, attempt + 1, delay,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 60)
                else:
                    raise

    # ── Path-cache replay (1.3) ──────────────────────────────────────────────

    async def _replay_cached_path(
        self,
        url: str,
        steps: List[Dict[str, Any]],
        apartment_name: str,
        browser: BrowserSession,
    ) -> Optional[ApartmentData]:
        """Execute cached browser steps without LLM calls.

        Returns :class:`ApartmentData` if replay produced pricing data,
        ``None`` if any step failed (caller falls back to full agent loop).

        Uses the last ``extract_all_units`` result found anywhere in the
        replay, not just the final step — some paths navigate further after
        extraction (e.g. amenities, contact) and would otherwise always miss.
        """
        last_result: Optional[Dict[str, Any]] = None
        units_result: Optional[Dict[str, Any]] = None  # best extract_all_units hit
        for step in steps:
            action = step.get("action")
            args: Dict[str, Any] = step.get("args", {})
            try:
                if action == "navigate_to":
                    last_result = await browser.navigate_to(args.get("url", url))
                elif action == "click_link":
                    last_result = await browser.click_link(args.get("text_or_href", ""))
                elif action == "click_button":
                    last_result = await browser.click_button(args.get("text", ""))
                elif action == "scroll_down":
                    last_result = await browser.scroll_down()
                elif action == "read_iframe":
                    last_result = await browser.read_iframe(args.get("keyword", ""))
                elif action == "extract_all_units":
                    last_result = await browser.extract_all_units()
                    if isinstance(last_result, dict) and last_result.get("units"):
                        units_result = last_result
                else:
                    logger.warning("Replay: unknown action %r, skipping", action)
                    continue

                if isinstance(last_result, dict) and last_result.get("error"):
                    logger.info("Replay step %r failed: %s", action, last_result["error"])
                    return None
            except Exception as exc:
                logger.info("Replay step %r raised: %s", action, exc)
                return None

        # Prefer the extract_all_units result even if later steps followed it.
        check = units_result if units_result is not None else last_result
        if isinstance(check, dict) and "units" in check:
            data = _parse_units_to_apartment_data(
                check["units"], apartment_name, url
            )
            if data and data.floor_plans:
                return data

        # No usable units extracted — caller falls back to full LLM loop.
        return None

    # ── Main scrape loop ─────────────────────────────────────────────────────

    async def scrape(
        self,
        url: str,
        headless: bool = True,
    ) -> Tuple[Optional[ApartmentData], ScrapeMetrics]:
        """Run the agent and return ``(data, metrics)``.

        Flow
        ----
        1. If a path-cache entry exists (1.3): attempt browser-only replay.
           On success → return immediately with ``metrics.cache_hit = True``.
        2. Otherwise run the full ReAct loop, trimming old history (1.1) and
           using reduced page-state caps (1.2).
        3. On success, save the navigation path to cache for next time (1.3).

        *data* is ``None`` if no pricing data was found.  *metrics* is always
        returned and reflects actual LLM usage (0 calls on cache hit).
        """
        from .compliance import check_robots_txt
        from .path_cache import invalidate_path, load_path, save_path

        metrics = ScrapeMetrics(url=url)
        t0 = time.monotonic()

        # Compliance gate — respect robots.txt before any browser activity
        robots = await check_robots_txt(url)
        if not robots["allowed"]:
            logger.warning("robots.txt disallows scraping %s — aborting", url)
            metrics.elapsed_sec = time.monotonic() - t0
            return None, metrics

        # Choose browser context (reuse vs. create new) — optimisation 1.4
        if self._browser_instance is not None:
            self._browser_instance._active_frame = None  # reset state for new site
            browser_ctx: Any = _NullContextManager(self._browser_instance)
        else:
            browser_ctx = self._browser_class(headless=headless)

        async with browser_ctx as browser:
            from .fetch import fetch_static, fetch_rendered, has_sufficient_plan_signals, is_cloudflare_challenge
            from .browser_tools import is_apartment_website

            # ── Load adapter hint from registry (before any I/O) ─────────────
            from datetime import datetime, timezone
            from urllib.parse import urlparse
            from sqlalchemy import select as _sa_select
            _domain = urlparse(url).netloc.lower()
            _hint: Optional[str] = None
            try:
                from app.db.session import SessionLocal as _SessionLocal
                from app.models.site_registry import ScrapeSiteRegistry as _SiteReg
                with _SessionLocal() as _hint_db:
                    _hint_reg = _hint_db.execute(
                        _sa_select(_SiteReg).where(_SiteReg.domain == _domain)
                    ).scalar_one_or_none()
                    if _hint_reg and _hint_reg.last_successful_adapter:
                        _candidate = _hint_reg.last_successful_adapter
                        if _candidate in HINT_EXCLUDED_ADAPTERS:
                            logger.debug(
                                "Ignoring excluded hint '%s' for %s — will walk full registry",
                                _candidate, _domain,
                            )
                        else:
                            _hint = _candidate
            except Exception as _exc:
                logger.warning("Failed to load registry hint for %s: %s", _domain, _exc)

            # ── Stage 1: static HTML fast path ───────────────────────────────
            _html_static = await fetch_static(url)
            if is_cloudflare_challenge(_html_static):
                logger.info("Cloudflare challenge on %s — upgrading to rendered", url)
                _html_static = ""
            _html = _html_static
            _used_rendered = False

            if _html:
                _apt_valid, _apt_reason = is_apartment_website(_html, url)
                if not _apt_valid:
                    metrics.outcome = "not_apartment"
                    metrics.elapsed_sec = time.monotonic() - t0
                    logger.info("Skipping %s — not an apartment website: %s", url, _apt_reason)
                    return None, metrics

            # ── Stage 2: try platform adapters on static HTML ─────────────────
            _platform_result = await try_platforms(_html, url, browser, hint_adapter_name=_hint) if _html else None

            # ── Stage 3: static miss + weak signals → upgrade to rendered ─────
            if _platform_result is None and not has_sufficient_plan_signals(_html):
                logger.info(
                    "Static adapters missed for %s (weak signals) — upgrading to rendered fetch",
                    url,
                )
                _rendered = await fetch_rendered(url, browser)
                if _rendered and len(_rendered) > max(len(_html) * 2, 10_000):
                    # Re-check is_apartment_website on rendered HTML — catches SPA sites
                    # whose static <title> is a blank shell but rendered title reveals
                    # "Senior Living" or "Affordable Housing".
                    _apt_valid, _apt_reason = is_apartment_website(_rendered, url)
                    if not _apt_valid:
                        metrics.outcome = "not_apartment"
                        metrics.elapsed_sec = time.monotonic() - t0
                        logger.info("Rejected after render: %s — %s", url, _apt_reason)
                        return None, metrics
                    _html = _rendered
                    _used_rendered = True
                    _platform_result = await try_platforms(_html, url, browser, hint_adapter_name=_hint)

            # ── Stage 4: platform succeeded (static or rendered path) ─────────
            if _platform_result is not None:
                _pt_units, _pt_name = _platform_result
                _pt_data = _parse_units_to_apartment_data(
                    _pt_units, _derive_name_from_html(_html, url), url
                )
                if _pt_data and _pt_data.floor_plans:
                    metrics.outcome = "platform_direct_rendered" if _used_rendered else "platform_direct_static"
                    metrics.adapter_name = _pt_name
                    metrics.iterations = 0
                    metrics.elapsed_sec = time.monotonic() - t0
                    logger.info(
                        "Platform '%s' (%s path) → %d plans, $0.00, %.1fs",
                        _pt_name, "rendered" if _used_rendered else "static",
                        len(_pt_data.floor_plans), metrics.elapsed_sec,
                    )
                    # ── Persist adapter hint for next scrape ─────────────────
                    # Skip fallback adapters — caching them as hints would lock
                    # the domain out of specific-adapter retry on recovery.
                    if _pt_name in HINT_EXCLUDED_ADAPTERS:
                        logger.debug(
                            "Skipping hint write for fallback adapter '%s' on %s",
                            _pt_name, _domain,
                        )
                    elif _hint != _pt_name:
                        try:
                            from app.db.session import SessionLocal as _SessionLocal2
                            from app.models.site_registry import ScrapeSiteRegistry as _SiteReg2
                            with _SessionLocal2() as _hint_db2:
                                _hint_reg2 = _hint_db2.execute(
                                    _sa_select(_SiteReg2).where(_SiteReg2.domain == _domain)
                                ).scalar_one_or_none()
                                if _hint_reg2:
                                    _hint_reg2.last_successful_adapter = _pt_name
                                    _hint_reg2.last_adapter_success_at = datetime.now(timezone.utc)
                                    _hint_db2.commit()
                                    logger.debug("Registry hint updated: %s → %s", _domain, _pt_name)
                        except Exception as _exc2:
                            logger.warning("Failed to update registry hint for %s: %s", _domain, _exc2)
                    return _sanitize(_pt_data), metrics

            # ── Stage 5: path-cache + LLM agent (existing flow, unchanged) ───

            # ── 1.3: try cached path first ───────────────────────────────────
            cache_entry = load_path(url)
            if cache_entry:
                logger.info(
                    "Path cache HIT for %s — replaying %d steps (0 LLM calls)",
                    url, len(cache_entry["steps"]),
                )
                cached_data = await self._replay_cached_path(
                    url,
                    cache_entry["steps"],
                    cache_entry.get("apartment_name", ""),
                    browser,
                )
                if cached_data and cached_data.floor_plans:
                    metrics.cache_hit = True
                    metrics.outcome = "cache_hit"
                    metrics.elapsed_sec = time.monotonic() - t0
                    logger.info(
                        "Cache replay OK — %d plans, $0.00, %.1fs",
                        len(cached_data.floor_plans), metrics.elapsed_sec,
                    )
                    return _sanitize(cached_data), metrics
                else:
                    logger.info("Cache replay failed — invalidating and running full loop")
                    invalidate_path(url)

            # ── Full ReAct agent loop ────────────────────────────────────────
            messages: List[Dict[str, Any]] = [
                {
                    "role": "user",
                    "content": f"Extract apartment floor plan and pricing information from: {url}",
                }
            ]
            result: Optional[ApartmentData] = None
            navigation_steps: List[Dict[str, Any]] = []  # browser steps to cache

            for iteration in range(MAX_ITERATIONS):
                logger.info("Agent iteration %d / %d", iteration + 1, MAX_ITERATIONS)
                metrics.iterations = iteration + 1

                # 1.1: trim old tool results before sending to LLM
                response = await self._llm_call(
                    [{"role": "system", "content": SYSTEM_PROMPT}]
                    + self._trim_messages(messages),
                    metrics,
                )

                choice = response.choices[0]
                assistant_msg = choice.message

                assistant_dict: Dict[str, Any] = {"role": "assistant"}
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

                if not assistant_msg.tool_calls:
                    logger.info(
                        "Agent stopped with no tool call (finish_reason=%s)",
                        choice.finish_reason,
                    )
                    break

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
                                "submit_findings — %d plan(s) for %r",
                                len(result.floor_plans), result.name,
                            )
                        except Exception as exc:
                            logger.warning("Failed to parse submit_findings: %s", exc)
                        tool_result: Dict[str, Any] = {
                            "status": "ok", "message": "Findings recorded.",
                        }
                        done = True

                    else:
                        # Record browser step for path cache (1.3)
                        navigation_steps.append({"action": name, "args": args})

                        if name == "extract_all_units":
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
                            "content": json.dumps(
                                tool_result, ensure_ascii=False, default=str
                            ),
                        }
                    )

                if done:
                    break

            # ── 1.3: save navigation path on success ─────────────────────────
            if result and result.floor_plans and navigation_steps:
                save_path(url, navigation_steps, result.name)

        metrics.elapsed_sec = time.monotonic() - t0
        data = _sanitize(result)
        logger.info(
            "Scrape complete — cache=%s, %d iter, %d calls, %d tok, $%.4f, %.1fs",
            metrics.cache_hit,
            metrics.iterations,
            len(metrics.calls),
            metrics.total_tokens,
            metrics.total_cost_usd,
            metrics.elapsed_sec,
        )
        return data, metrics
