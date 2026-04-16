"""Playwright-based browser session used by the apartment agent as tool implementations."""

from __future__ import annotations

import asyncio
import re
from typing import List, Optional

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Frame, Page, async_playwright

# Caps to keep tool-result payloads manageable for the LLM
MAX_TEXT_CHARS = 4000   # reduced from 8000 — saves ~20-30% input tokens
MAX_LINKS = 20          # reduced from 50
MAX_BUTTONS = 15        # reduced from 40

# Keywords that indicate pricing-relevant content — these lines are
# prioritised when truncating page text so the model sees them first.
_PRICING_KEYWORDS = [
    "$", "bed", "bath", "sqft", "sq ft", "plan", "studio",
    "available", "price", "rent", "floor", "unit", "home",
]

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
        """
        frame = self._active_frame or self.page.main_frame
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
            # SightMap pattern: "HOME XXXX\nPlanName\nN Bed / N Bath / NNN sq. ft.\nAvailability\n$X,XXX /mo*"
            blocks = re.split(r"\n(?=HOME\s+\w+)", text)
            for block in blocks:
                lines = [l.strip() for l in block.splitlines() if l.strip()]
                if not lines or not re.match(r"HOME\s+\w+", lines[0]):
                    continue
                unit_no = re.sub(r"^HOME\s+", "", lines[0])
                unit: dict = {"unit_number": unit_no}
                for line in lines[1:]:
                    # Plan name line
                    if not unit.get("plan_name") and not re.search(r"\$|\d+ Bed|sq\. ft\.|Available", line, re.I):
                        unit["plan_name"] = line
                    # Bed/bath/sqft
                    m = re.search(r"(\d+)\s*Bed.*?(\d+)\s*Bath.*?([\d,]+)\s*sq", line, re.I)
                    if m:
                        unit["bedrooms"] = int(m.group(1))
                        unit["bathrooms"] = int(m.group(2))
                        unit["size_sqft"] = int(m.group(3).replace(",", ""))
                    # Availability
                    if re.search(r"available|waitlist", line, re.I):
                        unit["availability"] = line
                    # Price — prefer "Base Rent $X,XXX" over total monthly
                    m_base = re.search(r"Base Rent\s+\$?([\d,]+)", line, re.I)
                    m_price = re.search(r"\$([\d,]+)\s*/mo", line, re.I)
                    if m_base:
                        unit["price"] = int(m_base.group(1).replace(",", ""))
                    elif m_price and "price" not in unit:
                        unit["price"] = int(m_price.group(1).replace(",", ""))
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
            # Find lines like "3\n2 HOMES" or "5\n1 Home"
            floor_matches = re.findall(r"(\d{1,2})\n(\d+)\s+Home", text, re.I)
            non_empty_floors = [int(f) for f, n in floor_matches if int(n) > 0]
        except Exception:
            non_empty_floors = []

        for floor_num in non_empty_floors[:15]:  # cap at 15 floors
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

        # Clickable links
        links: List[dict] = []
        for a in soup.find_all("a", href=True):
            link_text = a.get_text(strip=True)
            if link_text and len(links) < MAX_LINKS:
                links.append({"text": link_text[:80], "href": str(a["href"])[:150]})

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
