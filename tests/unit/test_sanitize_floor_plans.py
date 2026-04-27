"""
Tests for _sanitize_floor_plans deterministic contamination guards.
Covers BUG-04 (sibling property), BUG-05 (starting-from), BUG-06 (deposit floor).
"""
import pytest
from app.services.scraper_agent.models import FloorPlan
from app.worker import (
    _sanitize_floor_plans,
    _looks_like_sibling_property,
    _looks_like_starting_from_contamination,
    _BAY_AREA_RENT_FLOOR,
    _BAY_AREA_RENT_CEILING,
)


def fp(name="A1", beds=1, sqft=720.0, min_price=None, max_price=None,
       baths=1.0, unit_number=None, availability=None):
    """Quick FloorPlan factory for tests."""
    return FloorPlan(
        name=name, bedrooms=beds, size_sqft=sqft,
        min_price=min_price, max_price=max_price,
        bathrooms=baths, unit_number=unit_number, availability=availability,
    )


# ─── Filter A: sibling property heuristic ─────────────────────────────

class TestSiblingPropertyFilter:
    def test_filters_marina_playa(self):
        plans = [
            fp(name="Marina Playa", min_price=2475, max_price=2475),
            fp(name="A1", min_price=4200, max_price=4200),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert len(cleaned) == 1
        assert cleaned[0].name == "A1"
        assert summary["sibling_dropped"] == 1

    def test_filters_briarwood_apartments(self):
        plans = [
            fp(name="Briarwood Apartments", min_price=2981),
            fp(name="The Arches Apartments", min_price=3015),
            fp(name="Lorien Apartments", min_price=3845),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert len(cleaned) == 0
        assert summary["sibling_dropped"] == 3

    def test_keeps_legitimate_codes(self):
        plans = [
            fp(name="A1", min_price=3000),
            fp(name="B2G", min_price=3500),
            fp(name="1x1A", min_price=3100),
            fp(name="Studio S1", min_price=2800),
            fp(name="Plan E", min_price=4000),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert len(cleaned) == 5
        assert summary["sibling_dropped"] == 0

    def test_keeps_studio_loft(self):
        # "Studio A Loft" has a multi-word name but starts with Studio code
        plans = [fp(name="Studio A Loft", min_price=2800)]
        cleaned, _ = _sanitize_floor_plans(plans)
        assert len(cleaned) == 1

    def test_filters_property_with_apartments_word(self):
        plans = [
            fp(name="The Marc Apartments", min_price=2900),
            fp(name="A1", min_price=3000),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert len(cleaned) == 1
        assert cleaned[0].name == "A1"
        assert summary["sibling_dropped"] == 1

    def test_short_name_kept(self):
        # Filter requires len >= 5 and >= 2 words
        plans = [fp(name="Park", min_price=3000)]  # has keyword but 1 word
        cleaned, _ = _sanitize_floor_plans(plans)
        assert len(cleaned) == 1

    def test_helper_directly(self):
        assert _looks_like_sibling_property("Marina Playa") is True
        assert _looks_like_sibling_property("Briarwood Apartments") is True
        assert _looks_like_sibling_property("A1") is False
        assert _looks_like_sibling_property("Studio S1") is False
        assert _looks_like_sibling_property("1x1A") is False
        assert _looks_like_sibling_property("Plan E") is False
        # Edge cases
        assert _looks_like_sibling_property("") is False
        assert _looks_like_sibling_property("Park") is False  # 1 word


# ─── Filter B: deposit floor ──────────────────────────────────────────

class TestDepositFloor:
    def test_nulls_deposit_1000(self):
        plans = [fp(name="Studio Plan A", min_price=1000, max_price=1000)]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert len(cleaned) == 1
        assert cleaned[0].min_price is None
        assert cleaned[0].max_price is None
        assert summary["deposit_nulled"] == 1

    def test_nulls_deposit_500(self):
        plans = [fp(name="Studio", min_price=500, max_price=500)]
        cleaned, _ = _sanitize_floor_plans(plans)
        assert cleaned[0].min_price is None
        assert cleaned[0].max_price is None

    def test_keeps_legitimate_studio_1500(self):
        # Boundary: $1500 is the floor; values >= 1500 are kept
        plans = [fp(name="Studio", min_price=1500, max_price=1500)]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert cleaned[0].min_price == 1500
        assert summary["deposit_nulled"] == 0

    def test_nulls_below_floor_1499(self):
        plans = [fp(name="Studio", min_price=1499)]
        cleaned, _ = _sanitize_floor_plans(plans)
        assert cleaned[0].min_price is None

    def test_keeps_high_rent(self):
        plans = [fp(name="Penthouse", min_price=15000, max_price=18000)]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert cleaned[0].min_price == 15000
        assert cleaned[0].max_price == 18000
        assert summary["deposit_nulled"] == 0

    def test_nulls_above_ceiling(self):
        # 30000+ likely typo (annual stored as monthly)
        plans = [fp(name="Plan A", min_price=30000)]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert cleaned[0].min_price is None
        assert summary["ceiling_nulled"] == 1

    def test_null_already_null(self):
        plans = [fp(name="Studio", min_price=None, max_price=None)]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert cleaned[0].min_price is None
        assert summary["deposit_nulled"] == 0


# ─── Filter D: starting-from contamination ────────────────────────────

class TestStartingFromContamination:
    def test_5_plans_same_price_all_nulled(self):
        plans = [
            fp(name="A1", min_price=3200, max_price=3200),
            fp(name="A2", min_price=3200, max_price=3200),
            fp(name="A3", min_price=3200, max_price=3200),
            fp(name="B1", min_price=3200, max_price=3200),
            fp(name="B2", min_price=3200, max_price=3200),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert all(p.min_price is None for p in cleaned)
        assert all(p.max_price is None for p in cleaned)
        assert summary["starting_from_triggered"] is True

    def test_distinct_prices_unchanged(self):
        plans = [
            fp(name="A1", min_price=3200),
            fp(name="A2", min_price=3400),
            fp(name="A3", min_price=3600),
            fp(name="B1", min_price=4000),
            fp(name="B2", min_price=4200),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        prices = [p.min_price for p in cleaned]
        assert prices == [3200, 3400, 3600, 4000, 4200]
        assert summary["starting_from_triggered"] is False

    def test_few_plans_skip_check(self):
        # < 4 priced plans → don't trigger heuristic
        plans = [
            fp(name="A1", min_price=3200),
            fp(name="A2", min_price=3200),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert cleaned[0].min_price == 3200
        assert summary["starting_from_triggered"] is False

    def test_above_50pct_threshold_triggers(self):
        # 4/5 = 80% same → triggers
        plans = [
            fp(name="A1", min_price=3200),
            fp(name="A2", min_price=3200),
            fp(name="A3", min_price=3200),
            fp(name="A4", min_price=3200),
            fp(name="B1", min_price=5000),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert all(p.min_price is None for p in cleaned)
        assert summary["starting_from_triggered"] is True

    def test_below_50pct_threshold_unchanged(self):
        # 2/5 = 40% same → no trigger
        plans = [
            fp(name="A1", min_price=3200),
            fp(name="A2", min_price=3200),
            fp(name="A3", min_price=3500),
            fp(name="A4", min_price=3700),
            fp(name="A5", min_price=4100),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert summary["starting_from_triggered"] is False
        assert cleaned[0].min_price == 3200


# ─── Combined / regression tests ──────────────────────────────────────

class TestComposedFilters:
    def test_three_filters_compose(self):
        plans = [
            fp(name="Marina Playa", min_price=2475),  # sibling → drop
            fp(name="Studio A", min_price=800),         # deposit → null price
            fp(name="A1", min_price=3500),              # legit
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert len(cleaned) == 2
        names = {p.name for p in cleaned}
        assert names == {"Studio A", "A1"}
        studio = next(p for p in cleaned if p.name == "Studio A")
        assert studio.min_price is None
        a1 = next(p for p in cleaned if p.name == "A1")
        assert a1.min_price == 3500

    def test_canonical_typical_apt(self):
        # Mimics what rentmiro / theryden produce — distinct prices,
        # standard plan names. Must pass through unchanged.
        plans = [
            fp(name="Studio S1", min_price=2495, max_price=2495, beds=0, sqft=480),
            fp(name="A1", min_price=3000, max_price=3000, beds=1, sqft=680),
            fp(name="A2", min_price=3200, max_price=3200, beds=1, sqft=720),
            fp(name="B1", min_price=4100, max_price=4100, beds=2, sqft=950),
        ]
        cleaned, summary = _sanitize_floor_plans(plans)
        assert len(cleaned) == 4
        assert all(p.min_price is not None for p in cleaned)
        assert all(value == 0 for value in summary.values()
                   if isinstance(value, int))
        assert summary["starting_from_triggered"] is False

    def test_sanitize_returns_tuple(self):
        plans = [fp(name="A1", min_price=3000)]
        result = _sanitize_floor_plans(plans)
        assert isinstance(result, tuple)
        assert len(result) == 2
        cleaned, summary = result
        assert isinstance(cleaned, list)
        assert isinstance(summary, dict)
        expected_keys = {
            "sibling_dropped", "deposit_nulled",
            "ceiling_nulled", "starting_from_triggered"
        }
        assert set(summary.keys()) == expected_keys

    def test_empty_input(self):
        cleaned, summary = _sanitize_floor_plans([])
        assert cleaned == []
        assert summary["sibling_dropped"] == 0
