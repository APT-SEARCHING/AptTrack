"""Platform adapter registry.

try_platforms() is the single entry-point called by the scrape loop.
It iterates the ordered PLATFORM_REGISTRY, short-circuits on the first
successful extraction, and returns None if no adapter matches.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)


def _build_registry() -> List[PlatformAdapter]:
    # Deferred imports so that adapter modules are only loaded when first used.
    from .avalonbay import AvalonBayAdapter
    from .fatwin import FatWinAdapter
    from .generic_detail import GenericDetailPageAdapter
    from .greystar import GreystarAdapter
    from .jonah_digital import JonahDigitalAdapter
    from .sightmap import SightMapAdapter

    return [
        JonahDigitalAdapter(),
        FatWinAdapter(),
        SightMapAdapter(),
        AvalonBayAdapter(),       # static HTML JSON; 4 Bay Area properties
        GreystarAdapter(),        # before generic_detail; URL-based detect fires on redirected pages
        GenericDetailPageAdapter(),
    ]


# Module-level registry, built lazily on first call to try_platforms().
_REGISTRY: Optional[List[PlatformAdapter]] = None


def get_registry() -> List[PlatformAdapter]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


async def try_platforms(
    html: str,
    url: str,
    browser: "BrowserSession",
) -> Optional[Tuple[List[dict], str]]:
    """Try each registered platform adapter in order.

    Returns ``(units, adapter_name)`` on the first adapter that both detects
    the platform and successfully extracts at least one unit.
    Returns ``None`` if no adapter matched or all raised exceptions.
    """
    for adapter in get_registry():
        if not adapter.detect(html, url):
            continue
        try:
            units = await adapter.extract(html, url, browser)
            if units:
                return units, adapter.name
        except Exception as exc:
            logger.warning(
                "%s pre-check failed: %s — falling through to agent",
                adapter.name, exc,
            )
    return None
