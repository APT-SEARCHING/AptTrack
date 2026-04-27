"""Regression tests for _sanitize() in agent.py.

Covers:
- Slider-range contamination (current behaviour, >50% same pair)
- BUG-06: deposit amounts submitted as rent (price < $1,000, Bay Area floor)
- BUG-05: "starting from" overview price (>50% share exact same price)

Tests marked xfail for BUG-05/06 expected failures document intended future
behaviour — flip to passing once the fix is implemented.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add backend to path so agent.py imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))


def _import_sanitize():
    from app.services.scraper_agent.agent import _sanitize
    return _sanitize


def _fp(name, min_price=None, max_price=None):
    fp = MagicMock()
    fp.name = name
    fp.min_price = min_price
    fp.max_price = max_price
    return fp


def _data(plans):
    data = MagicMock()
    data.floor_plans = plans
    return data


# ---------------------------------------------------------------------------
# Slider contamination (existing behaviour — must stay green)
# ---------------------------------------------------------------------------

def test_slider_contamination_nulled():
    """>50% of plans share the same (min, max) pair → contamination, null them."""
    _sanitize = _import_sanitize()
    plans = [
        _fp("A1", 1500, 4000),
        _fp("A2", 1500, 4000),
        _fp("A3", 1500, 4000),
        _fp("B1", 2800, 2900),
    ]
    result = _sanitize(_data(plans))
    contaminated = [p for p in result.floor_plans if p.name in ("A1", "A2", "A3")]
    clean = next(p for p in result.floor_plans if p.name == "B1")
    for p in contaminated:
        assert p.min_price is None and p.max_price is None
    assert clean.min_price == 2800


def test_slider_all_same_single_plan_preserved():
    """Only one price pair exists (all plans same) — single plan, no contamination logic."""
    _sanitize = _import_sanitize()
    plans = [_fp("A1", 2500, 3500)]
    result = _sanitize(_data(plans))
    assert result.floor_plans[0].min_price == 2500


def test_slider_threshold_not_crossed():
    """Exactly 50% same pair — threshold is >50%, so no nulling."""
    _sanitize = _import_sanitize()
    plans = [
        _fp("A1", 1500, 4000),
        _fp("B1", 2800, 2900),
    ]
    result = _sanitize(_data(plans))
    a1 = next(p for p in result.floor_plans if p.name == "A1")
    assert a1.min_price == 1500


def test_none_input_passthrough():
    _sanitize = _import_sanitize()
    assert _sanitize(None) is None


def test_empty_plans_passthrough():
    _sanitize = _import_sanitize()
    data = _data([])
    assert _sanitize(data) is data


# ---------------------------------------------------------------------------
# BUG-06: deposit amounts as rent (min_price < $1,000) — future fix
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="BUG-06: _sanitize does not yet reject sub-$1000 deposit prices", strict=True)
def test_deposit_price_below_floor_nulled():
    """Plans with min_price < $1,000 should be nulled — Bay Area rent floor."""
    _sanitize = _import_sanitize()
    plans = [
        _fp("Studio Plan A", min_price=1000, max_price=1000),  # deposit, not rent
        _fp("1 Bed Plan J",  min_price=1000, max_price=1000),  # deposit, not rent
    ]
    result = _sanitize(_data(plans))
    for p in result.floor_plans:
        assert p.min_price is None, f"Expected null for deposit price on {p.name}"


@pytest.mark.xfail(reason="BUG-06: _sanitize does not yet reject sub-$1000 deposit prices", strict=True)
def test_hazelwood_tiny_deposit_nulled():
    """$500 / $600 (Hazelwood deposits) must be rejected."""
    _sanitize = _import_sanitize()
    plans = [
        _fp("Studio",     min_price=500, max_price=500),
        _fp("1 Bedroom",  min_price=600, max_price=600),
    ]
    result = _sanitize(_data(plans))
    for p in result.floor_plans:
        assert p.min_price is None


@pytest.mark.xfail(reason="BUG-06: _sanitize does not yet reject sub-$1000 deposit prices", strict=True)
def test_mixed_deposit_and_real_rent():
    """Null only the sub-$1000 plans; keep the valid rent."""
    _sanitize = _import_sanitize()
    plans = [
        _fp("Studio",    min_price=500,  max_price=500),
        _fp("1 Bed A1",  min_price=2055, max_price=2055),
    ]
    result = _sanitize(_data(plans))
    studio = next(p for p in result.floor_plans if p.name == "Studio")
    one_bed = next(p for p in result.floor_plans if p.name == "1 Bed A1")
    assert studio.min_price is None
    assert one_bed.min_price == 2055


# ---------------------------------------------------------------------------
# BUG-05: "starting from" overview price — future fix
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="BUG-05: _sanitize does not yet detect all-same overview price", strict=True)
def test_starting_from_all_same_price_nulled():
    """If >50% of plans share the exact same min_price (but not a (min,max) pair
    collision caught by the slider check), treat as 'starting from' contamination."""
    _sanitize = _import_sanitize()
    # Savoy: 23 plans all at $3,200 "starting from"
    plans = [_fp(f"Plan {i}", min_price=3200, max_price=3200) for i in range(23)]
    result = _sanitize(_data(plans))
    non_null = [p for p in result.floor_plans if p.min_price is not None]
    # Should keep at most 1 sentinel plan (or 0) — not all 23
    assert len(non_null) <= 1, f"Expected at most 1 priced plan, got {len(non_null)}"
