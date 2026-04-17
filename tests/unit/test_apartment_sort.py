"""Unit tests for GET /apartments?sort= query parameter.

Uses an in-memory SQLite database via TestClient so no running server is needed.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401 — registers all models with Base.metadata
from app.db.base_class import Base
from app.db.session import get_db
from app.main import app
from app.models.apartment import Apartment, Plan


# ---------------------------------------------------------------------------
# In-memory DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helper
# ---------------------------------------------------------------------------

def _seed(db: Session) -> None:
    """Three apartments with known min prices for deterministic sort assertions."""
    for title, city, price in [
        ("Cheap Arms",    "Oakland",       1_500.0),
        ("Mid Tower",     "San Jose",      3_000.0),
        ("Luxury Spire",  "San Francisco", 6_000.0),
    ]:
        apt = Apartment(
            title=title, city=city, state="CA", zipcode="00000",
            property_type="apartment", is_available=True,
        )
        db.add(apt)
        db.flush()
        db.add(Plan(
            apartment_id=apt.id, name="1BR", bedrooms=1, bathrooms=1,
            area_sqft=600.0, price=price, is_available=True,
        ))
    db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sort_price_asc(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments?sort=price_asc")
    assert resp.status_code == 200
    titles = [a["title"] for a in resp.json()]
    assert titles == ["Cheap Arms", "Mid Tower", "Luxury Spire"]


def test_sort_price_desc(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments?sort=price_desc")
    assert resp.status_code == 200
    titles = [a["title"] for a in resp.json()]
    assert titles == ["Luxury Spire", "Mid Tower", "Cheap Arms"]


def test_sort_name_asc(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments?sort=name_asc")
    assert resp.status_code == 200
    titles = [a["title"] for a in resp.json()]
    assert titles == ["Cheap Arms", "Luxury Spire", "Mid Tower"]


def test_sort_updated_desc(client, db_session):
    """updated_desc just has to return 200 and all rows — order depends on insert time."""
    _seed(db_session)
    resp = client.get("/api/v1/apartments?sort=updated_desc")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_sort_default_is_price_asc(client, db_session):
    _seed(db_session)
    resp_default = client.get("/api/v1/apartments")
    resp_explicit = client.get("/api/v1/apartments?sort=price_asc")
    assert resp_default.json() == resp_explicit.json()


def test_sort_invalid_value_returns_422(client, db_session):
    resp = client.get("/api/v1/apartments?sort=bogus")
    assert resp.status_code == 422
