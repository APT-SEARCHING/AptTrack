"""FatWin platform adapter.

Detects WordPress sites using the FatWin apartment plugin via the
_FATWIN_SIGNAL substring, then concurrently fetches each /floorplan/
detail page via aiohttp.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

import aiohttp

from ..browser_tools import (
    _extract_fatwin_hrefs,
    _fetch_fatwin_plans,
    _is_fatwin,
)
from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_USER_AGENT = "AptTrack/1.0 (rental price transparency tool; contact@apttrack.app)"


class FatWinAdapter(PlatformAdapter):
    name = "fatwin"

    def detect(self, html: str, url: str) -> bool:
        return bool(html) and _is_fatwin(html)

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        hrefs = _extract_fatwin_hrefs(html, url)
        if not hrefs:
            return []
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            headers={"User-Agent": _USER_AGENT},
        ) as session:
            units = await _fetch_fatwin_plans(hrefs, session)
        return units
