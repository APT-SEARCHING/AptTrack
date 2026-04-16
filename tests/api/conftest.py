from __future__ import annotations

"""Shared fixtures for API integration tests.

Uses a real database (PostgreSQL via TEST_DATABASE_URL, or SQLite in-memory as
default so tests run on any machine without a running Postgres instance).

Each test function gets an isolated session: data added in the test is never
committed to the underlying database — the outer connection-level transaction
is always rolled back on teardown.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Side-effect import: registers all models with Base.metadata
import app.db.base  # noqa: F401
from app.core.security import create_access_token, hash_password
from app.db.base_class import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User

_DEFAULT_TEST_URL = "sqlite:///:memory:"
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_URL)


# ---------------------------------------------------------------------------
# Disable rate limiting for all tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset slowapi in-memory counters before each test so no test hits 429."""
    from app.core.limiter import limiter
    try:
        limiter._storage.reset()
    except Exception:
        pass
    yield


# ---------------------------------------------------------------------------
# Engine — created once per test session
# ---------------------------------------------------------------------------

def _make_engine():
    if _TEST_DATABASE_URL.startswith("sqlite"):
        return create_engine(
            _TEST_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(_TEST_DATABASE_URL)


@pytest.fixture
def db():
    """Each test gets a brand-new in-memory SQLite database for perfect isolation."""
    engine = _make_engine()
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# TestClient that injects the test session
# ---------------------------------------------------------------------------

@pytest.fixture
def client(db):
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# User + auth token fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db):
    user = User(
        email="admin@test.example",
        hashed_password=hash_password("adminpass123"),
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def regular_user(db):
    user = User(
        email="user@test.example",
        hashed_password=hash_password("userpass123"),
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def other_user(db):
    user = User(
        email="other@test.example",
        hashed_password=hash_password("otherpass123"),
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def admin_headers(admin_user):
    token = create_access_token({"sub": str(admin_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user_headers(regular_user):
    token = create_access_token({"sub": str(regular_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_headers(other_user):
    token = create_access_token({"sub": str(other_user.id)})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Common data fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_apartment_payload():
    return {
        "title": "Test Apartments",
        "city": "San Francisco",
        "state": "CA",
        "zipcode": "94102",
        "property_type": "apartment",
        "plans": [
            {
                "name": "Studio A",
                "bedrooms": 0.0,
                "bathrooms": 1.0,
                "area_sqft": 450.0,
                "price": 2500.0,
                "is_available": True,
            }
        ],
    }
