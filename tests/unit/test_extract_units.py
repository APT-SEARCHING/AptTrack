"""Unit tests for the SightMap unit-block parser (B3 + B4 fixes).

_scrape_visible_units is a nested closure so we can't import it directly.
Instead we replicate the parsing logic — identical to the production code —
so tests catch any future regressions in the regex layer without requiring
a live browser.
"""
from __future__ import annotations

import re
from typing import List

# ---------------------------------------------------------------------------
# Constants replicated from browser_tools (keep in sync)
# ---------------------------------------------------------------------------

_UI_VERB_BLACKLIST = frozenset({
    "favorite", "available", "available now", "view details", "view detail",
    "tour", "tour now", "schedule tour", "select", "see details",
    "apply now", "contact", "share", "save", "compare", "hide", "show more",
    "schedule", "inquire",
})

_PLAN_NAME_REGEX = re.compile(r"^[A-Za-z][A-Za-z0-9\s\-\/\.]{1,40}$")

# ---------------------------------------------------------------------------
# Price regexes (keep in sync with browser_tools)
# ---------------------------------------------------------------------------

_BASE_RENT_BEFORE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)\s+Base\s+Rent", re.I)
_BASE_RENT_AFTER_RE  = re.compile(r"Base\s+Rent\s+\$?\s*([\d,]+(?:\.\d{1,2})?)", re.I)
_MO_PRICE_RE         = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)\s*(?:/|\s+per\s+)\s*mo", re.I)
_STANDALONE_PRICE_RE = re.compile(r"^\$\s*([\d,]+(?:\.\d{1,2})?)\s*$")
_FLOOR_RE            = re.compile(r"(\d{1,2})\n(\d+)\s+(?:Home|Unit|Apt)s?", re.I)


def _parse_price(s: str):
    try:
        val = float(s.replace(",", ""))
        if 500 <= val <= 25_000:
            return val
    except ValueError:
        pass
    return None


# ---------------------------------------------------------------------------
# Parser replicated from browser_tools._scrape_visible_units
# (keep in sync with backend/app/services/scraper_agent/browser_tools.py)
# ---------------------------------------------------------------------------

def _parse_sightmap_text(text: str) -> List[dict]:
    """Parse SightMap-style text into a list of unit dicts."""
    _UNIT_HEADER_RE = re.compile(r"^(?:HOME|APT)\s+\w+")
    blocks = re.split(r"\n(?=(?:HOME|APT)\s+\w+)", text)
    found: list[dict] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines or not _UNIT_HEADER_RE.match(lines[0]):
            continue
        unit_no = re.sub(r"^(?:HOME|APT)\s+", "", lines[0])
        unit: dict = {"unit_number": unit_no}
        for line in lines[1:]:
            # Plan name — first line that passes all filters
            if not unit.get("plan_name"):
                stripped = line.strip()
                if (stripped
                        and not re.search(r"\$|\d+\s*Bed|sq\.?\s*ft|waitlist", stripped, re.I)
                        and stripped.lower() not in _UI_VERB_BLACKLIST
                        and _PLAN_NAME_REGEX.match(stripped)
                        and not _UNIT_HEADER_RE.match(stripped.upper())):
                    unit["plan_name"] = stripped
            # Studio detection (must precede bed-count regex)
            if "bedrooms" not in unit and re.search(r"\bstudio\b", line, re.I):
                unit["bedrooms"] = 0
            # Bed count
            if "bedrooms" not in unit:
                m = re.search(r"(\d+)\s*Bed", line, re.I)
                if m:
                    unit["bedrooms"] = int(m.group(1))
            # Bath count
            if "bathrooms" not in unit:
                m = re.search(r"(\d+)\s*Bath", line, re.I)
                if m:
                    unit["bathrooms"] = int(m.group(1))
            # Sqft — handles "420 sq. ft.", "1,050 sqft", "680 sq ft"
            if "size_sqft" not in unit:
                m = re.search(r"([\d,]+)\s*sq\.?\s*ft", line, re.I)
                if m:
                    unit["size_sqft"] = int(m.group(1).replace(",", ""))
            # Availability
            if re.search(r"available|waitlist", line, re.I):
                unit["availability"] = line

        # Price — three passes: Base Rent preferred, then /mo total, then bare $
        price = None
        for ln in lines[1:]:
            _m = _BASE_RENT_BEFORE_RE.search(ln) or _BASE_RENT_AFTER_RE.search(ln)
            if _m:
                price = _parse_price(_m.group(1))
                break
        if price is None:
            for ln in lines[1:]:
                _m = _MO_PRICE_RE.search(ln)
                if _m:
                    price = _parse_price(_m.group(1))
                    break
        if price is None:
            for ln in lines[1:]:
                _m = _STANDALONE_PRICE_RE.match(ln.strip())
                if _m:
                    price = _parse_price(_m.group(1))
                    break
        if price is not None:
            unit["price"] = price

        found.append(unit)
    return found


