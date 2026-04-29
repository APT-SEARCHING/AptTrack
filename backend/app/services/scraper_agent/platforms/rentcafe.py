"""RentCafe / Yardi platform adapter.

RentCafe (Yardi's SaaS CMS, hosted on rentcafe.com) is used by Mode Apartments,
Viewpoint, Tan Plaza, and many other Bay Area properties.  The floor plan data
is server-side rendered on the ``/floorplans`` subpage in two places:

1. Card header text: ``"L | 3 | Bed | 2 | Bath | Inquire for details"``
   → plan name, bed count, bath count, availability

2. Guided-tour onclick: ``setGA4Cookie('GT','L','3','1449','1449','6072','8306')``
   → plan name, beds, sqft, sqft (repeated), price_min, price_max

Availability comes from ``<span class="fp-availability">N Available</span>``
or fallback text in the card.

No Playwright or API call required — all data is in the static HTML.

detect() fires when the page HTML contains ``cdngeneralmvc.rentcafe.com`` or
``api.rentcafe.com`` (both are loaded on every page of a RentCafe site).
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_RENTCAFE_RE = re.compile(r"(?:cdngeneralmvc|api)\.rentcafe\.com", re.I)
# setGA4Cookie('GT', 'L', '3', '1449', '1449', '6072', '8306')
_GA4_RE = re.compile(
    r"setGA4Cookie\('GT',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)',\s*'([^']+)'\)",
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def _floorplans_url(page_url: str) -> str:
    """Return the /floorplans URL for a RentCafe property page."""
    p = urlparse(page_url)
    base = f"{p.scheme}://{p.netloc}"
    return urljoin(base, "/floorplans")


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read(600_000)
        if r.headers.get("Content-Encoding", "") == "gzip":
            import gzip as _gzip
            raw = _gzip.decompress(raw)
        return raw.decode("utf-8", errors="ignore")


def _parse_rentcafe_floorplans(html: str) -> List[dict]:
    """Extract floor plans from a RentCafe /floorplans page.

    Handles three RentCafe card variants:
    - Mode/standard:  ``data-floorplan-id`` span in card header
                      text: ``"L | 3 | Bed | 2 | Bath | Inquire"``
    - Viewpoint:      same structure but long names like
                      ``"Studio Affordable (All Floor Plans) | Studio | 1 | Bath"``
    - Tan Plaza:      ``<h2>1A</h2>`` in card, text: ``"1A | 1 | Bed | 1 | Bath | 854 Sq. Ft."``
    """
    soup = BeautifulSoup(html, "html.parser")

    # --- Step 1: build sqft + price map from setGA4Cookie calls ---
    # setGA4Cookie('GT', name, beds, sqft_min, sqft_max, price_min, price_max)
    ga4: Dict[str, dict] = {}
    for m in _GA4_RE.finditer(html):
        name, beds_s, sqft_min_s, _sqft_max_s, price_min_s, price_max_s = m.groups()
        if name in ga4:
            continue  # each plan appears twice on the page
        try:
            ga4[name] = {
                "bedrooms": float(beds_s),
                "size_sqft": float(sqft_min_s) if sqft_min_s and sqft_min_s != "0" else None,
                "min_price": float(price_min_s) if price_min_s and price_min_s != "0" else None,
                "max_price": float(price_max_s) if price_max_s and price_max_s != "0" else None,
            }
        except (ValueError, TypeError):
            continue

    # --- Step 2: find card containers ---
    # Two strategies: data-floorplan-id spans (Mode/Viewpoint) or h2 in cards (Tan Plaza)
    card_containers = []

    fp_spans = soup.find_all("span", attrs={"data-floorplan-id": True})
    if fp_spans:
        for span in fp_spans:
            container = span.parent
            for _ in range(8):
                if container is None:
                    break
                if any("card" in c.lower() for c in container.get("class", [])):
                    break
                container = container.parent
            if container is not None:
                card_containers.append(container)
    else:
        # Fallback: h2 elements inside card divs (Tan Plaza layout)
        for h2 in soup.find_all("h2"):
            name_text = h2.get_text(strip=True)
            if not name_text or name_text.lower() in ("filters", "no matches"):
                continue
            container = h2.parent
            for _ in range(8):
                if container is None:
                    break
                if any("card" in c.lower() for c in container.get("class", [])):
                    break
                container = container.parent
            if container is not None:
                card_containers.append(container)

    # --- Step 3: parse each card ---
    plans: List[dict] = []
    seen: set = set()

    for container in card_containers:
        text = container.get_text(separator="|", strip=True)
        tokens = [t.strip() for t in text.split("|") if t.strip()]

        # Plan name: first non-trivial token before "Bed" or "Bath"
        name: Optional[str] = None
        for i, tok in enumerate(tokens):
            if tok.lower() in ("bed", "bath", "studio", "inquire", "filters"):
                break
            if tok and len(tok) >= 1 and not re.match(r"^\d+$", tok):
                name = tok
                break
        if not name or name in seen:
            continue
        seen.add(name)

        # Bath count: numeric token immediately before "Bath"
        baths: Optional[float] = None
        for i, tok in enumerate(tokens):
            if tok.lower() == "bath" and i > 0:
                try:
                    baths = float(tokens[i - 1])
                except (ValueError, IndexError):
                    pass
                break

        # Sqft: from card text "NNN Sq. Ft." (fallback to GA4)
        sqft_m = re.search(r"([\d,]+)\s*Sq\.?\s*Ft\.", text, re.I)
        sqft_from_card: Optional[float] = float(sqft_m.group(1).replace(",", "")) if sqft_m else None

        # Availability: fp-availability span or text pattern
        avail_span = container.find("span", class_="fp-availability")
        if avail_span:
            availability: Optional[str] = avail_span.get_text(strip=True) or None
        else:
            avail_m = re.search(r"(\d+\s+Available|Inquire for details|Call for details|Waitlist)", text, re.I)
            availability = avail_m.group(1) if avail_m else None

        # GA4 data takes precedence for beds/sqft/price; card fills in baths
        ga = ga4.get(name, {})
        price = ga.get("min_price")
        sqft = ga.get("size_sqft") or sqft_from_card
        beds = ga.get("bedrooms")

        # Beds from name when GA4 is absent: "Studio"→0, "1 Bedroom"→1, etc.
        if beds is None:
            if re.search(r"\bstudio\b", name, re.I):
                beds = 0.0
            else:
                bed_m = re.search(r"(\d+)\s*Bedroom", name, re.I)
                if bed_m:
                    beds = float(bed_m.group(1))

        # Skip aggregate "All Floor Plans" rows that have no sqft AND no price
        if sqft is None and price is None:
            continue

        plans.append({
            "plan_name": name,
            "bedrooms": beds,
            "bathrooms": baths,
            "size_sqft": sqft,
            "price": price,
            "availability": availability,
        })

    return plans


class RentCafeAdapter(PlatformAdapter):
    """Adapter for Yardi RentCafe managed properties."""

    name = "rentcafe"

    def __init__(self) -> None:
        self._floorplans_url: Optional[str] = None

    def detect(self, html: str, url: str) -> bool:
        if not html:
            return False
        if not _RENTCAFE_RE.search(html):
            return False
        self._floorplans_url = _floorplans_url(url)
        logger.info("RentCafe detected at %s → %s", url, self._floorplans_url)
        return True

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        fp_url = self._floorplans_url or _floorplans_url(url)
        try:
            fp_html = _fetch_html(fp_url)
        except (urllib.error.URLError, OSError) as exc:
            logger.warning("RentCafe: failed to fetch %s: %s", fp_url, exc)
            return []
        plans = _parse_rentcafe_floorplans(fp_html)
        logger.info("RentCafe extracted %d plans from %s", len(plans), fp_url)
        return plans
