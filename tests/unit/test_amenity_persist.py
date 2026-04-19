"""Unit tests for amenity persistence in _persist_scraped_prices (Phase 3B.5)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401
from app.db.base_class import Base
from app.models.apartment import Apartment, Plan
from app.services.scraper_agent.models import ApartmentData, FloorPlan


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
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _make_apartment(db: Session) -> Apartment:
    apt = Apartment(
        title="Amenity Test Apts", city="San Jose", state="CA",
        zipcode="95110", property_type="apartment", is_available=True,
    )
    db.add(apt)
    db.flush()
    plan = Plan(
        apartment_id=apt.id, name="1BR", bedrooms=1, bathrooms=1,
        area_sqft=700, price=2800.0, is_available=True,
    )
    db.add(plan)
    db.flush()
    return apt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAmenityPersist:

    def test_amenities_written_to_apartment(self, db: Session):
        """scraper result with amenities dict → fields saved on Apartment row."""
        from app.worker import _persist_scraped_prices

        apt = _make_apartment(db)
        result = ApartmentData(
            name="Amenity Test Apts",
            floor_plans=[FloorPlan(name="1BR", bedrooms=1, bathrooms=1, min_price=2800.0)],
            amenities={
                "pets_allowed": True,
                "has_parking": True,
                "has_pool": False,
                "has_gym": True,
                "has_dishwasher": None,     # unknown — should not overwrite
                "has_washer_dryer": True,
                "has_air_conditioning": True,
            },
        )
        _persist_scraped_prices(apt.id, result, db)

        refreshed = db.execute(select(Apartment).where(Apartment.id == apt.id)).scalar_one()
        assert refreshed.pets_allowed is True
        assert refreshed.has_parking is True
        assert refreshed.has_pool is False
        assert refreshed.has_gym is True
        assert refreshed.has_dishwasher is None   # null → not overwritten
        assert refreshed.has_washer_dryer is True
        assert refreshed.has_air_conditioning is True

    def test_null_amenity_does_not_overwrite_existing(self, db: Session):
        """A null amenity value from the LLM does not erase a previously-captured True."""
        from app.worker import _persist_scraped_prices

        apt = _make_apartment(db)
        apt.pets_allowed = True   # previously captured
        db.flush()

        # New scrape: LLM doesn't mention pets (null) — should preserve True
        result = ApartmentData(
            name="Amenity Test Apts",
            floor_plans=[FloorPlan(name="1BR", bedrooms=1, bathrooms=1, min_price=2800.0)],
            amenities={"pets_allowed": None, "has_pool": True},
        )
        _persist_scraped_prices(apt.id, result, db)

        refreshed = db.execute(select(Apartment).where(Apartment.id == apt.id)).scalar_one()
        assert refreshed.pets_allowed is True   # preserved
        assert refreshed.has_pool is True       # newly set

    def test_no_amenities_in_result_is_noop(self, db: Session):
        """Result with amenities=None does not touch Apartment amenity columns."""
        from app.worker import _persist_scraped_prices

        apt = _make_apartment(db)
        apt.has_gym = True
        db.flush()

        result = ApartmentData(
            name="Amenity Test Apts",
            floor_plans=[FloorPlan(name="1BR", bedrooms=1, bathrooms=1, min_price=2800.0)],
            amenities=None,
        )
        _persist_scraped_prices(apt.id, result, db)

        refreshed = db.execute(select(Apartment).where(Apartment.id == apt.id)).scalar_one()
        assert refreshed.has_gym is True   # untouched