def _floor_buttons(text: str) -> list[int]:
    """Replicate the floor-button detection regex from extract_all_units."""
    matches = _FLOOR_RE.findall(text)
    return sorted(int(f) for f, n in matches if int(n) > 0)


# ---------------------------------------------------------------------------
# Tests: multiline SightMap layout (the B3 fix target)
# ---------------------------------------------------------------------------

MULTILINE_STUDIO = """\
HOME E316
Studio S1
Studio
1 Bath
420 sq. ft.
Available Now
$2,950 /mo*
"""

def test_multiline_studio_bedrooms():
    units = _parse_sightmap_text(MULTILINE_STUDIO)
    assert len(units) == 1
    assert units[0]["bedrooms"] == 0


def test_multiline_studio_bathrooms():
    units = _parse_sightmap_text(MULTILINE_STUDIO)
    assert units[0]["bathrooms"] == 1


def test_multiline_studio_sqft():
    units = _parse_sightmap_text(MULTILINE_STUDIO)
    assert units[0]["size_sqft"] == 420


def test_multiline_studio_price():
    units = _parse_sightmap_text(MULTILINE_STUDIO)
    assert units[0]["price"] == 2950


def test_multiline_studio_unit_number():
    units = _parse_sightmap_text(MULTILINE_STUDIO)
    assert units[0]["unit_number"] == "E316"


def test_multiline_studio_plan_name():
    units = _parse_sightmap_text(MULTILINE_STUDIO)
    # "Studio S1" is the plan name; "Studio" alone on next line is the bedroom-type label
    assert units[0].get("plan_name") == "Studio S1"


# ---------------------------------------------------------------------------
# Tests: single-line format (backward compatibility)
# ---------------------------------------------------------------------------

SINGLE_LINE_1BR = """\
HOME A201
Plan A2
1 Bed / 1 Bath / 680 sq. ft.
Available 6/16
$3,100 /mo*
"""

def test_singleline_bedrooms():
    units = _parse_sightmap_text(SINGLE_LINE_1BR)
    assert len(units) == 1
    assert units[0]["bedrooms"] == 1


def test_singleline_bathrooms():
    units = _parse_sightmap_text(SINGLE_LINE_1BR)
    assert units[0]["bathrooms"] == 1


def test_singleline_sqft():
    units = _parse_sightmap_text(SINGLE_LINE_1BR)
    assert units[0]["size_sqft"] == 680


def test_singleline_price():
    units = _parse_sightmap_text(SINGLE_LINE_1BR)
    assert units[0]["price"] == 3100


def test_singleline_plan_name():
    units = _parse_sightmap_text(SINGLE_LINE_1BR)
    assert units[0].get("plan_name") == "Plan A2"


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

def test_sqft_with_comma():
    text = "HOME B501\nPlan B5\n2 Bed\n2 Bath\n1,050 sq. ft.\n$4,200 /mo*\n"
    units = _parse_sightmap_text(text)
    assert units[0]["size_sqft"] == 1050


def test_sqft_format_sqft_no_period():
    text = "HOME C102\nPlan C1\n1 Bed\n1 Bath\n650 sqft\nAvailable Now\n$3,000 /mo*\n"
    units = _parse_sightmap_text(text)
    assert units[0]["size_sqft"] == 650


