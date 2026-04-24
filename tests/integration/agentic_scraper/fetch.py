"""Two-stage HTML fetch: static first, rendered as fallback.

Static (aiohttp): ~500ms. Good for server-rendered sites and sites that don't
require JS for floor-plan data.

Rendered (Playwright): 3-15s with DOM-signal wait. Required for React/Vue SPAs
(e.g. RentCafe brand sites, Cloudflare-protected sites) where plan data is
injected into the DOM by JavaScript.

The same platform adapters run against both HTML types. Adapters that only
detect signals present in the JS-rendered DOM (RentCafe SPA brand sites, etc.)
activate in Stage 2.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from .browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_UA = "AptTrack/1.0 (rental price transparency tool; contact@apttrack.app)"


# ---------------------------------------------------------------------------
# Static fetch
# ---------------------------------------------------------------------------

async def fetch_static(url: str, *, timeout: int = 15) -> str:
    """Fetch HTML via aiohttp (no JS execution). Returns "" on any error."""
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            headers={"User-Agent": _UA},
        ) as sess:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
                return await r.text(errors="replace")
    except Exception as exc:
        logger.warning("Static fetch failed for %s: %s", url, exc)
        return ""


# ---------------------------------------------------------------------------
# Cloudflare challenge detection
# ---------------------------------------------------------------------------

def is_cloudflare_challenge(html: str) -> bool:
    """Return True if html is a Cloudflare bot-challenge page, not real content.

    CF challenge pages are small (<20 KB) and contain distinctive markers.
    Treating them as empty forces the caller to upgrade to a rendered fetch.
    """
    if not html or len(html) > 20_000:
        return False
    lower = html.lower()
    return (
        ("just a moment" in lower and "cloudflare" in lower)
        or "cf-chl-" in lower
        or "__cf_bm" in lower
    )


# ---------------------------------------------------------------------------
# Rendered fetch
# ---------------------------------------------------------------------------

async def fetch_rendered(
    url: str,
    browser: "BrowserSession",
    *,
    timeout_ms: int = 30_000,
) -> str:
    """Fetch HTML via Playwright with DOM-signal-based hydration wait.

    Waits until the page contains recognisable floor-plan DOM elements
    (data-floorplan-id attributes, floorplan CSS classes, plan-card classes,
    or multi-link /floorplans/ anchors) before capturing content.  Falls back
    to a 1.5 s sleep if the signal never appears — the page may have loaded
    with different markup than expected.

    NOT networkidle: RentCafe's CDN keeps polling indefinitely, causing
    networkidle to time out even when the page is fully usable.
    """
    try:
        await browser.page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await browser.page.wait_for_function(
                """() => {
                    if (document.querySelector('[data-floorplan-id]')) return true;
                    if (document.querySelectorAll('[class*="floorplan"]').length >= 2) return true;
                    if (document.querySelectorAll('a[href*="/floorplans/"]').length >= 2
                        && !document.querySelector('a[href="/floorplans/"]:only-of-type')) return true;
                    if (document.querySelectorAll('[class*="plan-card"]').length >= 2) return true;
                    const t = (document.body && document.body.innerText || '').toLowerCase();
                    if (t.includes('loading floorplans') || t.includes('loading floor plans')
                        || t.includes('please wait')) return false;
                    return false;
                }""",
                timeout=12_000,
            )
        except Exception:
            pass  # timeout OK — is_apartment_website + adapters decide next
        await asyncio.sleep(1.5)
        return await browser.page.content()
    except Exception as exc:
        logger.warning("Rendered fetch failed for %s: %s", url, exc)
        return ""


# ---------------------------------------------------------------------------
# Static-sufficiency heuristic
# ---------------------------------------------------------------------------

_SIGNAL_TOKENS = (
    "sightmap.com",
    "fatwin.com",
    "jd-fp-floorplan-card",
    "cdngeneralmvc.rentcafe.com",
    "api.rentcafe.com",
    "fusion.globalcontent",
    "bozzuto.com",
    "entrata",
    "realpage",
)

_HREF_HINT_RE = re.compile(
    r'<a[^>]+href="[^"]*(?:floor-?plans?|residences?|/plan-)[^"]*/[a-zA-Z0-9\-]+/?"',
    re.I,
)

_BED_DOLLAR_RE = re.compile(
    r"\$\d[\d,]*(?:\s*[/-]\s*\$?\d[\d,]*)?\s*(?:/\s*mo)?[\s\S]{0,200}?\d+\s*bed",
    re.I,
)


def has_sufficient_plan_signals(html: str) -> bool:
    """Return True if static HTML already has enough signals for an adapter.

    Used to skip the expensive rendered fetch on server-rendered sites
    (Jonah Digital, FatWin, etc.) that don't need JS execution.
    Returns False → caller should upgrade to rendered fetch.
    """
    if not html or len(html) < 5_000:
        return False
    lower = html.lower()
    if any(tok in lower for tok in _SIGNAL_TOKENS):
        return True
    if _HREF_HINT_RE.search(html):
        return True
    if _BED_DOLLAR_RE.search(html):
        return True
    return False
