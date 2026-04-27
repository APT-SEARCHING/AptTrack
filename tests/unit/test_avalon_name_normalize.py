"""Tests for _normalize_avalon_plan_names — BUG-03 generic name unblocking."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.worker import _normalize_avalon_plan_names, _GENERIC_NAME_RE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan(name, bedrooms, area_sqft, apt_id=1):
    p = MagicMock()
    p.name = name
    p.bedrooms = bedrooms
    p.area_sqft = area_sqft
    p.apartment_id = apt_id
    p.is_available = True
    return p


def _fp(name, bedrooms, size_sqft):
    fp = MagicMock()
    fp.name = name
    fp.bedrooms = bedrooms
    fp.size_sqft = size_sqft
    return fp


def _db_with_plans(plans):
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = plans
    db.execute.return_value = result
    return db


# ---------------------------------------------------------------------------
# _GENERIC_NAME_RE pattern tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "1 Bed / 1 Bath",
    "1 Bedroom / 1 Bath",
    "2 Bed / 2 Bath",
    "Studio / 1 Bath",
    "studio/1bath",
    "1 bed-1 bath",
])
def test_generic_pattern_matches(name):
    assert _GENERIC_NAME_RE.match(name), f"Expected match for: {name!r}"


@pytest.mark.parametrize("name", [
    "A2G",
    "B1G",
    "S1A",
    "1x1A",
    "Plan A",
])
def test_generic_pattern_no_match(name):
    assert not _GENERIC_NAME_RE.match(name), f"Expected no match for: {name!r}"


# ---------------------------------------------------------------------------
# _normalize_avalon_plan_names behavioural tests
# ---------------------------------------------------------------------------

AVALON_URL = "https://www.avaloncommunities.com/california/san-jose-apartments/eaves-san-jose/floor-plans"
EAVES_URL = "https://www.eavesbyavalon.com/california/san-jose/eaves-san-jose"
NON_AVALON_URL = "https://rentmiro.com/floorplans"


def test_renames_generic_to_specific():
    plan = _plan("1 Bed / 1 Bath", bedrooms=1, area_sqft=720)
    db = _db_with_plans([plan])
    fps = [_fp("A2G", bedrooms=1, size_sqft=722)]  # sqft within ±5%

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 1
    assert plan.name == "A2G"
    db.flush.assert_called_once()


def test_no_match_beds_mismatch():
    plan = _plan("1 Bed / 1 Bath", bedrooms=2, area_sqft=720)
    db = _db_with_plans([plan])
    fps = [_fp("A2G", bedrooms=1, size_sqft=722)]

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 0
    assert plan.name == "1 Bed / 1 Bath"
    db.flush.assert_not_called()


def test_sqft_outside_tolerance():
    plan = _plan("1 Bed / 1 Bath", bedrooms=1, area_sqft=720)
    db = _db_with_plans([plan])
    fps = [_fp("A2G", bedrooms=1, size_sqft=900)]  # 25% off

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 0
    assert plan.name == "1 Bed / 1 Bath"


def test_already_specific_no_rename():
    plan = _plan("A2G", bedrooms=1, area_sqft=720)
    db = _db_with_plans([plan])
    fps = [_fp("A2G", bedrooms=1, size_sqft=720)]

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 0
    db.flush.assert_not_called()


def test_non_avalon_apt_skipped():
    plan = _plan("1 Bed / 1 Bath", bedrooms=1, area_sqft=720)
    db = MagicMock()
    fps = [_fp("A2G", bedrooms=1, size_sqft=720)]

    count = _normalize_avalon_plan_names(1, NON_AVALON_URL, fps, db)

    assert count == 0
    db.execute.assert_not_called()


def test_adapter_returns_generic_skipped():
    """Adapter also returned a generic name — nothing better to rename to."""
    plan = _plan("1 Bed / 1 Bath", bedrooms=1, area_sqft=720)
    db = _db_with_plans([plan])
    fps = [_fp("1 Bed / 1 Bath", bedrooms=1, size_sqft=720)]

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 0
    assert plan.name == "1 Bed / 1 Bath"


def test_studio_pattern_recognized():
    plan = _plan("Studio / 1 Bath", bedrooms=0, area_sqft=580)
    db = _db_with_plans([plan])
    fps = [_fp("S1A", bedrooms=0, size_sqft=580)]

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 1
    assert plan.name == "S1A"


def test_existing_specific_plans_unchanged():
    """Mixed DB: specific plan untouched; generic plan renamed to the other code."""
    plan_specific = _plan("A2G", bedrooms=1, area_sqft=720)
    plan_generic = _plan("1 Bed / 1 Bath", bedrooms=2, area_sqft=950)
    db = _db_with_plans([plan_specific, plan_generic])
    fps = [
        _fp("A2G", bedrooms=1, size_sqft=720),
        _fp("B1G", bedrooms=2, size_sqft=950),
    ]

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 1
    assert plan_specific.name == "A2G"   # unchanged
    assert plan_generic.name == "B1G"    # renamed


def test_eaves_domain_also_matched():
    plan = _plan("Studio / 1 Bath", bedrooms=0, area_sqft=400)
    db = _db_with_plans([plan])
    fps = [_fp("S1G", bedrooms=0, size_sqft=400)]

    count = _normalize_avalon_plan_names(1, EAVES_URL, fps, db)

    assert count == 1
    assert plan.name == "S1G"


def test_no_sqft_on_fp_skipped():
    """FP without sqft cannot be matched — skip it."""
    plan = _plan("1 Bed / 1 Bath", bedrooms=1, area_sqft=720)
    db = _db_with_plans([plan])
    fps = [_fp("A2G", bedrooms=1, size_sqft=None)]

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 0


def test_no_sqft_on_db_plan_skipped():
    """DB plan without area_sqft cannot be sqft-matched — skip it."""
    plan = _plan("1 Bed / 1 Bath", bedrooms=1, area_sqft=None)
    db = _db_with_plans([plan])
    fps = [_fp("A2G", bedrooms=1, size_sqft=720)]

    count = _normalize_avalon_plan_names(1, AVALON_URL, fps, db)

    assert count == 0
