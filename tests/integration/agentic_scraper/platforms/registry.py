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
    from .leasingstar import LeasingStarAdapter
    from .rentcafe import RentCafeAdapter
    from .sightmap import SightMapAdapter
    from .universal_dom import UniversalDOMExtractor
    from .windsor import WindsorAdapter

    return [
        JonahDigitalAdapter(),
        FatWinAdapter(),
        AvalonBayAdapter(),       # before SightMap: Avalon pages embed SightMap iframes but data is in Fusion.globalContent
        WindsorAdapter(),         # Spaces/Nestio; 2 Windsor properties
        LeasingStarAdapter(),     # before SightMap: RealPage/LeaseStar sites may also embed SightMap widgets
        SightMapAdapter(),
        GreystarAdapter(),        # before generic_detail; URL-based detect fires on redirected pages
        RentCafeAdapter(),        # Yardi RentCafe; static GA4 data on /floorplans subpage
        GenericDetailPageAdapter(),
        UniversalDOMExtractor(),  # fires last — catches unknown CMS card-list layouts
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
    *,
    hint_adapter_name: Optional[str] = None,
) -> Optional[Tuple[List[dict], str]]:
    """Try each registered platform adapter in order.

    If ``hint_adapter_name`` is provided, that adapter is tried first (fast
    path for previously-successful sites).  On hint miss the full registry is
    walked, skipping the already-tried adapter.

    Returns ``(units, adapter_name)`` on the first adapter that both detects
    the platform and successfully extracts at least one unit.
    Returns ``None`` if no adapter matched or all raised exceptions.
    """
    registry = get_registry()
    tried_first: Optional[str] = None

    # ── Hint fast path ────────────────────────────────────────────────────────
    if hint_adapter_name:
        hinted = next((a for a in registry if a.name == hint_adapter_name), None)
        if hinted:
            tried_first = hinted.name
            try:
                if hinted.detect(html, url):
                    units = await hinted.extract(html, url, browser)
                    if units:
                        logger.debug("Hint hit: %s → %d units", hinted.name, len(units))
                        return units, hinted.name
                    else:
                        logger.info(
                            "Hint '%s' detected but returned no units — falling through to full registry",
                            hinted.name,
                        )
                else:
                    logger.debug("Hint '%s' did not detect — falling through to full registry", hinted.name)
            except Exception as exc:
                logger.warning("Hinted adapter '%s' raised: %s — falling through", hint_adapter_name, exc)

    # ── Full registry walk (skip adapter already tried above) ────────────────
    for adapter in registry:
        if adapter.name == tried_first:
            continue
        if not adapter.detect(html, url):
            continue
        try:
            units = await adapter.extract(html, url, browser)
            if units:
                if adapter.name == "universal_dom":
                    logger.info(
                        "Universal DOM fallback used for %s — candidate for specific adapter if pattern recurs",
                        url,
                    )
                return units, adapter.name
        except Exception as exc:
            logger.warning(
                "%s pre-check failed: %s — falling through to agent",
                adapter.name, exc,
            )
    return None
