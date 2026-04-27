"""Universal DOM extractor — card-list detection without site-specific selectors.

Fires LAST in the registry. Works on any rendered DOM where plans are
presented as ≥2 repeated sibling elements with shared tag+class signature
and text containing plan signals (bedrooms + bathrooms + sqft + price).

Examples it catches:
- Greystar new-format property pages
- Custom CMS sites with <div class="plan-card">...</div> × N
- Sites where plans are a grid/carousel but have no per-plan detail URL

It does NOT catch:
- Sites where plans are behind tab clicks (only first tab in DOM)
- Sites rendering plans in shadow DOM (BeautifulSoup can't see)
- Sites blocking JS-rendered scraping (fall through to LLM agent)
"""
from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Dict, List, Optional

from bs4 import BeautifulSoup, Tag

from .base import PlatformAdapter

if TYPE_CHECKING:
    from ..browser_tools import BrowserSession

logger = logging.getLogger(__name__)

_SPEC_RE = re.compile(r"\b(\d+)\s*(?:bed(?:room)?s?|br)\b|\bstudio\b", re.I)
_BATH_RE = re.compile(r"\b(\d+(?:\.\d)?)\s*(?:bath(?:room)?s?|ba)\b", re.I)
_SQFT_RE = re.compile(r"([\d,]+)\s*(?:sq\.?\s*ft\.?|sqft|square\s*feet)", re.I)

# Price extraction — two-pass with deposit/fee stripping
_RENT_PRICE_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(?:/|\s+per\s+)\s*(?:mo|month)\b",
    re.I,
)
_PLAIN_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")
_DEPOSIT_PHRASE_RE = re.compile(
    r"deposit(?:\s+starting\s+at)?[\s:]*\$\s*[\d,]+(?:\.\d{1,2})?",
    re.I,
)
_FEE_PHRASE_RE = re.compile(
    r"(?:admin|application|app|move-?in|amenity|parking|pet|holding)\s+fee[\s:]*\$\s*[\d,]+(?:\.\d{1,2})?",
    re.I,
)

# Kept for _has_plan_signals only (signal detection doesn't need deposit-awareness)
_PRICE_RE = re.compile(r"\$\s*([\d,]{3,6})(?:\s*[/\-]\s*\$?\s*([\d,]{3,6}))?", re.I)


def _parse_price(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ""))
    except (ValueError, TypeError):
        return None


def _extract_price_from_card_text(text: str) -> Optional[float]:
    """Extract monthly rent from card text, filtering out deposit/fee amounts.

    Strategy:
    1. Pass A (raw text): $X /mo or per month — explicit suffix wins immediately,
       no stripping needed (rent marker is unambiguous).
    2. Strip deposit/fee phrases from text for Pass B only.
    3. Pass B (stripped text): any bare $X >= $1,000 (Bay Area rent floor).
    4. Return None if no plausible rent found.
    """
    if not text:
        return None

    # Pass A — explicit /mo or per month suffix on raw text
    m = _RENT_PRICE_RE.search(text)
    if m:
        v = _parse_price(m.group(1))
        if v is not None and 500 <= v <= 25_000:
            return v

    # Strip deposit/fee phrases before searching for bare $ amounts
    cleaned = _DEPOSIT_PHRASE_RE.sub("", text)
    cleaned = _FEE_PHRASE_RE.sub("", cleaned)

    # Pass B — bare $ amounts with Bay Area rent floor ($1,000)
    for m in _PLAIN_PRICE_RE.finditer(cleaned):
        v = _parse_price(m.group(1))
        if v is not None and 1_000 <= v <= 25_000:
            return v

    return None


def _has_plan_signals(text: str) -> int:
    """Return count of distinct plan-data signal types present in text (0–4)."""
    n = 0
    if _SPEC_RE.search(text):
        n += 1
    if _BATH_RE.search(text):
        n += 1
    if _SQFT_RE.search(text):
        n += 1
    if _PRICE_RE.search(text):
        n += 1
    return n


def _sibling_signature(el: Tag) -> tuple:
    """(tag_name, frozenset_of_classes) — used to group repeated sibling elements."""
    return (el.name, frozenset(el.get("class", [])))


def _find_best_card_group(soup: BeautifulSoup) -> List[Tag]:
    """Find the group of repeated siblings that best represents a floor-plan card list.

    Scoring:
    - Count siblings sharing the same (tag, class) signature
    - Require ≥2 in the group have ≥2 plan signals each
    - Prefer groups in the range 2–25 (nav menus and feature grids are filtered out
      by the ratio threshold; giant repeating footer links are filtered by size_factor)
    """
    best_group: List[Tag] = []
    best_score = 0.0

    for parent in soup.find_all(True):
        children = [c for c in parent.children if isinstance(c, Tag)]
        if len(children) < 2:
            continue

        by_sig: Dict[tuple, List[Tag]] = {}
        for c in children:
            by_sig.setdefault(_sibling_signature(c), []).append(c)

        for sig, group in by_sig.items():
            if len(group) < 2:
                continue
            with_signals = sum(
                1 for g in group
                if _has_plan_signals(g.get_text(" ", strip=True)) >= 2
            )
            if with_signals < 2:
                continue
            ratio = with_signals / len(group)
            if ratio < 0.6:
                continue
            # Prefer tight groups (3–25); penalise nav-scale (many tiny items)
            size_factor = 1.0 if 2 <= len(group) <= 25 else 0.5
            score = with_signals * ratio * size_factor
            if score > best_score:
                best_score = score
                best_group = group

    return best_group


def _parse_card(card: Tag) -> Dict:
    """Extract plan fields from a single card element."""
    text = card.get_text(" ", strip=True)
    unit: Dict = {}

    # --- Bedrooms ---
    m = _SPEC_RE.search(text)
    if m:
        if "studio" in m.group(0).lower():
            unit["bedrooms"] = 0.0
        elif m.group(1):
            unit["bedrooms"] = float(m.group(1))

    # --- Bathrooms ---
    m = _BATH_RE.search(text)
    if m:
        try:
            unit["bathrooms"] = float(m.group(1))
        except ValueError:
            pass

    # --- Square feet ---
    m = _SQFT_RE.search(text)
    if m:
        try:
            unit["size_sqft"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # --- Price ---
    price = _extract_price_from_card_text(text)
    if price is not None:
        unit["price"] = price

    # --- Plan name: first heading tag ---
    for tag_name in ("h2", "h3", "h4", "h5"):
        h = card.find(tag_name)
        if h:
            name = h.get_text(strip=True)
            if name and 1 < len(name) < 60:
                unit["plan_name"] = name
                break

    return unit


class UniversalDOMExtractor(PlatformAdapter):
    """Adapter for unknown-CMS sites where plans appear as repeated sibling DOM elements.

    Fires last in the registry — all specific adapters take priority.
    Works on both static and Playwright-rendered HTML; gains the most value
    when called with rendered HTML (Phase 1 two-stage fetch).
    """

    name = "universal_dom"

    def detect(self, html: str, url: str) -> bool:
        if not html or len(html) < 5_000:
            return False
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return False
        return len(_find_best_card_group(soup)) >= 2

    async def extract(
        self,
        html: str,
        url: str,
        browser: "BrowserSession",
    ) -> List[Dict]:
        soup = BeautifulSoup(html, "html.parser")
        group = _find_best_card_group(soup)
        units = []
        for card in group:
            u = _parse_card(card)
            if u.get("bedrooms") is not None and u.get("price") is not None:
                units.append(u)
        logger.info(
            "UniversalDOMExtractor on %s: %d cards → %d valid units",
            url,
            len(group),
            len(units),
        )
        return units
