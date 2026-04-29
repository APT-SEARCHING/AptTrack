"""
Unit tests for SightMap plan-name validation guards (BUG-16).

Verifies that _NOT_A_PLAN_NAME_RE and _UNIT_NUMBER_RE correctly reject
UI verb phrases and bare unit numbers that SightMap injects in the
position where real plan codes appear.
"""
import re
import pytest
from app.services.scraper_agent.browser_tools import (
    _NOT_A_PLAN_NAME_RE,
    _UNIT_NUMBER_RE,
    _PLAN_NAME_REGEX,
    _UI_VERB_BLACKLIST,
)


# ─── _NOT_A_PLAN_NAME_RE: prefix-verb rejection ───────────────────────────────

class TestNotAPlanNameRe:
    def test_rejects_availability_date_may(self):
        assert _NOT_A_PLAN_NAME_RE.match("Available May 7th")

    def test_rejects_availability_date_jun(self):
        assert _NOT_A_PLAN_NAME_RE.match("Available Jun 5th")

    def test_rejects_availability_date_jul(self):
        assert _NOT_A_PLAN_NAME_RE.match("Available Jul 7th")

    def test_rejects_request_a_tour(self):
        assert _NOT_A_PLAN_NAME_RE.match("Request a Tour")

    def test_rejects_schedule_tour(self):
        assert _NOT_A_PLAN_NAME_RE.match("Schedule Tour")

    def test_rejects_view_details(self):
        assert _NOT_A_PLAN_NAME_RE.match("View Details")

    def test_rejects_apply_now(self):
        assert _NOT_A_PLAN_NAME_RE.match("Apply Now")

    def test_rejects_contact_us(self):
        assert _NOT_A_PLAN_NAME_RE.match("Contact Us")

    def test_rejects_select_unit(self):
        assert _NOT_A_PLAN_NAME_RE.match("Select Unit")

    def test_rejects_see_details(self):
        assert _NOT_A_PLAN_NAME_RE.match("See Details")

    def test_case_insensitive(self):
        assert _NOT_A_PLAN_NAME_RE.match("AVAILABLE May 7th")
        assert _NOT_A_PLAN_NAME_RE.match("available may 7th")

    # Real plan codes must NOT match
    def test_accepts_plan_code_a1(self):
        assert not _NOT_A_PLAN_NAME_RE.match("A1")

    def test_accepts_plan_code_s5(self):
        assert not _NOT_A_PLAN_NAME_RE.match("S5")

    def test_accepts_plan_code_b12(self):
        assert not _NOT_A_PLAN_NAME_RE.match("B12")

    def test_accepts_studio_a(self):
        assert not _NOT_A_PLAN_NAME_RE.match("Studio A")

    def test_accepts_studio_b_loft(self):
        assert not _NOT_A_PLAN_NAME_RE.match("Studio B Loft")

    def test_accepts_plan_1b(self):
        assert not _NOT_A_PLAN_NAME_RE.match("Plan 1B")

    def test_accepts_trail_names(self):
        # BUG-14 regression: Tolman real plan names
        assert not _NOT_A_PLAN_NAME_RE.match("Dry Creek")
        assert not _NOT_A_PLAN_NAME_RE.match("High Ridge")
        assert not _NOT_A_PLAN_NAME_RE.match("Vista Peak")


# ─── _UNIT_NUMBER_RE: bare unit number rejection ──────────────────────────────

class TestUnitNumberRe:
    def test_rejects_e303(self):
        assert _UNIT_NUMBER_RE.match("E303")

    def test_rejects_a1023(self):
        assert _UNIT_NUMBER_RE.match("A1023")

    def test_rejects_b205(self):
        assert _UNIT_NUMBER_RE.match("B205")

    def test_rejects_c100(self):
        assert _UNIT_NUMBER_RE.match("C100")

    # Real plan codes: 1–2 digit suffixes must NOT match
    def test_accepts_a1(self):
        assert not _UNIT_NUMBER_RE.match("A1")

    def test_accepts_a18(self):
        assert not _UNIT_NUMBER_RE.match("A18")

    def test_accepts_s5(self):
        assert not _UNIT_NUMBER_RE.match("S5")

    def test_accepts_b12(self):
        assert not _UNIT_NUMBER_RE.match("B12")

    def test_accepts_engrain_1f(self):
        # Engrain format: digit-first, no leading letter → doesn't match
        assert not _UNIT_NUMBER_RE.match("1F")

    def test_accepts_plan_1f(self):
        assert not _UNIT_NUMBER_RE.match("Plan 1F")

    def test_accepts_multi_word(self):
        # Must be exactly one letter + digits, no spaces
        assert not _UNIT_NUMBER_RE.match("A 303")
        assert not _UNIT_NUMBER_RE.match("Studio A")


# ─── Integration: both guards compose correctly with existing checks ──────────

class TestComposition:
    """Verify ghost strings that slipped through old code are now blocked,
    and that clean plan names still pass all three layers."""

    GHOST_NAMES = [
        "Available May 7th",
        "Available May 6th",
        "Available Jul 7th",
        "Available Jun 5th",
        "Request a Tour",
        "E303",
    ]

    LEGIT_NAMES = [
        "A1", "A2", "A18", "S5", "B12",
        "Studio A", "Studio B Loft", "Plan 1B",
        "Dry Creek", "High Ridge", "Vista Peak",
    ]

    def _would_be_accepted(self, name: str) -> bool:
        """Simulate the full guard chain from the extraction loop."""
        import re as _re
        stripped = name.strip()
        if not stripped:
            return False
        if _NOT_A_PLAN_NAME_RE.match(stripped):
            return False
        if _UNIT_NUMBER_RE.match(stripped):
            return False
        if _re.search(r"\$|\d+\s*Bed|sq\.?\s*ft|waitlist", stripped, _re.I):
            return False
        if stripped.lower() in _UI_VERB_BLACKLIST:
            return False
        if not _PLAN_NAME_REGEX.match(stripped):
            return False
        return True

    def test_all_ghost_names_blocked(self):
        for name in self.GHOST_NAMES:
            assert not self._would_be_accepted(name), f"Ghost name not blocked: {name!r}"

    def test_all_legit_names_accepted(self):
        for name in self.LEGIT_NAMES:
            assert self._would_be_accepted(name), f"Legit name blocked: {name!r}"

    def test_block_order_available_date(self):
        # "Available May 7th" is caught by _NOT_A_PLAN_NAME_RE before any other check
        assert _NOT_A_PLAN_NAME_RE.match("Available May 7th")
        # It would otherwise pass _PLAN_NAME_REGEX (starts with letter, valid chars)
        assert _PLAN_NAME_REGEX.match("Available May 7th")

    def test_block_order_unit_number(self):
        # "E303" is caught by _UNIT_NUMBER_RE
        assert _UNIT_NUMBER_RE.match("E303")
        # It would otherwise pass _PLAN_NAME_REGEX
        assert _PLAN_NAME_REGEX.match("E303")
