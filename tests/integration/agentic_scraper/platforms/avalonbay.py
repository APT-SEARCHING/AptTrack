"""AvalonBay Communities platform adapter.

AvalonBay properties (avaloncommunities.com — both Avalon and AVA brands)
are rendered via Arc Publishing (Washington Post CMS).  The page HTML
contains a server-side-rendered JSON blob:

    window.Fusion = window.Fusion || {};
    ...
    Fusion.globalContent = { "communityId": "AVB-CA540", "units": [...], ... };

The `units` array provides complete per-unit data:
  - floorPlan.name   → plan name (e.g. "796", "S1")
  - bedroomNumber    → int (0 = studio)
  - bathroomNumber   → int/float
  - squareFeet       → int
  - floorNumber      → string
  - unitStatus       → "VacantAvailable" | "Occupied" | ...
  - startingAtPricesUnfurnished.prices.netEffectivePrice → int

The data is fully available in static HTML — no Playwright or API calls
are needed.  We group individual units by plan name and report the
minimum price across all available units per plan.

detect() fires when:
  - The URL host contains "avaloncommunities.com", OR
  - Fusion.globalContent appears in the HTML.
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Dict, List, Optional

from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_FUSION_CONTENT_RE = re.compile(
    r"Fusion\.globalContent\s*=\s*(\{.+?);\s*Fusion\.",
    re.DOTALL,
)


def _parse_avalon_global_content(html: str) -> List[Dict]:
    """Parse Fusion.globalContent from AvalonBay page HTML.

    Groups individual units by floorPlan.name and returns one dict per
    distinct plan, carrying the minimum price across available units.
    Returns [] if the blob is absent or contains no usable units.
    """
    m = _FUSION_CONTENT_RE.search(html)
    if not m:
        return []

    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError) as exc:
        logger.debug("AvalonBayAdapter: failed to parse globalContent JSON: %s", exc)
        return []

    raw_units: List[Dict] = data.get("units", [])
    if not raw_units:
        return []

    # Group by plan name; track min price over available units
    plans: Dict[str, Dict] = {}
    for unit in raw_units:
        fp = unit.get("floorPlan") or {}
        plan_name = (fp.get("name") or "").strip()
        if not plan_name:
            continue

        beds_raw = unit.get("bedroomNumber", 0)
        try:
            beds = float(beds_raw)
        except (TypeError, ValueError):
            beds = 0.0

        baths_raw = unit.get("bathroomNumber", 1)
        try:
            baths = float(baths_raw)
        except (TypeError, ValueError):
            baths = 1.0

        sqft_raw = unit.get("squareFeet")
        try:
            sqft = int(sqft_raw) if sqft_raw else None
        except (TypeError, ValueError):
            sqft = None

        # Price: startingAtPricesUnfurnished.prices.netEffectivePrice
        price: Optional[float] = None
        pricing = unit.get("startingAtPricesUnfurnished") or {}
        if isinstance(pricing, dict):
            prices_inner = pricing.get("prices") or {}
            if isinstance(prices_inner, dict):
                raw_p = (
                    prices_inner.get("netEffectivePrice")
                    or prices_inner.get("price")
                    or prices_inner.get("totalPrice")
                )
                if raw_p is not None:
                    try:
                        price = float(raw_p)
                    except (TypeError, ValueError):
                        price = None

        status = unit.get("unitStatus", "")
        is_available = status in ("VacantAvailable", "Available", "")

        if plan_name not in plans:
            plans[plan_name] = {
                "plan_name": plan_name,
                "bedrooms": beds,
                "bathrooms": baths,
                "size_sqft": sqft,
                "price": price if is_available else None,
                "availability": "available" if is_available else "unavailable",
            }
        else:
            existing = plans[plan_name]
            # Update sqft if we now have it
            if existing["size_sqft"] is None and sqft is not None:
                existing["size_sqft"] = sqft
            # Keep the cheapest available price
            if is_available and price is not None:
                if existing["price"] is None or price < existing["price"]:
                    existing["price"] = price
                existing["availability"] = "available"

    result = list(plans.values())
    logger.debug(
        "AvalonBayAdapter: parsed %d units → %d distinct plans", len(raw_units), len(result)
    )
    return result


class AvalonBayAdapter(PlatformAdapter):
    """Adapter for AvalonBay Communities properties (Avalon and AVA brands)."""

    name = "avalonbay"

    def __init__(self) -> None:
        self._units: List[Dict] = []

    def detect(self, html: str, url: str) -> bool:
        if "avaloncommunities.com" in url:
            self._units = _parse_avalon_global_content(html) if html else []
            return True

        if html and _FUSION_CONTENT_RE.search(html):
            units = _parse_avalon_global_content(html)
            if units:
                self._units = units
                return True

        return False

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        units = list(self._units)
        if not units:
            units = _parse_avalon_global_content(html)

        n_priced = sum(1 for u in units if u["price"] is not None)
        logger.info(
            "AvalonBayAdapter: %d plans (%d priced) from static HTML at %s",
            len(units), n_priced, url,
        )
        return units
