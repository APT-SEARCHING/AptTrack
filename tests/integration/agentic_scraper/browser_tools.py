"""Playwright-based browser session used by the apartment agent as tool implementations."""

from __future__ import annotations

import asyncio
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Frame, Page, async_playwright

# Caps to keep tool-result payloads manageable for the LLM
MAX_TEXT_CHARS = 4000   # reduced from 8000 — saves ~20-30% input tokens
MAX_LINKS = 20          # reduced from 50
MAX_BUTTONS = 15        # reduced from 40

# Keywords that indicate pricing-relevant content — these lines are
# prioritised when truncating page text so the model sees them first.
_PRICING_KEYWORDS = [
    "$", "bed", "bath", "sqft", "sq ft", "sq. ft", "sq.ft", "plan", "studio",
    "available", "price", "rent", "floor", "unit", "home",
]

# UI labels that SightMap (and similar widgets) inject as the first line of a
# unit block.  Must never be captured as a floor-plan name.
_UI_VERB_BLACKLIST = frozenset({
    "favorite", "available", "available now", "view details", "view detail",
    "tour", "tour now", "schedule tour", "select", "see details",
    "apply now", "contact", "share", "save", "compare", "hide", "show more",
    "schedule", "inquire", "unit",
})

# A valid plan name: starts with a letter, 2–41 chars total, only letters /
# digits / spaces / hyphens / slashes / dots.  Rejects "1 Bath", "$2,950", etc.
_PLAN_NAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z0-9\s\-\/\.]{1,40}$")

# UI verb phrases that appear where plan names should be in SightMap unit
# cards (e.g. "Available May 7th", "Request a Tour", "Schedule Tour").
# _UI_VERB_BLACKLIST catches exact-match words; this regex catches prefixes.
_NOT_A_PLAN_NAME_RE = re.compile(
    r"^(?:available|request|schedule|view|see|apply|contact|"
    r"tour|select|inquire|share|save|compare|hide|show)\b",
    re.I,
)

# Bare unit-number pattern: single uppercase letter + 3 or more digits
# (E303, A1023, B205).  Real plan codes use 1–2 digit suffixes (A1, S5, B12).
_UNIT_NUMBER_RE = re.compile(r"^[A-Z]\d{3,}$")


# ---------------------------------------------------------------------------
# RentCafe FloorPlan V2 plan-card parser
# ---------------------------------------------------------------------------
# Used by properties built on the RentCafe/Yardi CMS (The Ryden, Atlas Oakland,
# The Asher Fremont, etc.).  Each ``units_grid--item`` element represents one
# floor-plan type with aggregated pricing.

_RENTCAFE_SKIP = re.compile(
    r"^(View Units|Virtual Tour|Video|sq\.?\s*ft\.?|"
    r"Request a Tour|Contact Us|click here|to start over\.?)$",
    re.I,
)


def _parse_rentcafe_card_lines(lines: List[str]) -> dict:
    """Parse one ``units_grid--item`` text block into a unit dict.

    Expected line sequence (some fields may be absent):
    ``PlanName → N BR / N.0 BA (or "Studio") → , sqft → sq ft →
      [Virtual Tour] → [Video] → View Units → from $X* →
      Base Rent $X • N mo. → N Available [Date / "Now"]``

    Returns an empty dict for UI-placeholder items (e.g. "No results match…").
    """
    if not lines:
        return {}
    # "No results match the selected filters" placeholder — drop it
    if re.search(r"no results\s+match|click here", lines[0], re.I):
        return {}

    unit: dict = {}
    for line in lines:
        if _RENTCAFE_SKIP.match(line):
            continue

        # Plan name — first non-skipped line
        if "plan_name" not in unit:
            unit["plan_name"] = line
            if re.search(r"\bstudio\b", line, re.I):
                unit.setdefault("bedrooms", 0)
            continue

        # Bed/bath: "1 BR / 1.0 BA"
        m = re.match(r"(\d+)\s*BR\s*/\s*([\d.]+)\s*BA", line, re.I)
        if m:
            unit["bedrooms"] = int(m.group(1))
            unit["bathrooms"] = float(m.group(2))
            continue

        # Studio standalone: "Studio" or "Studio/1BA"
        if re.match(r"^studio\b", line, re.I):
            unit.setdefault("bedrooms", 0)
            m_ba = re.search(r"([\d.]+)\s*BA", line, re.I)
            if m_ba:
                unit["bathrooms"] = float(m_ba.group(1))
            continue

        # Sqft: ", 690" or ", 694 - 775" (take the smaller value)
        m = re.match(r",\s*([\d,]+)(?:\s*[-\u2013]\s*([\d,]+))?", line)
        if m:
            unit["size_sqft"] = int(m.group(1).replace(",", ""))
            continue

        # Base rent (preferred price): "Base Rent $2,895 • 12 mo."
        m = re.search(r"Base Rent\s+\$?([\d,]+)", line, re.I)
        if m:
            unit["price"] = int(m.group(1).replace(",", ""))
            continue

        # Starting price fallback: "from $2,901*"
        m = re.search(r"from\s+\$?([\d,]+)", line, re.I)
        if m and "price" not in unit:
            unit["price"] = int(m.group(1).replace(",", ""))
            continue

        # Availability
        if re.search(r"\bavailable\b|\bwaitlist\b|\bno units\b", line, re.I):
            unit["availability"] = line

    return unit


