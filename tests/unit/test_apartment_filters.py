"""Unit tests for advanced apartment filter params.

Covers: pets_allowed, has_parking, min_sqft, max_sqft, available_before,
and a combination of several filters together.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401
from app.db.base_class import Base
from app.db.session import get_db
from app.main import app
from app.models.apartment import Apartment, Plan


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
# Seed: three apartments with distinct attribute combinations
# ---------------------------------------------------------------------------

def _seed(db: Session) -> None:
    configs = [
        # (title, pets, parking, sqft, avail_from_days_offset)
        ("Pet Friendly Lofts", True,  True,  650.0, 10),   # avail in 10 days
        ("No Pets Tower",      False, True,  900.0, 60),   # avail in 60 days
        ("Garage Gardens",     True,  False, 450.0, None), # no available_from
    ]
    for title, pets, parking, sqft, days in configs:
        apt = Apartment(
            title=title, city="San Jose", state="CA", zipcode="95101",
            property_type="apartment", is_available=True,
            pets_allowed=pets, has_parking=parking,
        )
        db.add(apt)
        db.flush()
        avail = None
        if days is not None:
            from datetime import timedelta
            avail = datetime.now(timezone.utc) + timedelta(days=days)
        db.add(Plan(
            apartment_id=apt.id, name="1BR", bedrooms=1, bathrooms=1,
            area_sqft=sqft, price=2000.0, is_available=True,
            available_from=avail,
        ))
    db.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_filter_pets_allowed_true(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments?pets_allowed=true")
    assert resp.status_code == 200
    titles = {a["title"] for a in resp.json()}
    assert "Pet Friendly Lofts" in titles
    assert "Garage Gardens" in titles
    assert "No Pets Tower" not in titles


def test_filter_pets_allowed_false(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments?pets_allowed=false")
    assert resp.status_code == 200
    titles = {a["title"] for a in resp.json()}
    assert "No Pets Tower" in titles
    assert "Pet Friendly Lofts" not in titles


def test_filter_has_parking_true(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments?has_parking=true")
    assert resp.status_code == 200
    titles = {a["title"] for a in resp.json()}
    assert "Pet Friendly Lofts" in titles
    assert "No Pets Tower" in titles
    assert "Garage Gardens" not in titles


def test_filter_min_sqft(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments?min_sqft=700")
    assert resp.status_code == 200
    titles = {a["title"] for a in resp.json()}
    assert "No Pets Tower" in titles        # 900 sqft
    assert "Pet Friendly Lofts" not in titles  # 650 sqft
    assert "Garage Gardens" not in titles      # 450 sqft


def test_filter_max_sqft(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments?max_sqft=500")
    assert resp.status_code == 200
    titles = {a["title"] for a in resp.json()}
    assert "Garage Gardens" in titles       # 450 sqft
    assert "No Pets Tower" not in titles    # 900 sqft


def test_filter_available_before(client, db_session):
    _seed(db_session)
    from datetime import timedelta
    # 30 days from now — should only include Pet Friendly Lofts (avail in 10d)
    cutoff = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    resp = client.get(f"/api/v1/apartments?available_before={cutoff}")
    assert resp.status_code == 200
    titles = {a["title"] for a in resp.json()}
    assert "Pet Friendly Lofts" in titles   # 10 days
    assert "No Pets Tower" not in titles    # 60 days
    assert "Garage Gardens" not in titles   # no available_from


def test_filter_combination(client, db_session):
    _seed(db_session)
    # pets=true + min_sqft=600 → only Pet Friendly Lofts (650 sqft, pets ok)
    resp = client.get("/api/v1/apartments?pets_allowed=true&min_sqft=600")
    assert resp.status_code == 200
    titles = {a["title"] for a in resp.json()}
    assert titles == {"Pet Friendly Lofts"}


def test_no_filter_returns_all(client, db_session):
    _seed(db_session)
    resp = client.get("/api/v1/apartments")
    assert resp.status_code == 200
    assert len(resp.json()) == 3
