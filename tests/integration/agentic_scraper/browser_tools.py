"""Playwright-based browser session used by the apartment agent as tool implementations."""

import asyncio
import re
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

# Caps to keep tool-result payloads manageable for the LLM
MAX_TEXT_CHARS = 6000
MAX_LINKS = 50
MAX_BUTTONS = 30


class BrowserSession:
    """Async context manager that wraps a headless Chromium browser.

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

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    async def navigate_to(self, url: str) -> dict:
        """Navigate to *url* and return a page-state dict."""
        try:
            await self.page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await self._settle()
            return await self._page_state()
        except Exception as exc:
            return {"error": str(exc), "url": url, "text": "", "links": [], "buttons": []}

    async def click_link(self, text_or_href: str) -> dict:
        """Click a link whose visible text or href contains *text_or_href*."""
        try:
            loc = self.page.get_by_role("link", name=text_or_href, exact=False)
            if await loc.count() > 0:
                await loc.first.click(timeout=6_000)
            else:
                # Fall back to href substring match
                loc = self.page.locator(f'a[href*="{text_or_href}"]')
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
        try:
            for role in ("button", "tab"):
                loc = self.page.get_by_role(role, name=text, exact=False)  # type: ignore[arg-type]
                if await loc.count() > 0:
                    await loc.first.click(timeout=6_000)
                    await self._settle()
                    return await self._page_state()

            # Last resort: any element with matching text content
            loc = self.page.get_by_text(text, exact=False)
            if await loc.count() > 0:
                await loc.first.click(timeout=6_000)
                await self._settle()
                return await self._page_state()

            return {"error": f"No button/tab found matching: {text!r}"}
        except Exception as exc:
            return {"error": str(exc)}

    async def scroll_down(self) -> dict:
        """Scroll one viewport height down."""
        await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(1)
        return await self._page_state()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _settle(self) -> None:
        """Wait for the page to reach a stable network state."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            # Some SPAs never fire networkidle; a short sleep is sufficient
            await asyncio.sleep(2)

    async def _page_state(self) -> dict:
        """Return a structured snapshot of the current page."""
        html = await self.page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Strip boilerplate tags
        for tag in soup(["script", "style", "noscript", "meta", "head"]):
            tag.decompose()

        # Visible text — truncated to keep LLM payload small
        raw_text = soup.get_text(separator="\n", strip=True)
        lines = [line for line in raw_text.splitlines() if line.strip()]
        text = "\n".join(lines)[:MAX_TEXT_CHARS]

        # Clickable links
        links: list[dict] = []
        for a in soup.find_all("a", href=True):
            link_text = a.get_text(strip=True)
            if link_text and len(links) < MAX_LINKS:
                links.append({"text": link_text[:80], "href": str(a["href"])[:150]})

        # Buttons and ARIA tabs
        seen: set[str] = set()
        buttons: list[str] = []
        candidates = soup.find_all("button")
        candidates += soup.find_all(
            attrs={"role": re.compile(r"^(button|tab)$", re.I)}
        )
        for el in candidates:
            label = el.get_text(strip=True)[:80]
            if label and label not in seen and len(buttons) < MAX_BUTTONS:
                seen.add(label)
                buttons.append(label)

        return {
            "url": self.page.url,
            "text": text,
            "links": links,
            "buttons": buttons,
        }