# ---------------------------------------------------------------------------
# Apartment website validator
# ---------------------------------------------------------------------------
# Quick keyword scan on static HTML to reject non-apartment sites (hotels,
# senior-care facilities, etc.) before any Playwright or LLM work is done.

# Signals in the page <title> or <meta name="description"> that indicate
# this is NOT a standard rental apartment complex.
_NON_APT_TITLE_KEYWORDS: List[str] = [
    "hotel", "motel", " inn ", "resort", "hostel",
    "assisted living", "memory care", "skilled nursing", "senior living",
    "retirement community", "independent living",
    "short-term rental", "extended stay america",
    # Affordable / income-restricted housing
    "housing authority",
    "community development corporation",
    "affordable housing",
]

# Strong body-text signals that indicate hospitality / non-apartment content.
# Keep this list tight — apartment sites must not be false-positived.
_NON_APT_BODY_KEYWORDS: List[str] = [
    "per night",
    "check-in date",
    "checkout date",
    "nightly rate",
    "book a room",
    "room reservations",
    "nights stayed",
    # Affordable / income-restricted housing
    "income restricted",
    "income qualified",
    "% ami",
    "area median income",
    "section 8 voucher",
    "hud-funded",
    "low-income housing tax credit",
    "lihtc",
]

# At least one of these must appear somewhere in the page text for the site
# to be considered an apartment complex (fail-open: if neither list matches
# we let the site through rather than risk a false rejection).
_APT_POSITIVE_KEYWORDS: List[str] = [
    "floor plan", "floorplan",
    "bedroom", "studio",
    "per month", "/mo", "monthly rent",
    "lease", "move-in",
    "sq. ft.", "sqft", "sq ft",
    "apartment", " apt ",
    "1 bed", "2 bed", "3 bed",
]

# Hard-coded hotel-chain domains to reject immediately.
_HOTEL_DOMAINS: frozenset = frozenset({
    "hyatt.com", "marriott.com", "hilton.com", "ihg.com", "wyndham.com",
    "bestwestern.com", "choicehotels.com", "radissonhotels.com",
    "accor.com", "starwoodhotels.com",
})


def is_apartment_website(html: str, url: str) -> tuple:
    """Return ``(True, "")`` if *html* looks like a residential apartment site.

    Returns ``(False, reason)`` if the page is clearly a hotel, senior-care
    facility, or other non-apartment property.  On any parsing error the
    function returns ``(True, "")`` so the caller falls through to the agent.

    Only the first 60 KB of HTML is examined for speed.
    """
    try:
        from urllib.parse import urlparse as _urlparse
        domain = _urlparse(url).netloc.lower()
        for hd in _HOTEL_DOMAINS:
            if hd in domain:
                return False, f"domain is a hotel chain ({hd})"

        soup = BeautifulSoup(html[:60_000], "html.parser")

        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True).lower() if title_tag else ""

        meta_tag = soup.find("meta", attrs={"name": "description"})
        meta_text = (meta_tag.get("content") or "").lower() if meta_tag else ""

        header = title_text + " " + meta_text

        for kw in _NON_APT_TITLE_KEYWORDS:
            if kw in header:
                return False, f"title/meta contains '{kw}'"

        body_text = soup.get_text(separator=" ", strip=True)[:25_000].lower()

        for kw in _NON_APT_BODY_KEYWORDS:
            if kw in body_text:
                return False, f"page body contains '{kw}'"

        # Positive check — if any apartment signal present, accept immediately
        for kw in _APT_POSITIVE_KEYWORDS:
            if kw in body_text or kw in header:
                return True, ""

        # No rejection or positive signal — let through conservatively
        return True, ""
    except Exception:
        return True, ""


# ---------------------------------------------------------------------------
# Jonah Digital platform parser
# ---------------------------------------------------------------------------

_JD_SIGNAL = "jd-fp-floorplan-card"


def _is_jonah_digital(html: str) -> bool:
    return _JD_SIGNAL in html


