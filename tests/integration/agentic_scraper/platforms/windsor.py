"""Windsor Communities (Spaces/Nestio) platform adapter.

Windsor-managed properties (windsorcommunities.com) use the Spaces/Nestio
leasing widget.  The homepage carries no unit data, but the /floorplans/
sub-page embeds every available unit as an <article> element with rich
data-spaces-* attributes in the static HTML:

    data-spaces-sort-plan-name  → plan letter (e.g. "A", "C", "G")
    data-spaces-sort-price      → rent in dollars (int)
    data-spaces-sort-area       → sqft (int)
    data-spaces-sort-bed        → bedrooms (0 = studio)
    data-spaces-sort-bath       → bathrooms (float)
    data-spaces-available       → "true" / "false"

No Playwright or JavaScript execution is required.  The adapter fetches
the /floorplans/ URL directly via urllib, then groups units by plan name
and keeps the minimum price across available units.

detect() fires when:
  - The URL host contains "windsorcommunities.com", OR
  - The page HTML contains a link to a windsorcommunities.com …/floorplans/ page.

Both the Windsor Winchester and Cannery Park by Windsor properties use the
same windsorcommunities.com structure (Cannery Park's brand front at
canneryparkbywindsor.com redirects to windsorcommunities.com, so the
agent already sees the correct host by the time detect() is called).
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_FLOORPLANS_LINK_RE = re.compile(
    r'https://www\.windsorcommunities\.com/properties/[^"\']+/floorplans/',
    re.IGNORECASE,
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)


def _floorplans_url_from(page_url: str, html: str) -> Optional[str]:
    """Derive the /floorplans/ URL to fetch.

    Strategy:
      1. If page_url itself is already a windsorcommunities.com URL that
         contains /properties/<slug>/, append /floorplans/ to the path.
      2. Fall back to scanning the homepage HTML for a full floorplans link.
    """
    parsed = urlparse(page_url)
    if "windsorcommunities.com" in parsed.netloc:
        # Extract /properties/<slug>/ segment
        m = re.search(r"/properties/[^/?#]+", parsed.path)
        if m:
            base = f"https://www.windsorcommunities.com{m.group(0).rstrip('/')}/"
            return base + "floorplans/"

    # Fall back: scan HTML for the canonical floorplans link
    m = _FLOORPLANS_LINK_RE.search(html or "")
    if m:
        return m.group(0)

    return None


def _fetch_html(url: str) -> Optional[str]:
    """Fetch URL with a simple urllib GET; return decoded HTML or None on error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read(600_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("WindsorAdapter: HTTP fetch failed for %s: %s", url, exc)
        return None


def _parse_windsor_floorplans(html: str) -> List[Dict]:
    """Parse Windsor /floorplans/ HTML and return per-plan unit dicts.

    Reads data-spaces-* attributes from every <article> with
    data-spaces-obj="unit", then groups units by plan name and keeps
    the cheapest available price.
    """
    articles = re.findall(
        r'<article[^>]*data-spaces-obj=["\']unit["\'][^>]*>',
        html,
    )
    if not articles:
        return []

    def _attr(tag: str, name: str) -> Optional[str]:
        m = re.search(rf'data-spaces-{re.escape(name)}=["\']([^"\']+)["\']', tag)
        return m.group(1) if m else None

    # plan_name → aggregated info
    plans: Dict[str, Dict] = {}

    for tag in articles:
        plan_name = _attr(tag, "sort-plan-name")
        if not plan_name:
            continue

        available_raw = _attr(tag, "available")
        is_available = available_raw == "true"

        price_raw = _attr(tag, "sort-price")
        try:
            price: Optional[float] = float(price_raw) if price_raw else None
        except (ValueError, TypeError):
            price = None

        sqft_raw = _attr(tag, "sort-area")
        try:
            sqft: Optional[int] = int(sqft_raw) if sqft_raw else None
        except (ValueError, TypeError):
            sqft = None

        beds_raw = _attr(tag, "sort-bed")
        try:
            beds: float = float(beds_raw) if beds_raw is not None else 0.0
        except (ValueError, TypeError):
            beds = 0.0

        baths_raw = _attr(tag, "sort-bath")
        try:
            baths: float = float(baths_raw) if baths_raw is not None else 1.0
        except (ValueError, TypeError):
            baths = 1.0

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
            # Fill sqft if not yet seen for this plan
            if existing["size_sqft"] is None and sqft is not None:
                existing["size_sqft"] = sqft
            # Track cheapest available price
            if is_available and price is not None:
                if existing["price"] is None or price < existing["price"]:
                    existing["price"] = price
                existing["availability"] = "available"

    result = list(plans.values())
    logger.debug(
        "WindsorAdapter: parsed %d articles → %d distinct plans",
        len(articles), len(result),
    )
    return result


class WindsorAdapter(PlatformAdapter):
    """Adapter for Windsor Communities properties (Spaces/Nestio platform)."""

    name = "windsor"

    def __init__(self) -> None:
        self._floorplans_url: Optional[str] = None

    def detect(self, html: str, url: str) -> bool:
        parsed = urlparse(url)
        if "windsorcommunities.com" in parsed.netloc:
            self._floorplans_url = _floorplans_url_from(url, html)
            return True

        # HTML-based: homepage links to a windsorcommunities.com floorplans page
        if html and _FLOORPLANS_LINK_RE.search(html):
            self._floorplans_url = _floorplans_url_from(url, html)
            return True

        return False

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        fp_url = self._floorplans_url or _floorplans_url_from(url, html)
        if not fp_url:
            logger.warning("WindsorAdapter: could not derive floorplans URL from %s", url)
            return []

        logger.info("WindsorAdapter: fetching floorplans page %s", fp_url)
        fp_html = _fetch_html(fp_url)
        if not fp_html:
            return []

        units = _parse_windsor_floorplans(fp_html)
        n_priced = sum(1 for u in units if u["price"] is not None)
        logger.info(
            "WindsorAdapter: %d plans (%d priced) from %s",
            len(units), n_priced, fp_url,
        )
        return units
