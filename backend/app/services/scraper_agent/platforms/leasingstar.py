"""RealPage / LeaseStar platform adapter.

RealPage-managed properties (e.g. 121 Tasman) embed a LeaseStar leasing
widget on their CMS page.  The property ID is available in the static HTML
as a JavaScript variable:

    var propertyId='5551678';
    var lsApi='https://c-leasestar-api.realpage.com';

The LeaseStar CAPI endpoint returns all floor plans as structured JSON at no
cost:

    https://capi.myleasestar.com/v2/property/{propertyId}/floorplans

Fields used:
    name                → plan name (e.g. "E1", "A2")
    bedRooms            → "S" (studio=0) or "1"/"2" (int/float)
    bathRooms           → "1"/"2" (float)
    minimumSquareFeet   → sqft
    minimumMarketRent   → starting price in USD

No Playwright or JavaScript execution is required — all data is in the
public CAPI JSON.

detect() fires when the page HTML contains both:
  - ``var propertyId='<digits>'``
  - ``c-leasestar-api.realpage.com`` or ``myleasestar.com``
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, List, Optional

from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_PROPERTY_ID_RE = re.compile(r"var\s+propertyId\s*=\s*'(\d+)'")
_LEASINGSTAR_SIGNAL_RE = re.compile(
    r"(?:c-leasestar-api\.realpage\.com|myleasestar\.com)", re.I
)
_CAPI_URL = "https://capi.myleasestar.com/v2/property/{property_id}/floorplans"
_HEADERS = {
    "User-Agent": (
        "AptTrack/1.0 (rental price transparency tool; contact@apttrack.app)"
    ),
    "Accept": "application/json",
}


def _fetch_leasingstar_plans(property_id: str) -> List[dict]:
    """Call the LeaseStar CAPI and return a list of normalised plan dicts."""
    url = _CAPI_URL.format(property_id=property_id)
    req = urllib.request.Request(url, headers=_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", errors="ignore"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        logger.warning("LeaseStar CAPI fetch failed for property %s: %s", property_id, exc)
        return []

    plans: List[dict] = []
    for fp in data.get("floorplans", []):
        name = (fp.get("name") or "").strip()
        if not name:
            continue

        # bedRooms: "S" = studio (0), else parse as int/float
        bed_raw = fp.get("bedRooms", "")
        if isinstance(bed_raw, str) and bed_raw.upper() in ("S", "STUDIO"):
            beds: Optional[float] = 0.0
        else:
            try:
                beds = float(bed_raw)
            except (TypeError, ValueError):
                beds = None

        # bathRooms: "1", "1.5", "2", etc.
        try:
            baths: Optional[float] = float(fp.get("bathRooms") or 0) or None
        except (TypeError, ValueError):
            baths = None

        sqft_min = fp.get("minimumSquareFeet")
        sqft: Optional[float] = float(sqft_min) if sqft_min else None

        price_raw = fp.get("minimumMarketRent")
        price: Optional[float] = float(price_raw) if price_raw else None

        plans.append({
            "plan_name": name,
            "bedrooms": beds,
            "bathrooms": baths,
            "size_sqft": sqft,
            "price": price,
            "availability": "Available" if price else None,
        })

    return plans


class LeasingStarAdapter(PlatformAdapter):
    """Adapter for RealPage / LeaseStar managed properties."""

    name = "leasingstar"

    def __init__(self) -> None:
        self._property_id: Optional[str] = None

    def detect(self, html: str, url: str) -> bool:
        if not html:
            return False
        if not _LEASINGSTAR_SIGNAL_RE.search(html):
            return False
        m = _PROPERTY_ID_RE.search(html)
        if not m:
            return False
        self._property_id = m.group(1)
        logger.info("LeaseStar property detected: id=%s url=%s", self._property_id, url)
        return True

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        property_id = self._property_id
        if not property_id:
            m = _PROPERTY_ID_RE.search(html or "")
            if m:
                property_id = m.group(1)
        if not property_id:
            return []
        plans = _fetch_leasingstar_plans(property_id)
        logger.info("LeaseStar extracted %d plans for property %s", len(plans), property_id)
        return plans