def _extract_jonah_digital_hrefs(html: str, base_url: str) -> List[str]:
    """Return absolute detail-page URLs from Jonah Digital floor-plan card hrefs.

    Jonah Digital sometimes embeds card markup inside <template> or <script>
    elements that BeautifulSoup won't traverse.  We use a regex pass on the
    raw HTML to catch those hrefs too.
    """
    seen: set[str] = set()
    hrefs: List[str] = []

    # Primary: BeautifulSoup on live DOM elements
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        cls = " ".join(a.get("class", []))
        href = a["href"].strip()
        if "jd-fp-floorplan-card" in cls and href:
            abs_url = urljoin(base_url, href)
            if abs_url not in seen:
                seen.add(abs_url)
                hrefs.append(abs_url)

    # Fallback: regex scan of raw HTML for hrefs adjacent to jd-fp-floorplan-card
    for m in re.finditer(
        r'<a\b[^>]*?(?:href=["\']([^"\']+)["\'][^>]*class=["\'][^"\']*jd-fp-floorplan-card'
        r'|class=["\'][^"\']*jd-fp-floorplan-card[^"\']*["\'][^>]*href=["\']([^"\']+)["\'])',
        html,
    ):
        raw = m.group(1) or m.group(2)
        if raw:
            abs_url = urljoin(base_url, raw.strip())
            if abs_url not in seen:
                seen.add(abs_url)
                hrefs.append(abs_url)

    return hrefs