def test_base_rent_preferred_over_total():
    text = "HOME D401\nPlan D4\n2 Bed\n2 Bath\n900 sq. ft.\nBase Rent $3,800\n$4,100 /mo*\n"
    units = _parse_sightmap_text(text)
    assert units[0]["price"] == 3800  # base rent, not total


def test_multiple_units_parsed():
    text = """\
HOME E316
Studio S1
Studio
1 Bath
420 sq. ft.
Available Now
$2,950 /mo*
HOME A201
Plan A2
1 Bed / 1 Bath / 680 sq. ft.
Available 6/16
$3,100 /mo*
"""
    units = _parse_sightmap_text(text)
    assert len(units) == 2
    assert units[0]["unit_number"] == "E316"
    assert units[1]["unit_number"] == "A201"


def test_availability_captured():
    units = _parse_sightmap_text(MULTILINE_STUDIO)
    assert "Available Now" in units[0].get("availability", "")


def test_waitlist_captured():
    text = "HOME F101\nS2\nStudio\n1 Bath\n490 sq. ft.\nWaitlist\n$3,200 /mo*\n"
    units = _parse_sightmap_text(text)
    assert "waitlist" in units[0].get("availability", "").lower()


# ---------------------------------------------------------------------------
# B4 tests: UI verb blacklist / plan name validation
# ---------------------------------------------------------------------------

def test_favorite_label_skipped_picks_real_plan_name():
    """'Favorite' as first line is rejected; subsequent plan name is captured."""
    text = (
        "HOME E316\n"
        "Favorite\n"
        "Studio S1\n"
        "Studio\n"
        "1 Bath\n"
        "420 sq. ft.\n"
        "Available Now\n"
        "$2,950 /mo*\n"
    )
    units = _parse_sightmap_text(text)
    assert units[0].get("plan_name") == "Studio S1"


def test_tour_now_skipped():
    """'Tour Now' is rejected by blacklist."""
    text = (
        "HOME B205\n"
        "Tour Now\n"
        "Plan B2\n"
        "1 Bed\n"
        "1 Bath\n"
        "680 sq. ft.\n"
        "$3,100 /mo*\n"
    )
    units = _parse_sightmap_text(text)
    assert units[0].get("plan_name") == "Plan B2"


def test_view_details_skipped():
    """'View Details' is rejected by blacklist."""
    text = (
        "HOME C301\n"
        "View Details\n"
        "Plan C3\n"
        "2 Bed\n"
        "2 Bath\n"
        "950 sq. ft.\n"
        "$4,200 /mo*\n"
    )
    units = _parse_sightmap_text(text)
    assert units[0].get("plan_name") == "Plan C3"


def test_studio_s1_correctly_captured():
    """'Studio S1' (plan code) is accepted as plan_name (not a UI verb)."""
    text = (
        "HOME D410\n"
        "Studio S1\n"
        "Studio\n"
        "1 Bath\n"
        "537 sq. ft.\n"
        "$2,800 /mo*\n"
    )
    units = _parse_sightmap_text(text)
    assert units[0].get("plan_name") == "Studio S1"


def test_only_ui_verbs_falls_back_to_type_label():
    """UI verbs skipped; 'Studio' (type label) becomes plan_name as best fallback."""
    text = (
        "HOME G101\n"
        "Favorite\n"
        "Tour Now\n"
        "View Details\n"
        "Studio\n"
        "1 Bath\n"
        "490 sq. ft.\n"
        "$2,600 /mo*\n"
    )
    units = _parse_sightmap_text(text)
    # All UI verbs rejected; "Studio" is a valid _PLAN_NAME_REGEX match
    assert units[0].get("plan_name") == "Studio"


def test_only_ui_verbs_truly_no_plan_name():
    """Block with no valid plan name line at all → plan_name absent."""
    text = (
        "HOME G102\n"
        "Favorite\n"
        "Tour Now\n"
        "1 Bath\n"
        "490 sq. ft.\n"
        "$2,600 /mo*\n"
    )
    units = _parse_sightmap_text(text)
    assert units[0].get("plan_name") is None


