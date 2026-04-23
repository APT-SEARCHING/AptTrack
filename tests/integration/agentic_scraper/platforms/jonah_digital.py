"""Jonah Digital platform adapter.

Detects sites built on the Jonah Digital CMS via the _JD_SIGNAL substring,
then concurrently fetches each floor-plan detail page via aiohttp.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

import aiohttp

from ..browser_tools import (
    _extract_jonah_digital_hrefs,
    _fetch_jonah_digital_plans,
    _is_jonah_digital,
)
from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_USER_AGENT = "AptTrack/1.0 (rental price transparency tool; contact@apttrack.app)"


class JonahDigitalAdapter(PlatformAdapter):
    name = "jonah_digital"

    def detect(self, html: str, url: str) -> bool:
        return bool(html) and _is_jonah_digital(html)

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        hrefs = _extract_jonah_digital_hrefs(html, url)
        if not hrefs:
            return []
        async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False),
            headers={"User-Agent": _USER_AGENT},
        ) as session:
            units = await _fetch_jonah_digital_plans(hrefs, session)
        return units