def _parse_jonah_digital_detail(html: str, detail_url: str) -> Optional[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    slug = urlparse(detail_url).path.rstrip("/").rsplit("/", 1)[-1]
    _HEADING_EXCLUDE_RE = re.compile(
        r"floor\s*plans?|available|contact|schedule|pet\s*policy|book\s*a\s*tour"
        r"|leasing|spaces\s*created|now\s*leasing|our\s*amenities",
        re.I,
    )
    name: Optional[str] = None
    slug_upper = slug.upper()
    for tag in soup.find_all(["h1", "h2", "h3"]):
        t = tag.get_text(strip=True)
        if not t or len(t) >= 80 or _HEADING_EXCLUDE_RE.search(t):
            continue
        if t.upper() == slug_upper:
            name = t
            break
        if name is None:
            name = t
    if not name:
        name = slug

    sqft: Optional[float] = None
    sqft_m = re.search(r"([\d,]+)\s*(?:sq\.?\s*ft|square\s*feet)", text, re.I)
    if sqft_m:
        sqft = float(sqft_m.group(1).replace(",", ""))

    beds: float = 0.0
    if sqft_m:
        _near60 = text[max(0, sqft_m.start() - 60):sqft_m.start() + 20]
        if re.search(r"\bstudio\b", _near60, re.I):
            beds = 0.0
        else:
            best_bed_m = None
            best_dist = float("inf")
            for _bm in re.finditer(r"(\d+)\s*(?:bed(?:room)?s?)", text, re.I):
                dist = abs(sqft_m.start() - _bm.end())
                if dist < best_dist:
                    best_dist = dist
                    best_bed_m = _bm
            if best_bed_m:
                beds = float(best_bed_m.group(1))
    else:
        m = re.search(r"(\d+)\s*(?:bed(?:room)?s?)", text, re.I)
        if m:
            beds = float(m.group(1))
        elif re.search(r"\bstudio\b", text, re.I):
            beds = 0.0

    price: Optional[float] = None
    price_matches = re.findall(r"\$([\d,]+)(?:\s*[-\u2013]\s*\$([\d,]+))?", text)
    for lo_str, _ in price_matches:
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


async def _fetch_jonah_digital_plans(
    hrefs: List[str],
    session: aiohttp.ClientSession,
    concurrency: int = 5,
) -> List[Dict]:
    sem = asyncio.Semaphore(concurrency)
    results: List[Dict] = []

    async def _fetch_one(url: str) -> None:
        async with sem:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return
                    html = await resp.text(errors="replace")
                unit = _parse_jonah_digital_detail(html, url)
                if unit is not None:
                    results.append(unit)
            except Exception:
                pass

    await asyncio.gather(*[_fetch_one(u) for u in hrefs])
    return results


# ---------------------------------------------------------------------------
# FatWin (WordPress apartment plugin) parser
# ---------------------------------------------------------------------------

_FATWIN_SIGNAL = "fatwin.com"


def _is_fatwin(html: str) -> bool:
    return _FATWIN_SIGNAL in html


def _extract_fatwin_hrefs(html: str, base_url: str) -> List[str]:
    seen: set[str] = set()
    hrefs: List[str] = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/floorplan/[^/?]+/?$", href):
            abs_url = urljoin(base_url, href.rstrip("/") + "/")
            if abs_url not in seen:
                seen.add(abs_url)
                hrefs.append(abs_url)
    return hrefs


def _parse_fatwin_detail(html: str, detail_url: str) -> Optional[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n", strip=True)

    name: str = urlparse(detail_url).path.rstrip("/").rsplit("/", 1)[-1]
    title_tag = soup.find("title")
    if title_tag:
        raw_title = title_tag.get_text(strip=True)
        name = raw_title.split("|")[0].strip() or name

    beds: float = 0.0
    sqft: Optional[float] = None
    m_line = re.search(
        r"(Studio|\d+\s*Bedroom)\s*\|\s*(\d+(?:\.\d+)?)\s*Bath.*?([\d,]+)(?:\s*-\s*([\d,]+))?\s*SF",
        text,
        re.I | re.S,
    )
    if m_line:
        bed_token = m_line.group(1).strip()
        if re.search(r"studio", bed_token, re.I):
            beds = 0.0
        else:
            beds = float(re.search(r"\d+", bed_token).group())
        sqft = float(m_line.group(3).replace(",", ""))

    price: Optional[float] = None
    base_rent_m = re.search(
        r"\$\s*([\d,]+)\s*\n?\s*Base\s+Rent"
        r"|Base\s+Rent\s*\n?\s*\$\s*([\d,]+)",
        text,
        re.I,
    )
    if base_rent_m:
        raw = (base_rent_m.group(1) or base_rent_m.group(2) or "").replace(",", "")
        try:
            candidate = float(raw)
            if 1_500 <= candidate <= 20_000:
                price = candidate
        except (ValueError, AttributeError):
            pass

    return {
        "plan_name": name,
        "bedrooms": beds,
        "size_sqft": sqft,
        "price": price,
        "availability": "available",
    }


async def _fetch_fatwin_plans(
    hrefs: List[str],
    session: aiohttp.ClientSession,
    concurrency: int = 5,
) -> List[Dict]:
    sem = asyncio.Semaphore(concurrency)
    results: List[Dict] = []

    async def _fetch_one(url: str) -> None:
        async with sem:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        return
                    html = await resp.text(errors="replace")
                unit = _parse_fatwin_detail(html, url)
                if unit is not None:
                    results.append(unit)
            except Exception:
                pass

    await asyncio.gather(*[_fetch_one(u) for u in hrefs])
    return results


# ---------------------------------------------------------------------------
# SightMap embed URL extractor
# ---------------------------------------------------------------------------

# (\w+) must be ≥6 chars to exclude `api` from `sightmap.com/embed/api.js`
_SIGHTMAP_EMBED_RE = re.compile(r'https://sightmap\.com/embed/([a-z0-9]{6,})', re.I)
# Shea Apartments pattern: engrain_id="yzvgdo6zvln" in HTML attribute
_SIGHTMAP_ENGRAIN_RE = re.compile(r'engrain[_-]?id=["\']([a-z0-9]{6,})["\']', re.I)


def _extract_sightmap_embed_url(html: str) -> Optional[str]:
    """Return the full SightMap embed URL if found in *html*, else None.

    Handles two embed patterns:
    - Direct iframe/link: ``https://sightmap.com/embed/XXXX``
    - Shea/Engrain attribute: ``engrain_id="XXXX"`` (widget configured in JS)
    """
    m = _SIGHTMAP_EMBED_RE.search(html)
    if m:
        return m.group(0)
    m = _SIGHTMAP_ENGRAIN_RE.search(html)
    if m:
        return f"https://sightmap.com/embed/{m.group(1)}"
    return None


# ---------------------------------------------------------------------------
# SightMap price-parsing helpers (used by _scrape_visible_units)
# ---------------------------------------------------------------------------

# "$3,412 Base Rent" — price before label (Revela / newer Engrain format)
_BASE_RENT_BEFORE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)\s+Base\s+Rent", re.I)
# "Base Rent $3,800" — label before price (older Engrain format)
_BASE_RENT_AFTER_RE = re.compile(r"Base\s+Rent\s+\$?\s*([\d,]+(?:\.\d{1,2})?)", re.I)
# "$3,445.12 /mo*" or "$3,100 /mo" — decimal-safe, handles asterisk suffix
_MO_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(?:/|\s+per\s+)\s*mo", re.I)
# Bare "$3,200" or "$3,200.50" on a line by itself
_STANDALONE_PRICE_RE = re.compile(r"^\$\s*([\d,]+(?:\.\d{1,2})?)\s*$")


def _parse_price(s: str) -> Optional[float]:
    """Parse '3,445.12' or '3,445' → float. Returns None if outside [500, 25000]."""
    try:
        val = float(s.replace(",", ""))
        if 500 <= val <= 25_000:
            return val
    except ValueError:
        pass
    return None


# ---------------------------------------------------------------------------
# Link scoring for _page_state rank-then-truncate
# ---------------------------------------------------------------------------

_LINK_TEXT_POSITIVE: List[tuple] = [
    (r"\bfloor\s*plans?\b", 100),
    (r"\bplans?\s*&?\s*pricing\b", 95),
    (r"\bavailability\b", 90),
    (r"\bresidences?\b", 80),
    (r"\blive\s+here\b", 40),
    (r"\bapartments?\b", 50),
    (r"\brentals?\b", 50),
    (r"\bhomes?\b", 30),
]

_HREF_POSITIVE: List[tuple] = [
    (r"/floor-?plans?/?$", 80),
    (r"/availability/?$", 70),
    (r"/plans?/?$", 60),
    (r"/apartments?/?$", 40),
    (r"/residences?/?$", 40),
    (r"/rentals?/?$", 40),
]

_LINK_TEXT_NEGATIVE: List[tuple] = [
    (r"\binstagram\b|\bfacebook\b|\btwitter\b|\blinkedin\b|\btiktok\b", -80),
    (r"\bprivacy\b|\bterms\b|\baccessibility\b|\bfair\s+housing\b", -60),
    (r"\bsitemap\b|\bcookie", -50),
    (r"\bcontact\s+us\b", -40),
    (r"\bschedule\s+tour\b", -30),
    (r"\bapply\s+now\b", -30),
    (r"\blogin\b|\bsign\s*in\b|\bresident\s+portal\b", -30),
]

_HREF_NEGATIVE: List[tuple] = [
    (r"instagram\.com|facebook\.com|twitter\.com|linkedin\.com|tiktok\.com", -90),
    (r"^(?:mailto|tel):", -90),
    (r"/(?:privacy|terms|accessibility|sitemap|cookies?)\b", -60),
    (r"/(?:login|signin|portal|resident)\b", -30),
]

_PLATFORM_DOMAINS = ("sightmap", "rentcafe", "entrata", "yardi")


def _score_link(text: str, href: str, base_domain: str) -> int:
    """Score a link for floor-plan discovery relevance. Higher = more relevant."""
    score = 0
    text_lower = text.lower()
    href_lower = href.lower()

    for pattern, weight in _LINK_TEXT_POSITIVE:
        if re.search(pattern, text_lower):
            score += weight
            break
    for pattern, weight in _HREF_POSITIVE:
        if re.search(pattern, href_lower):
            score += weight
            break
    for pattern, weight in _LINK_TEXT_NEGATIVE:
        if re.search(pattern, text_lower):
            score += weight
            break
    for pattern, weight in _HREF_NEGATIVE:
        if re.search(pattern, href_lower):
            score += weight
            break

    if href.startswith("http"):
        try:
            link_domain = urlparse(href).netloc.lower()
            if link_domain and link_domain != base_domain:
                if not any(p in link_domain for p in _PLATFORM_DOMAINS):
                    score -= 20
        except Exception:
            pass

    return score


class BrowserSession:
    """Async context manager that wraps a headless Chromium browser.

    Tracks an "active frame" which is initially the top-level page but can
    be switched into an iframe via ``read_iframe()``.  All tool calls
    (click_link, click_button, scroll_down, _page_state) operate on
    whichever frame is currently active.

    Usage::

        async with BrowserSession() as browser:
            state = await browser.navigate_to("https://...")
    """

    def __init__(self, headless: bool = True):
        self._headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        # The frame currently being read; starts as the top-level page.
        self._active_frame: Optional[Frame] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "BrowserSession":
        await self.start()
        return self

    async def __aexit__(self, *_args) -> None:
        await self.stop()

    async def start(self) -> None:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self._headless)
        self._context = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        self.page = await self._context.new_page()
        self._active_frame = None  # set after first navigation

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def navigate_to(self, url: str) -> dict:
        """Navigate to *url* and return a page-state dict (outer page only)."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await self._settle()
            self._active_frame = self.page.main_frame  # reset to outer page
            return await self._page_state()
        except Exception as exc:
            return {"error": str(exc), "url": url, "text": "", "links": [], "buttons": [], "iframes": []}

    async def read_iframe(self, keyword: str, timeout: float = 10.0, _replay: bool = False) -> dict:
        """Switch the active frame to the first iframe whose src contains *keyword*.

        After this call all subsequent tool calls (click_button, scroll_down,
        get_page_content) operate inside that iframe until navigate_to resets it.

        Returns the iframe's page state so the agent can see its content.

        Polls for up to *timeout* seconds so that lazy-loaded iframes (e.g.
        SightMap widgets that inject after initial page load) are found even
        when called immediately after navigate_to (as during cache replay).

        _replay=True uses a longer wait (frame-level networkidle + extra sleep)
        so that SightMap's async API calls complete before extract_all_units runs.
        During live agent runs the LLM's own processing time covers this gap.
        """
        try:
            poll_interval = 0.5
            elapsed = 0.0
            while elapsed <= timeout:
                for frame in self.page.frames:
                    if keyword.lower() in frame.url.lower():
                        self._active_frame = frame
                        if _replay:
                            # During replay there is no LLM delay between steps —
                            # wait for the iframe's own XHR traffic to settle.
                            try:
                                await frame.wait_for_load_state("networkidle", timeout=15_000)
                            except Exception:
                                await asyncio.sleep(3)
                            await asyncio.sleep(3)  # extra buffer
                        else:
                            await self._settle()
                            await asyncio.sleep(2)
                        state = await self._page_state()
                        state["active_frame"] = frame.url
                        return state
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
            # Not found after waiting — list available frames to help the agent
            available = [f.url for f in self.page.frames if f.url and f.url != "about:blank"]
            return {
                "error": f"No iframe found matching {keyword!r} (waited {timeout:.0f}s)",
                "available_iframes": available,
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def click_link(self, text_or_href: str) -> dict:
        """Click a link whose visible text or href contains *text_or_href*."""
        frame = self._active_frame or self.page.main_frame
        try:
            loc = frame.get_by_role("link", name=text_or_href, exact=False)
            if await loc.count() > 0:
                await loc.first.click(timeout=6_000)
            else:
                loc = frame.locator(f'a[href*="{text_or_href}"]')
                if await loc.count() > 0:
                    await loc.first.click(timeout=6_000)
                else:
                    return {"error": f"No link found matching: {text_or_href!r}"}
            await self._settle()
            return await self._page_state()
        except Exception as exc:
            return {"error": str(exc)}

    async def click_button(self, text: str) -> dict:
        """Click a button or tab whose label contains *text*."""
        frame = self._active_frame or self.page.main_frame
        try:
            for role in ("button", "tab"):
                loc = frame.get_by_role(role, name=text, exact=False)  # type: ignore[arg-type]
                if await loc.count() > 0:
                    await loc.first.click(timeout=6_000)
                    await self._settle()
                    return await self._page_state()

            loc = frame.get_by_text(text, exact=False)
            if await loc.count() > 0:
                await loc.first.click(timeout=6_000)
                await self._settle()
                return await self._page_state()

            return {"error": f"No button/tab found matching: {text!r}"}
        except Exception as exc:
            return {"error": str(exc)}

    async def scroll_down(self) -> dict:
        """Scroll one viewport height down."""
        frame = self._active_frame or self.page.main_frame
        try:
            await frame.evaluate("window.scrollBy(0, window.innerHeight)")
        except Exception:
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(1)
        return await self._page_state()

    async def extract_all_units(self) -> dict:
        """Enumerate every available unit shown in the current iframe or page.

        Works by cycling through every floor/tab button that has a non-zero
        unit count, clicking each one, and scraping the resulting unit list.
        Returns a dict with a ``units`` list — each item has keys:
        unit_number, plan_name, bedrooms, bathrooms, size_sqft, price, availability.

        Falls back to plain text extraction if no structured unit cards are found.

        Short-circuits to a direct HTTP fetch for Jonah Digital sites (JD widget
        renders empty shells in static HTML; prices live on per-plan detail pages).
        """
        frame = self._active_frame or self.page.main_frame

        # --- Jonah Digital fast path ---
        try:
            html = await frame.content()
        except Exception:
            html = await self.page.content()

        if _is_jonah_digital(html):
            current_url = self.page.url
            hrefs = _extract_jonah_digital_hrefs(html, current_url)
            if hrefs:
                connector = aiohttp.TCPConnector(ssl=False)
                headers = {
                    "User-Agent": (
                        "AptTrack/1.0 (rental price transparency tool; "
                        "contact@apttrack.app)"
                    )
                }
                async with aiohttp.ClientSession(connector=connector, headers=headers) as sess:
                    jd_units = await _fetch_jonah_digital_plans(hrefs, sess)
                if jd_units:
                    return {"units": jd_units, "total": len(jd_units), "method": "jonah_digital"}

        units: list[dict] = []
        seen_units: set[str] = set()

        async def _scrape_visible_units() -> list[dict]:
            """Parse whatever unit cards are currently visible in the frame."""
            try:
                html = await frame.content()
            except Exception:
                html = await self.page.content()
            soup = BeautifulSoup(html, "html.parser")
            for t in soup(["script", "style"]): t.decompose()
            text = soup.get_text(separator="\n", strip=True)

            found: list[dict] = []
            import re
            # SightMap patterns:
            #   Standard:  "HOME XXXX\nPlanName\nN Bed / N Bath / NNN sq. ft.\n..."
            #   Engrain:   "APT XXXX\nPlan 1F\n1 Bed / 1 Bath / 841 sq. ft.\n...\n$3,774"
            _UNIT_HEADER_RE = re.compile(r"^(?:HOME|APT)\s+\w+")
            blocks = re.split(r"\n(?=(?:HOME|APT)\s+\w+)", text)
            for block in blocks:
                lines = [l.strip() for l in block.splitlines() if l.strip()]
                if not lines or not _UNIT_HEADER_RE.match(lines[0]):
                    continue
                unit_no = re.sub(r"^(?:HOME|APT)\s+", "", lines[0])
                unit: dict = {"unit_number": unit_no}
                for line in lines[1:]:
                    # Plan name — first line that passes all filters
                    if not unit.get("plan_name"):
                        stripped = line.strip()
                        if (stripped
                                and not _NOT_A_PLAN_NAME_RE.match(stripped)
                                and not _UNIT_NUMBER_RE.match(stripped)
                                and not re.search(r"\$|\d+\s*Bed|sq\.?\s*ft|waitlist", stripped, re.I)
                                and stripped.lower() not in _UI_VERB_BLACKLIST
                                and _PLAN_NAME_REGEX.match(stripped)
                                and not _UNIT_HEADER_RE.match(stripped.upper())):
                            unit["plan_name"] = stripped
                    # Studio detection (must precede bed-count regex)
                    if "bedrooms" not in unit and re.search(r"\bstudio\b", line, re.I):
                        unit["bedrooms"] = 0
                    # Bed count
                    if "bedrooms" not in unit:
                        m = re.search(r"(\d+)\s*Bed", line, re.I)
                        if m:
                            unit["bedrooms"] = int(m.group(1))
                    # Bath count
                    if "bathrooms" not in unit:
                        m = re.search(r"(\d+)\s*Bath", line, re.I)
                        if m:
                            unit["bathrooms"] = int(m.group(1))
                    # Sqft — handles "420 sq. ft.", "1,050 sqft", "680 sq ft"
                    if "size_sqft" not in unit:
                        m = re.search(r"([\d,]+)\s*sq\.?\s*ft", line, re.I)
                        if m:
                            unit["size_sqft"] = int(m.group(1).replace(",", ""))
                    # Availability
                    if re.search(r"available|waitlist", line, re.I):
                        unit["availability"] = line
                # Price — three passes: Base Rent preferred, then /mo total, then bare $
                # TODO: expose total_monthly_rent as a second field once FloorPlan
                #       model supports it (needs migration + persistence changes).
                _price: Optional[float] = None
                for _ln in lines[1:]:
                    _m = _BASE_RENT_BEFORE_RE.search(_ln) or _BASE_RENT_AFTER_RE.search(_ln)
                    if _m:
                        _price = _parse_price(_m.group(1))
                        break
                if _price is None:
                    for _ln in lines[1:]:
                        _m = _MO_PRICE_RE.search(_ln)
                        if _m:
                            _price = _parse_price(_m.group(1))
                            break
                if _price is None:
                    for _ln in lines[1:]:
                        _m = _STANDALONE_PRICE_RE.match(_ln.strip())
                        if _m:
                            _price = _parse_price(_m.group(1))
                            break
                if _price is not None:
                    unit["price"] = _price
                found.append(unit)
            return found

        # --- Step 1: collect what's visible without any clicks ---
        # Retry up to 3 times with increasing waits — SightMap's React widget
        # may still be fetching unit data when we first call this.
        visible = await _scrape_visible_units()
        for _wait in (4, 6):
            if visible:
                break
            await asyncio.sleep(_wait)
            visible = await _scrape_visible_units()
        for u in visible:
            key = u.get("unit_number", "")
            if key and key not in seen_units:
                seen_units.add(key)
                units.append(u)

        # --- Step 2: find floor buttons with available homes and click each ---
        try:
            html = await frame.content()
            soup = BeautifulSoup(html, "html.parser")
            import re
            text = soup.get_text(separator="\n", strip=True)
            # Find lines like "3\n2 HOMES", "5\n1 Home", or "3\n7 Units" (Engrain variant)
            floor_matches = re.findall(r"(\d{1,2})\n(\d+)\s+(?:Home|Unit|Apt)s?", text, re.I)
            non_empty_floors = sorted(int(f) for f, n in floor_matches if int(n) > 0)
        except Exception:
            non_empty_floors = []

        for floor_num in non_empty_floors[:30]:  # cap at 30 floors (SF high-rises)
            try:
                # Click the floor button by its exact number
                loc = frame.get_by_text(str(floor_num), exact=True)
                count = await loc.count()
                if count == 0:
                    continue
                # Pick the one inside the floor list (usually first match)
                await loc.first.click(timeout=4_000)
                await asyncio.sleep(1.5)
                floor_units = await _scrape_visible_units()
                for u in floor_units:
                    key = u.get("unit_number", "")
                    if key and key not in seen_units:
                        seen_units.add(key)
                        units.append(u)
            except Exception:
                continue

        # --- Step 3: fall back to RentCafe plan-card format on outer page ---
        # Handles properties whose SightMap is map-view only (no DOM unit list)
        # but whose main page uses the RentCafe FloorPlan V2 widget.
        if not units:
            units = await self._scrape_rentcafe_cards()

        return {"units": units, "total": len(units)}

    async def _scrape_rentcafe_cards(self) -> List[dict]:
        """Parse RentCafe ``units_grid--item`` plan cards from the outer page.

        Always reads from the main frame, so it works even when
        ``_active_frame`` points at a SightMap iframe.
        """
        try:
            html = await self.page.main_frame.content()
        except Exception:
            return []
        soup = BeautifulSoup(html, "html.parser")
        for t in soup(["script", "style"]):
            t.decompose()

        # Grid layout (most common) → table layout (fallback)
        items = soup.find_all(class_=re.compile(r"\bunits_grid--item\b", re.I))
        if not items:
            items = soup.find_all(class_=re.compile(r"\bunits_table--item\b", re.I))
        if not items:
            return []

        units: List[dict] = []
        for item in items:
            raw = item.get_text(separator="\n", strip=True).replace("\xa0", " ")
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            unit = _parse_rentcafe_card_lines(lines)
            if unit.get("plan_name"):
                units.append(unit)
        return units

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _smart_truncate(self, text: str, max_chars: int) -> str:
        """Truncate *text* to *max_chars*, prioritising pricing-relevant lines.

        Lines containing any pricing/apartment keyword are moved to the front
        so the model always sees them even when the page is long.
        """
        lines = text.split("\n")
        priority = [l for l in lines if any(k in l.lower() for k in _PRICING_KEYWORDS)]
        other = [l for l in lines if l not in priority]
        combined = "\n".join(priority + other)
        return combined[:max_chars]

    async def _settle(self) -> None:
        """Wait for the page to reach a stable network state."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            await asyncio.sleep(2)

    async def _page_state(self) -> dict:
        """Return a structured snapshot of the current active frame."""
        frame = self._active_frame or self.page.main_frame

        try:
            html = await frame.content()
        except Exception:
            html = await self.page.content()

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "meta", "head"]):
            tag.decompose()

        raw_text = soup.get_text(separator="\n", strip=True)
        lines = [line for line in raw_text.splitlines() if line.strip()]
        text = self._smart_truncate("\n".join(lines), MAX_TEXT_CHARS)

        # Clickable links — rank by floor-plan relevance, then keep top MAX_LINKS
        base_domain = urlparse(self.page.url).netloc.lower()
        scored: List[tuple] = []
        for a in soup.find_all("a", href=True):
            link_text = a.get_text(strip=True)
            if not link_text:
                continue
            href = str(a["href"])
            scored.append((_score_link(link_text, href, base_domain),
                           {"text": link_text[:80], "href": href[:150]}))
        scored.sort(key=lambda x: -x[0])  # stable sort preserves DOM order for ties
        links = [entry for _, entry in scored[:MAX_LINKS]]

        # Buttons and ARIA tabs
        seen: set = set()
        buttons: List[str] = []
        candidates = soup.find_all("button")
        candidates += soup.find_all(attrs={"role": re.compile(r"^(button|tab)$", re.I)})
        for el in candidates:
            label = el.get_text(strip=True)[:80]
            if label and label not in seen and len(buttons) < MAX_BUTTONS:
                seen.add(label)
                buttons.append(label)

        # Detect iframes on the outer page so the agent knows they exist
        iframes: list[str] = []
        if frame is self.page.main_frame:
            for f in self.page.frames:
                if f.url and f.url != "about:blank" and f is not self.page.main_frame:
                    iframes.append(f.url)

        result: dict = {
            "url": self.page.url,
            "active_frame": frame.url if frame is not self.page.main_frame else None,
            "text": text,
            "links": links,
            "buttons": buttons,
        }
        if iframes:
            result["iframes"] = iframes
        return result