def test_one_bath_not_plan_name():
    """'1 Bath' starts with a digit → rejected by _PLAN_NAME_REGEX."""
    text = (
        "HOME H202\n"
        "1 Bath\n"
        "Studio\n"
        "490 sq. ft.\n"
        "$2,700 /mo*\n"
    )
    units = _parse_sightmap_text(text)
    # "1 Bath" starts with digit so fails _PLAN_NAME_REGEX;
    # "Studio" is standalone and passes (not a field-value line)
    assert units[0].get("plan_name") == "Studio"


def test_dollar_line_not_plan_name():
    """'$2,950 /mo*' is rejected (contains $)."""
    text = (
        "HOME I303\n"
        "Plan I3\n"
        "Studio\n"
        "1 Bath\n"
        "420 sq. ft.\n"
        "$2,950 /mo*\n"
    )
    units = _parse_sightmap_text(text)
    assert units[0].get("plan_name") == "Plan I3"


# ---------------------------------------------------------------------------
# New tests: Revela/decimal price formats + floor button variants
# ---------------------------------------------------------------------------

def test_revela_price_base_rent_preferred():
    """Base Rent line wins over /mo* total when both present (Revela format)."""
    block = (
        "APT 1103\nRevela Floorplan Studio 0-1A\n"
        "Studio / 1 Bath / 514 sq. ft.\n14 Months\nAvailable Now\n"
        "$3,445.12 /mo*\n$3,412 Base Rent\n"
    )
    units = _parse_sightmap_text(block)
    assert len(units) == 1
    assert units[0]["price"] == 3412.0


def test_decimal_mo_only():
    """$X,XXX.XX /mo* with no Base Rent line → use the decimal /mo price."""
    block = "APT 101\nPlan A\n1 Bed / 1 Bath / 600 sq. ft.\nAvailable Now\n$3,200.50 /mo*\n"
    units = _parse_sightmap_text(block)
    assert units[0]["price"] == 3200.5


def test_integer_mo_only():
    """$X,XXX /mo* (integer, no decimal) — back-compat with existing sites."""
    block = "HOME A201\nPlan A2\n1 Bed / 1 Bath / 680 sq. ft.\nAvailable 6/16\n$3,100 /mo*\n"
    units = _parse_sightmap_text(block)
    assert units[0]["price"] == 3100.0


def test_bare_dollar_line():
    """Bare $X,XXX line (last-resort pattern) is captured."""
    block = "HOME Z999\nPlan Z\n2 Bed / 2 Bath / 900 sq. ft.\nAvailable Now\n$3,200\n"
    units = _parse_sightmap_text(block)
    assert units[0]["price"] == 3200.0


def test_floor_regex_apt_singular():
    """APTS / APT suffixes are matched by the updated floor regex."""
    text = "1\n5 APTS\n2\n4 APTS\n3\n3 APTS\n4\n1 APT"
    assert _floor_buttons(text) == [1, 2, 3, 4]


def test_floor_regex_home_back_compat():
    """Original 'Homes' variant still matches."""
    text = "1\n5 Homes\n2\n3 Homes"
    assert _floor_buttons(text) == [1, 2]


def test_floor_regex_unit_back_compat():
    """Original 'Units' variant still matches."""
    text = "1\n5 Units"
    assert _floor_buttons(text) == [1]


def test_price_clamp_too_low():
    """Price below $500 is rejected (not a valid rent)."""
    block = "HOME X1\nPlan X\n1 Bed / 1 Bath / 500 sq. ft.\nAvailable Now\n$100 /mo\n"
    units = _parse_sightmap_text(block)
    assert units[0].get("price") is None


def test_price_clamp_too_high():
    """Price above $25,000 is rejected."""
    block = "HOME X2\nPlan X\n1 Bed / 1 Bath / 500 sq. ft.\nAvailable Now\n$50,000 /mo\n"
    units = _parse_sightmap_text(block)
    assert units[0].get("price") is None


def test_no_price_found():
    """Block with no dollar amounts → price absent, no crash."""
    block = "HOME X3\nPlan X\n1 Bed / 1 Bath / 500 sq. ft.\nAvailable Now\n"
    units = _parse_sightmap_text(block)
    assert len(units) == 1
    assert units[0].get("price") is None
