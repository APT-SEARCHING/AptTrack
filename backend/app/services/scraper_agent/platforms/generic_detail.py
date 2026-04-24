"""Generic static-detail-page platform adapter.

Detects apartment sites that expose per-plan static detail pages via
standard URL path patterns (e.g. /floorplans/SLUG/, /plans/SLUG/).
Fetches all matching hrefs concurrently via aiohttp and parses each
page with a flexible regex-per-field parser that handles both
Jonah-Digital-style (h1 name, $ price) and FatWin-style (title name,
N Bedroom | N Bath | NNN SF) pages.

This adapter runs AFTER the dedicated CMS adapters (Jonah Digital,
FatWin, SightMap) so it only fires when none of those match.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_USER_AGENT = "AptTrack/1.0 (rental price transparency tool; contact@apttrack.app)"

# ---------------------------------------------------------------------------
# URL path patterns that indicate a per-plan static detail page.
# Require at least 2 characters after the final slash to avoid matching
# bare listing pages like /floorplans/ or /plans/.
# ---------------------------------------------------------------------------
_FLOORPLAN_HREF_RE: List[re.Pattern] = [
    re.compile(r"/floor-?plans?/[^/?#]{2,}/?$", re.I),   # /floorplans/a1/, /floor-plans/studio/
    re.compile(r"/plans?/[^/?#]{2,}/?$", re.I),           # /plans/studio/, /plan/a1/
    re.compile(r"/residences?/[^/?#]{2,}/?$", re.I),      # /residences/penthouse/
    re.compile(r"/[^/?#]+/plan-[^/?#]+/?$", re.I),        # /apartments/lincoln/plan-a1/
]

# At least this many matching hrefs must be found before firing.
# Prevents false positives from a single stray /plans/ nav link.
_MIN_LINKS = 2

# Plan names that are actually UI verbs or affordances — blacklisted.
_PLAN_NAME_BLACKLIST = re.compile(
    r"^(favorite|tour now|view detail[s]?|schedule(?: a)? tour|contact us?|"
    r"apply(?: now)?|get directions?|learn more|see all|show more|back to)$",
    re.I,
)


def _extract_generic_hrefs(html: str, base_url: str) -> List[str]:
    """Return deduplicated absolute floor-plan detail URLs from the page HTML."""
    seen: set = set()
    hrefs: List[str] = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        abs_url = urljoin(base_url, href)
        path = urlparse(abs_url).path
        if any(pat.search(path) for pat in _FLOORPLAN_HREF_RE):
            if abs_url not in seen:
                seen.add(abs_url)
                hrefs.append(abs_url)
    return hrefs


def _parse_generic_detail(html: str, detail_url: str) -> Optional[Dict]:
    """Parse a static floor-plan detail page into a unit dict.

    Tries strategies in order of reliability:
      Name  : h1/h2/h3 → <title> first segment → URL slug
      Beds  : "N bed[room]" regex, Studio keyword
      Sqft  : "NNN sq ft / SF / square feet" regex
      Price : first $ amount in $500–$20,000 range
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    # --- Plan name ---
    name: Optional[str] = None

    # Try h1/h2/h3 first (Jonah Digital style)
    for tag in soup.find_all(["h1", "h2", "h3"]):
        t = tag.get_text(strip=True)
        if (
            t
            and 1 < len(t) < 80
            and not re.search(r"floor\s*plan|available|contact|schedule|tour|apply", t, re.I)
            and not _PLAN_NAME_BLACKLIST.match(t)
        ):
            name = t
            break

    # Try <title> first segment (FatWin style)
    if not name:
        title_tag = soup.find("title")
        if title_tag:
            raw = title_tag.get_text(strip=True).split("|")[0].strip()
            if raw and len(raw) < 80 and not _PLAN_NAME_BLACKLIST.match(raw):
                name = raw

    # URL slug fallback
    if not name:
        name = urlparse(detail_url).path.rstrip("/").rsplit("/", 1)[-1]

    # --- Bedrooms ---
    beds: float = 0.0
    m = re.search(r"(\d+)\s*(?:bed(?:room)?s?)\b", text, re.I)
    if m:
        beds = float(m.group(1))
    elif re.search(r"\bstudio\b", text, re.I):
        beds = 0.0

    # --- Sqft (handles "NNN sq ft", "NNN SF", "NNN sq. ft.", "NNN square feet") ---
    sqft: Optional[float] = None
    m = re.search(r"([\d,]+)\s*(?:sq\.?\s*(?:ft\.?|feet)|SF)\b", text, re.I)
    if m:
        sqft = float(m.group(1).replace(",", ""))

    # --- Price (first plausible rent in $500–$20,000) ---
    price: Optional[float] = None
    for lo_str, _ in re.findall(r"\$([\d,]+)(?:\s*[-–]\s*\$([\d,]+))?", text):
        lo = int(lo_str.replace(",", ""))
        if 500 <= lo <= 20_000:
            price = float(lo)
            break

    return {
        "plan_name": name,
        "bedrooms": beds,
        "size_sqft": sqft,
        "price": price,
        "availability": "available",
    }


async def _fetch_generic_plans(
    hrefs: List[str],
    session: aiohttp.ClientSession,
    concurrency: int = 5,
) -> List[Dict]:
    """Fetch detail pages in parallel and return parsed unit dicts."""
    sem = asyncio.Semaphore(concurrency)
    results: List[Dict] = []

    async def _fetch_one(url: str) -> None:
        async with sem:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return
                    html = await resp.text(errors="replace")
                unit = _parse_generic_detail(html, url)
                if unit is not None:
                    results.append(unit)
            except Exception:
                pass

    await asyncio.gather(*[_fetch_one(u) for u in hrefs])
    return results


class GenericDetailPageAdapter(PlatformAdapter):
    """Adapter for sites with per-plan static detail pages linked from the listing page."""

    name = "generic_detail"

    def __init__(self) -> None:
        # Cache hrefs found during detect() so extract() doesn't re-parse HTML.
        self._hrefs: List[str] = []

    def detect(self, html: str, url: str) -> bool:
        if not html:
            self._hrefs = []
            return False
        self._hrefs = _extract_generic_hrefs(html, url)
        return len(self._hrefs) >= _MIN_LINKS

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        hrefs = self._hrefs
        if not hrefs:
            return []
        logger.info(
            "GenericDetailPage: %d plan links found at %s — fetching concurrently",
            len(hrefs),
            url,
        )
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            headers={"User-Agent": _USER_AGENT},
        ) as session:
            units = await _fetch_generic_plans(hrefs, session)

        # Soft-404 guard: if ≥3 results share the same plan_name (>50% of batch),
        # every detail page returned the same error/redirect page — discard the batch.
        if len(units) >= 3:
            from collections import Counter
            name_counts = Counter(u.get("plan_name") for u in units)
            most_common_name, most_common_count = name_counts.most_common(1)[0]
            if most_common_count / len(units) > 0.5:
                logger.warning(
                    "GenericDetailPage: %s — %d/%d units share plan_name %r; "
                    "soft-404 suspected, discarding batch",
                    url, most_common_count, len(units), most_common_name,
                )
                return []

        return units
