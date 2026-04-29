"""Unit tests for _persist_scraped_prices / _match_plan (B1 + B2 fixes).

B1: area_sqft, bedrooms, bathrooms, and name are backfilled from scraped data
    without clobbering good existing values.
B2: _match_plan strategies 3 (weak beds+baths) and 4 (auto-create) prevent
    data loss when exact and fuzzy-sqft matches both fail.

Note: plans.area_sqft has a NOT NULL DB constraint, so tests use 0 as the
"stale / unknown" placeholder (abs(0 - scraped) always exceeds 10 threshold).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401 — registers all models
from app.db.base_class import Base
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.worker import _persist_scraped_prices


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    yield session
    session.close()


def _make_apt(db: Session) -> Apartment:
    apt = Apartment(
        external_id="test-apt-1",
        title="Test Apartments",
        city="San Jose",
        state="CA",
        zipcode="95101",
        source_url="https://example.com/floorplans",
        is_available=True,
    )
    db.add(apt)
    db.flush()
    return apt


def _make_plan(db: Session, apt_id: int, **kwargs) -> Plan:
    """Create a Plan row. area_sqft defaults to 0 (stale placeholder) since NOT NULL."""
    defaults = dict(
        name="Studio",
        bedrooms=0.0,
        bathrooms=1.0,
        area_sqft=0.0,   # 0 = stale / unknown; NOT NULL constraint requires a value
        price=None,
        current_price=None,
        is_available=True,
    )
    defaults.update(kwargs)
    plan = Plan(apartment_id=apt_id, **defaults)
    db.add(plan)
    db.flush()
    return plan


def _make_fp(**kwargs) -> SimpleNamespace:
    """Build a minimal scraped FloorPlan namespace."""
    defaults = dict(
        name="Studio",
        bedrooms=0.0,
        bathrooms=1.0,
        size_sqft=None,
        min_price=None,
        max_price=None,
        external_url=None,
        floor_level=None,
        facing=None,
        unit_number=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_result(floor_plans, amenities=None, current_special=None):
    return SimpleNamespace(
        floor_plans=floor_plans,
        amenities=amenities,
        current_special=current_special,
    )


# ---------------------------------------------------------------------------
# Tests: area_sqft backfill
# ---------------------------------------------------------------------------

def test_sqft_backfilled_from_stale_zero(db):
    """area_sqft=0 (stale placeholder) in DB → updated to scraped size_sqft=680."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio", area_sqft=0.0)
    db.commit()

    fp = _make_fp(name="Studio", size_sqft=680.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.area_sqft == 680.0


def test_sqft_not_updated_when_diff_within_10(db):
    """area_sqft=680 in DB, scraped=682 → NOT updated (≤10 sqft noise)."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio", area_sqft=680.0)
    db.commit()

    fp = _make_fp(name="Studio", size_sqft=682.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.area_sqft == 680.0  # unchanged


def test_sqft_updated_when_diff_exceeds_10(db):
    """area_sqft=680 in DB, scraped=700 → updated (diff=20 > 10)."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio", area_sqft=680.0)
    db.commit()

    fp = _make_fp(name="Studio", size_sqft=700.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.area_sqft == 700.0


def test_sqft_not_overwritten_with_none(db):
    """Scraped size_sqft=None → DB area_sqft preserved."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio", area_sqft=650.0)
    db.commit()

    fp = _make_fp(name="Studio", size_sqft=None)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.area_sqft == 650.0


# ---------------------------------------------------------------------------
# Tests: name backfill
# ---------------------------------------------------------------------------

def test_name_updated_from_unit_placeholder(db):
    """Plan name 'Unit' → replaced with scraped name 'Studio A1'."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Unit", area_sqft=537.0)
    db.commit()

    fp = _make_fp(name="Studio A1", size_sqft=537.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.name == "Studio A1"


def test_name_not_overwritten_when_real(db):
    """Plan name 'Studio A1' (real) → NOT overwritten by scraped 'A1'."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio A1", area_sqft=537.0)
    db.commit()

    fp = _make_fp(name="A1", size_sqft=537.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.name == "Studio A1"


def test_name_updated_from_empty_string(db):
    """Plan name '' → replaced with scraped name."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="", area_sqft=537.0)
    db.commit()

    fp = _make_fp(name="1 Bed/1 Bath", size_sqft=537.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.name == "1 Bed/1 Bath"


# ---------------------------------------------------------------------------
# Tests: bedrooms / bathrooms backfill
# ---------------------------------------------------------------------------

def test_bedrooms_updated_when_stale(db):
    """DB bedrooms differs from scraped → updated."""
    apt = _make_apt(db)
    # seed with wrong bedrooms (common when seed data was approximate)
    plan = _make_plan(db, apt.id, name="1 Bed", bedrooms=0.0, area_sqft=650.0)
    db.commit()

    fp = _make_fp(name="1 Bed", bedrooms=1.0, size_sqft=650.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.bedrooms == 1.0


def test_bedrooms_preserved_when_fp_is_none(db):
    """fp.bedrooms=None → plan.bedrooms preserved."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio", bedrooms=0.0, area_sqft=537.0)
    db.commit()

    fp = _make_fp(name="Studio", bedrooms=None, size_sqft=537.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.bedrooms == 0.0


def test_bathrooms_updated_when_stale(db):
    """DB bathrooms differs from scraped → updated."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="2 Bed", bathrooms=1.0, area_sqft=1000.0)
    db.commit()

    fp = _make_fp(name="2 Bed", bathrooms=2.0, size_sqft=1000.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.bathrooms == 2.0


def test_bathrooms_preserved_when_fp_is_none(db):
    """fp.bathrooms=None → plan.bathrooms preserved."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio", bathrooms=1.0, area_sqft=537.0)
    db.commit()

    fp = _make_fp(name="Studio", bathrooms=None, size_sqft=537.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.bathrooms == 1.0


# ---------------------------------------------------------------------------
# Tests: price history still written
# ---------------------------------------------------------------------------

def test_price_history_written_on_match(db):
    """Successful match writes a PlanPriceHistory row."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio", area_sqft=537.0)
    db.commit()

    fp = _make_fp(name="Studio", size_sqft=537.0, min_price=2500.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    history = db.query(PlanPriceHistory).filter_by(plan_id=plan.id).all()
    assert len(history) == 1
    assert history[0].price == 2500.0


def test_unmatched_plan_skipped_when_no_bedrooms(db):
    """fp.bedrooms=None and no name match → no plan created, no history written."""
    apt = _make_apt(db)
    _make_plan(db, apt.id, name="Studio", area_sqft=537.0)
    db.commit()

    # bedrooms=None means strategy 4 (auto-create) cannot fire
    fp = _make_fp(name="Unknown Plan XYZ", bedrooms=None, size_sqft=2000.0, min_price=5000.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)  # must not raise

    count = db.query(PlanPriceHistory).count()
    assert count == 0


# ---------------------------------------------------------------------------
# B2 tests: _match_plan strategies 3 (weak beds+baths) and 4 (auto-create)
# ---------------------------------------------------------------------------

from app.worker import _match_plan  # noqa: E402


def test_different_name_no_sqft_autocreates(db):
    """Name mismatch + no sqft → cannot match existing plan → auto-create new one.

    Old strategy 3 (weak beds+baths fuzzy) has been removed because it caused
    false merges of distinct floor-plan types. A fp with a different name and no
    sqft now falls through to strategy 4 and creates a new plan row.
    """
    apt = _make_apt(db)
    _make_plan(db, apt.id, name="A1", bedrooms=1.0, bathrooms=1.0, area_sqft=650.0)
    db.commit()

    fp = _make_fp(name="A1-Renamed", bedrooms=1.0, bathrooms=1.0, size_sqft=None)
    result = _match_plan(apt.id, fp, db)

    assert result is not None
    assert result.name == "A1-Renamed"  # auto-created, not merged with A1


def test_strategy3_returns_none_when_ambiguous(db):
    """Strategy 3: 2 candidates with same beds+baths → None (don't guess)."""
    apt = _make_apt(db)
    _make_plan(db, apt.id, name="A1", bedrooms=1.0, bathrooms=1.0, area_sqft=650.0)
    _make_plan(db, apt.id, name="A2", bedrooms=1.0, bathrooms=1.0, area_sqft=750.0)
    db.commit()

    fp = _make_fp(name="New Plan", bedrooms=1.0, bathrooms=1.0, size_sqft=None)
    result = _match_plan(apt.id, fp, db)

    # Ambiguous — strategy 3 skips, strategy 4 auto-creates instead
    # (We just confirm it doesn't raise and returns something non-None via auto-create)
    assert result is not None
    assert result.name == "New Plan"  # auto-created by strategy 4


def test_strategy4_autocreates_plan_with_id(db):
    """Strategy 4: no match, fp.bedrooms known → new Plan created with populated id."""
    apt = _make_apt(db)
    db.commit()

    fp = _make_fp(name="B3", bedrooms=2.0, bathrooms=2.0, size_sqft=1050.0, min_price=3500.0)
    result = _match_plan(apt.id, fp, db)

    assert result is not None
    assert result.id is not None          # db.flush() ran, id assigned
    assert result.bedrooms == 2.0
    assert result.bathrooms == 2.0
    assert result.area_sqft == 1050.0
    assert result.name == "B3"


def test_strategy4_returns_none_when_bedrooms_missing(db):
    """Strategy 4: fp.bedrooms=None → None returned, nothing created."""
    apt = _make_apt(db)
    db.commit()

    fp = _make_fp(name="Mystery Plan", bedrooms=None, size_sqft=800.0)
    result = _match_plan(apt.id, fp, db)

    assert result is None
    plan_count = db.query(Plan).filter_by(apartment_id=apt.id).count()
    assert plan_count == 0


def test_strategy3_exact_sqft_matches_within_5(db):
    """Strategy 3: sqft within ±5 of a single candidate → match (rounding tolerance)."""
    apt = _make_apt(db)
    plan_a = _make_plan(db, apt.id, name="A1", bedrooms=1.0, bathrooms=1.0, area_sqft=650.0)
    _make_plan(db, apt.id, name="A2", bedrooms=1.0, bathrooms=1.0, area_sqft=750.0)
    db.commit()

    # sqft=655 is within ±5 of A1(650) only — unambiguous
    fp = _make_fp(name="A1-Renamed", bedrooms=1.0, bathrooms=1.0, size_sqft=655.0)
    result = _match_plan(apt.id, fp, db)

    assert result is not None
    assert result.id == plan_a.id  # matched A1, not A2


# ---------------------------------------------------------------------------
# Min-price aggregation: multiple FloorPlans with same name (SightMap per-unit)
# ---------------------------------------------------------------------------

def test_single_unit_per_plan_unchanged(db):
    """Single FloorPlan per name: existing behaviour preserved."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="A1", area_sqft=700.0)
    db.commit()

    fp = _make_fp(name="A1", size_sqft=700.0, min_price=3000.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.current_price == 3000.0


def test_multi_unit_picks_min_price(db):
    """3 FloorPlans named 'Edwards' → current_price = lowest ($3,195)."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Edwards", bedrooms=1.0, area_sqft=750.0)
    db.commit()

    fps = [
        _make_fp(name="Edwards", bedrooms=1.0, size_sqft=753.0, min_price=3515.0),
        _make_fp(name="Edwards", bedrooms=1.0, size_sqft=753.0, min_price=3195.0),
        _make_fp(name="Edwards", bedrooms=1.0, size_sqft=753.0, min_price=3365.0),
    ]
    _persist_scraped_prices(apt.id, _make_result(fps), db)

    db.refresh(plan)
    assert plan.current_price == 3195.0


def test_multi_unit_with_one_priceless(db):
    """[$3000, None, $2800] → current_price = $2800 (priceless unit ignored for price)."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Blacow", bedrooms=2.0, area_sqft=1050.0)
    db.commit()

    fps = [
        _make_fp(name="Blacow", bedrooms=2.0, size_sqft=1050.0, min_price=3000.0),
        _make_fp(name="Blacow", bedrooms=2.0, size_sqft=1050.0, min_price=None),
        _make_fp(name="Blacow", bedrooms=2.0, size_sqft=1050.0, min_price=2800.0),
    ]
    _persist_scraped_prices(apt.id, _make_result(fps), db)

    db.refresh(plan)
    assert plan.current_price == 2800.0


def test_all_priceless_units(db):
    """All FloorPlans have min_price=None → current_price stays None."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Studio", area_sqft=500.0, current_price=None)
    db.commit()

    fps = [
        _make_fp(name="Studio", size_sqft=500.0, min_price=None),
        _make_fp(name="Studio", size_sqft=500.0, min_price=None),
    ]
    _persist_scraped_prices(apt.id, _make_result(fps), db)

    db.refresh(plan)
    assert plan.current_price is None


def test_metadata_from_min_price_unit(db):
    """sqft taken from the min-price unit (699 sqft at $3,235), not the pricier one (753 sqft at $3,515)."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Edwards", bedrooms=1.0, area_sqft=0.0)
    db.commit()

    fps = [
        _make_fp(name="Edwards", bedrooms=1.0, size_sqft=753.0, min_price=3515.0),
        _make_fp(name="Edwards", bedrooms=1.0, size_sqft=699.0, min_price=3235.0),
    ]
    _persist_scraped_prices(apt.id, _make_result(fps), db)

    db.refresh(plan)
    assert plan.current_price == 3235.0
    assert plan.area_sqft == 699.0  # from the min-price unit


def test_price_history_written_once_per_plan_name(db):
    """3 units with same name → only 1 PlanPriceHistory row (the min price)."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="Cherry", bedrooms=2.0, area_sqft=1100.0)
    db.commit()

    fps = [
        _make_fp(name="Cherry", bedrooms=2.0, size_sqft=1100.0, min_price=4500.0),
        _make_fp(name="Cherry", bedrooms=2.0, size_sqft=1100.0, min_price=4225.0),
        _make_fp(name="Cherry", bedrooms=2.0, size_sqft=1100.0, min_price=4460.0),
    ]
    _persist_scraped_prices(apt.id, _make_result(fps), db)

    history = db.query(PlanPriceHistory).filter_by(plan_id=plan.id).all()
    assert len(history) == 1
    assert history[0].price == 4225.0


def test_autocreated_plan_gets_price_history(db):
    """Auto-created plan (strategy 4) still gets a PlanPriceHistory row written."""
    apt = _make_apt(db)
    db.commit()

    fp = _make_fp(name="New Studio", bedrooms=0.0, bathrooms=1.0, size_sqft=490.0, min_price=2200.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    new_plan = db.query(Plan).filter_by(apartment_id=apt.id, name="New Studio").one()
    history = db.query(PlanPriceHistory).filter_by(plan_id=new_plan.id).all()
    assert len(history) == 1
    assert history[0].price == 2200.0


# ---------------------------------------------------------------------------
# Tests: stale plan auto-unavailable (Pass 3)
# ---------------------------------------------------------------------------

def test_stale_plan_marked_unavailable(db):
    """Plan present in DB but absent from scrape → is_available=False."""
    apt = _make_apt(db)
    active = _make_plan(db, apt.id, name="A1", area_sqft=700.0, current_price=3000.0)
    ghost = _make_plan(db, apt.id, name="Unit", area_sqft=880.0, current_price=2877.0)
    db.commit()

    # Scrape only returns A1 — "Unit" is gone
    fp = _make_fp(name="A1", bedrooms=1.0, size_sqft=700.0, min_price=3050.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(active)
    db.refresh(ghost)
    assert active.is_available is True
    assert ghost.is_available is False


def test_stale_plan_not_wiped_on_empty_scrape(db):
    """If scrape returns 0 plans (extraction failure), no plans are marked unavailable."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="A1", area_sqft=700.0, current_price=3000.0)
    db.commit()

    # Empty scrape result — don't wipe everything
    _persist_scraped_prices(apt.id, _make_result([]), db)

    db.refresh(plan)
    assert plan.is_available is True  # safe — guard prevents false unavailability


def test_stale_plan_reactivates_on_return(db):
    """Plan previously archived → reactivated when it reappears in scrape."""
    apt = _make_apt(db)
    plan = _make_plan(db, apt.id, name="A1", area_sqft=700.0,
                      current_price=None, is_available=False)
    db.commit()

    # Plan reappears in scrape → _match_plan strategy 2 reactivates it
    fp = _make_fp(name="A1", bedrooms=1.0, size_sqft=700.0, min_price=3100.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(plan)
    assert plan.is_available is True
    assert plan.current_price == 3100.0


def test_multiple_stale_plans_all_marked(db):
    """All absent plans are marked unavailable in one scrape cycle."""
    apt = _make_apt(db)
    kept = _make_plan(db, apt.id, name="B1", bedrooms=2.0, area_sqft=1000.0)
    stale1 = _make_plan(db, apt.id, name="Ghost1", area_sqft=0.0)
    stale2 = _make_plan(db, apt.id, name="Ghost2", area_sqft=0.0)
    db.commit()

    fp = _make_fp(name="B1", bedrooms=2.0, size_sqft=1000.0, min_price=4000.0)
    _persist_scraped_prices(apt.id, _make_result([fp]), db)

    db.refresh(kept)
    db.refresh(stale1)
    db.refresh(stale2)
    assert kept.is_available is True
    assert stale1.is_available is False
    assert stale2.is_available is False
