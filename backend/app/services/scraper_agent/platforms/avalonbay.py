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

    Returns one dict per individual unit (not per plan) so that per-unit
    prices, unit numbers, and availability dates are preserved and can be
    shown in the dropdown UI — matching the SightMap pattern.
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

    result = []
    for unit in raw_units:
        fp = unit.get("floorPlan") or {}
        plan_name = (fp.get("name") or "").strip()
        if not plan_name:
            continue

        unit_number = str(unit.get("unitName") or "").strip() or None

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

        floor_raw = unit.get("floorNumber")
        try:
            floor = int(floor_raw) if floor_raw else None
        except (TypeError, ValueError):
            floor = None

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

        # Availability date from unit or pricing block
        avail_date = (
            unit.get("availableDateUnfurnished")
            or pricing.get("moveInDate")
        )
        if avail_date:
            # ISO date string → "Available YYYY-MM-DD" for _parse_availability
            avail_date = str(avail_date)[:10]  # keep YYYY-MM-DD only
            availability = "Available {}".format(avail_date)
        else:
            availability = "Available Now"

        status = unit.get("unitStatus", "")
        is_available = status in ("VacantAvailable", "Available", "NoticeAvailable", "")
        if not is_available:
            availability = "unavailable"

        result.append({
            "plan_name": plan_name,
            "unit_number": unit_number,
            "bedrooms": beds,
            "bathrooms": baths,
            "size_sqft": sqft,
            "floor_level": floor,
            "price": price if is_available else None,
            "availability": availability,
        })

    logger.debug(
        "AvalonBayAdapter: parsed %d raw units → %d unit entries", len(raw_units), len(result)
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
