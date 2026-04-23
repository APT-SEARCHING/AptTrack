"""Greystar corporate platform adapter.

Greystar-managed properties (e.g. 121 Tasman) have brand-front subdomains
that serve JavaScript-rendered placeholders.  Their corporate listing pages
at greystar.com/properties/<path>/floorplans are Next.js SSG pages.

Extraction strategy (two phases):

  Phase 1 — Static JSON-LD (always runs, 0 browser cost)
    The SSG HTML contains a <script type="application/ld+json"> block with a
    LodgingBusiness object whose `containsPlace` array lists every floor plan
    as an Accommodation item.  Fields available: name, numberOfBedrooms,
    numberOfBathroomsTotal.  Price and sqft are NOT in the static HTML.

  Phase 2 — Playwright hydration (runs when browser is available)
    React hydrates the page client-side and renders floor-plan cards with
    price ranges.  We navigate, wait for the loading placeholder to disappear,
    then parse the rendered DOM for price text and match it back to plan names
    from Phase 1.  sqft is not exposed by Greystar in any public data source.

detect() fires when:
  - The URL contains greystar.com/properties/, OR
  - The static HTML contains a LodgingBusiness JSON-LD with containsPlace.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Dict, List, Optional

from bs4 import BeautifulSoup

from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

# Minimum number of Accommodation items required to consider detection valid.
_MIN_PLANS = 1


def _parse_greystar_jsonld(html: str) -> List[Dict]:
    """Extract floor-plan unit dicts from the schema.org JSON-LD in static HTML.

    Returns a list of unit dicts with plan_name / bedrooms / bathrooms.
    price and size_sqft are left None — filled in by Phase 2 if available.
    """
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", type="application/ld+json")
    if not script or not script.string:
        return []

    try:
        data = json.loads(script.string)
    except (json.JSONDecodeError, ValueError):
        return []

    if data.get("@type") != "LodgingBusiness":
        return []

    units: List[Dict] = []
    for place in data.get("containsPlace", []):
        if place.get("@type") != "Accommodation":
            continue
        name = place.get("name", "").strip()
        if not name:
            continue
        beds_raw = place.get("numberOfBedrooms", 0)
        try:
            beds = float(beds_raw)
        except (TypeError, ValueError):
            beds = 0.0
        baths_raw = place.get("numberOfBathroomsTotal", 1)
        try:
            baths = float(baths_raw)
        except (TypeError, ValueError):
            baths = 1.0

        units.append({
            "plan_name": name,
            "bedrooms": beds,
            "bathrooms": baths,
            "size_sqft": None,   # not in Greystar public data
            "price": None,       # filled by Phase 2
            "availability": "available",
        })
    return units


def _merge_prices_from_rendered(units: List[Dict], rendered_html: str) -> List[Dict]:
    """Attempt to read prices from the Playwright-rendered DOM and attach them
    to the matching units from Phase 1.

    Greystar renders floor-plan cards after React hydration.  The exact DOM
    structure varies but prices appear as "$N,NNN/mo" or "$N,NNN - $N,NNN/mo"
    text.  We use two complementary strategies:

      A. Named-card matching — find a price that appears close (within 500 chars)
         to each plan name in the rendered text.
      B. Global harvest — if named matching yields no prices, harvest all
         plausible rent amounts and distribute them in list order.

    sqft remains None: Greystar does not expose sqft in any public-facing page.
    """
    soup = BeautifulSoup(rendered_html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    # Strategy A: find each plan name in rendered text, search nearby for price
    price_pattern = re.compile(r"\$([\d,]+)(?:\s*[-–]\s*\$([\d,]+))?(?:/mo|\s*per\s*month)?", re.I)
    updated = []
    for unit in units:
        name = unit["plan_name"]
        idx = text.find(name)
        if idx != -1:
            window = text[idx: idx + 600]
            m = price_pattern.search(window)
            if m:
                lo = int(m.group(1).replace(",", ""))
                if 500 <= lo <= 20_000:
                    unit = {**unit, "price": float(lo)}
        updated.append(unit)

    # Strategy B: if none got prices, harvest all rent amounts and assign in order
    if all(u["price"] is None for u in updated):
        prices: List[float] = []
        for m in price_pattern.finditer(text):
            lo = int(m.group(1).replace(",", ""))
            if 500 <= lo <= 20_000:
                prices.append(float(lo))
        if prices:
            logger.debug(
                "Greystar: named-card match found no prices; distributing %d harvested prices "
                "across %d plans", len(prices), len(updated)
            )
            for i, unit in enumerate(updated):
                if i < len(prices):
                    updated[i] = {**unit, "price": prices[i]}

    return updated


class GreystarAdapter(PlatformAdapter):
    """Adapter for Greystar-managed properties at greystar.com/properties/."""

    name = "greystar"

    def __init__(self) -> None:
        self._static_units: List[Dict] = []

    def detect(self, html: str, url: str) -> bool:
        # URL-based detection (fires when corporate_parent_url redirect has already run)
        if "greystar.com/properties/" in url:
            self._static_units = _parse_greystar_jsonld(html) if html else []
            return True

        # HTML-based detection (LodgingBusiness JSON-LD with containsPlace)
        if html:
            units = _parse_greystar_jsonld(html)
            if len(units) >= _MIN_PLANS:
                self._static_units = units
                return True

        return False

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        units = list(self._static_units)
        if not units:
            # Fallback: re-parse in case detect() was called on a different html
            units = _parse_greystar_jsonld(html)
        if not units:
            return []

        logger.info(
            "GreystarAdapter: %d plans from JSON-LD at %s; navigating for prices",
            len(units), url,
        )

        # Phase 2: Playwright hydration for prices
        try:
            state = await browser.navigate_to(url)
            if state.get("error"):
                logger.warning(
                    "GreystarAdapter: Playwright navigate failed (%s) — returning plans without prices",
                    state["error"],
                )
                return units

            # Wait for the loading placeholder to disappear (React hydration complete)
            try:
                await browser.page.wait_for_function(
                    "() => !document.body.innerText.includes('Loading component')",
                    timeout=12_000,
                )
            except Exception:
                pass  # Proceed — page may already be hydrated or placeholder never appeared

            # Extra buffer for post-hydration XHR (propertyUnits fetch)
            await asyncio.sleep(3)

            rendered_html = await browser.page.content()
            units = _merge_prices_from_rendered(units, rendered_html)

            n_priced = sum(1 for u in units if u["price"] is not None)
            logger.info(
                "GreystarAdapter: %d/%d plans priced after hydration", n_priced, len(units)
            )
        except Exception as exc:
            logger.warning(
                "GreystarAdapter: Phase 2 Playwright error (%s) — returning plans without prices",
                exc,
            )

        return units
