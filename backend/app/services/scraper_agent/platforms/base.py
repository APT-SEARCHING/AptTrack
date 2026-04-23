"""PlatformAdapter abstract base class.

Each concrete adapter encapsulates detection + extraction for one
CMS/platform (Jonah Digital, FatWin, SightMap, …).  The registry
calls detect() first; only if True does it call extract().
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession


class PlatformAdapter(ABC):
    """Interface every platform adapter must implement."""

    #: Human-readable name used in log messages and metrics.outcome
    name: str

    @abstractmethod
    def detect(self, html: str, url: str) -> bool:
        """Return True if this platform is present in the fetched homepage HTML."""
        ...

    @abstractmethod
    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[dict]:
        """Extract unit dicts from the site.

        Returns a list of unit dicts compatible with _parse_units_to_apartment_data,
        or an empty list if extraction found no data (treat as detection false-positive).

        Each dict has keys: plan_name, bedrooms, bathrooms, size_sqft, price, availability.
        (bathrooms is optional; may be absent for adapters that don't parse it.)
        """
        ...
