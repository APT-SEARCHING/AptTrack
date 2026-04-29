"""Equity Residential (equityapartments.com) platform adapter.

Floor plan and unit data is embedded in the static HTML as a JavaScript
variable: ``ea5.unitAvailability = {...}``.  The JSON contains
BedroomTypes → AvailableUnits with FloorplanName, SqFt, Bed, Bath,
BestTerm.Price, and AvailableDate.  No Playwright or API calls required.

detect() fires when ``ea5.unitAvailability`` appears in the page HTML AND
the domain is equityapartments.com.  The presence of that variable is the
definitive signal — it is injected by Equity's Angular app on property
detail pages only (not on search/home pages).
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

_EA5_RE = re.compile(r"ea5\.unitAvailability\s*=\s*(\{.*?\});\s*\n", re.S)
_DETECT_SIGNAL = "ea5.unitAvailability"


def _parse_equity_unit_availability(html: str) -> List[dict]:
    """Extract floor plans from the ``ea5.unitAvailability`` JSON blob.

    Groups individual unit rows by (FloorplanId, FloorplanName) and returns
    one dict per floor plan type with the minimum available price.
    """
    m = _EA5_RE.search(html)
    if not m:
        return []

    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        logger.warning("Equity: failed to parse ea5.unitAvailability JSON: %s", exc)
        return []

    # Group units by floor plan — one plan row per (FloorplanId, FloorplanName)
    plans: Dict[str, dict] = {}  # key: FloorplanId

    for bt in data.get("BedroomTypes", []):
        for unit in bt.get("AvailableUnits", []):
            fp_id = unit.get("FloorplanId") or unit.get("FloorplanName", "")
            fp_name = unit.get("FloorplanName") or ""
            price = unit.get("BestTerm", {}).get("Price")
            sqft = unit.get("SqFt")
            beds = unit.get("Bed")
            baths = unit.get("Bath")
            avail_raw = unit.get("AvailableDate")  # e.g. "6/12/2026"

            avail_iso: Optional[str] = None
            if avail_raw:
                try:
                    parts = avail_raw.split("/")
                    if len(parts) == 3:
                        m_part, d_part, y_part = parts
                        avail_iso = f"{y_part}-{m_part.zfill(2)}-{d_part.zfill(2)}"
                except Exception:
                    pass

            if fp_id not in plans:
                plans[fp_id] = {
                    "plan_name": fp_name,
                    "bedrooms": float(beds) if beds is not None else None,
                    "bathrooms": float(baths) if baths is not None else None,
                    "size_sqft": float(sqft) if sqft else None,
                    "price": price,
                    "available_from": avail_iso,
                    "availability": "available",
                }
            else:
                # Keep minimum price across units of the same floor plan
                existing = plans[fp_id]
                if price is not None:
                    if existing["price"] is None or price < existing["price"]:
                        existing["price"] = price
                        existing["available_from"] = avail_iso
                # Fill in sqft/beds/baths if missing
                if existing["size_sqft"] is None and sqft:
                    existing["size_sqft"] = float(sqft)
                if existing["bedrooms"] is None and beds is not None:
                    existing["bedrooms"] = float(beds)
                if existing["bathrooms"] is None and baths is not None:
                    existing["bathrooms"] = float(baths)

    result = list(plans.values())
    logger.info("Equity: parsed %d floor plan types from ea5.unitAvailability", len(result))
    return result


class EquityAdapter(PlatformAdapter):
    """Adapter for Equity Residential properties on equityapartments.com."""

    name = "equity"

    def detect(self, html: str, url: str) -> bool:
        if not html:
            return False
        if "equityapartments.com" not in url.lower():
            return False
        return _DETECT_SIGNAL in html

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        plans = _parse_equity_unit_availability(html)
        if not plans:
            logger.warning("Equity: no floor plans extracted from %s", url)
        return plans
