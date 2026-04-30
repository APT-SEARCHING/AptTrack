"""SightMap platform adapter.

Detects sites that embed a SightMap widget and navigates directly to the
embed URL using the live Playwright browser session to extract all units.

Unlike Jonah Digital / FatWin, this adapter uses the browser (not aiohttp)
and caches the embed URL found during detect() so extract() doesn't re-parse.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, List, Optional

from ..browser_tools import _extract_sightmap_embed_url
from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)


class SightMapAdapter(PlatformAdapter):
    name = "sightmap"

    def __init__(self) -> None:
        self._embed_url: Optional[str] = None

    def detect(self, html: str, url: str) -> bool:
        self._embed_url = _extract_sightmap_embed_url(html) if html else None
        return bool(self._embed_url)

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        embed_url = self._embed_url
        if not embed_url:
            return []
        logger.info("SightMap embed detected: %s — navigating directly", embed_url)
        state = await browser.navigate_to(embed_url)
        if state.get("error"):
            return []
        await asyncio.sleep(8)
        result = await browser.extract_all_units()
        return result.get("units", [])
