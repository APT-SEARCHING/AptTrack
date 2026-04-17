from __future__ import annotations

"""Tests for /api/v1/subscriptions endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

BASE = "/api/v1/subscriptions"
APTS_BASE = "/api/v1/apartments"


def _make_apartment(client, admin_headers):
    """Create a minimal apartment and return its id."""
    resp = client.post(
        APTS_BASE,
        json={"title": "Sub Test Apts", "city": "Oakland", "state": "CA", "zipcode": "94612"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def _sub_payload(apartment_id, **overrides):
    base = {
        "apartment_id": apartment_id,
        "target_price": 2000.0,
        "notify_email": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# POST /subscriptions
# ---------------------------------------------------------------------------

class TestCreateSubscription:
    def test_create_success(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(BASE, json=_sub_payload(apt_id), headers=user_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["apartment_id"] == apt_id
        assert data["target_price"] == 2000.0
        assert data["is_active"] is True

    def test_create_requires_auth(self, client: TestClient, admin_headers):
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(BASE, json=_sub_payload(apt_id))
        assert resp.status_code == 401

    def test_create_missing_target(self, client: TestClient, admin_headers, user_headers):
        """At least one threshold (target_price or price_drop_pct) is required."""
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(
            BASE,
            json={"apartment_id": apt_id, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 422

    def test_create_missing_scope(self, client: TestClient, user_headers):
        """At least one scope (apartment_id, plan_id, or city) is required."""
        resp = client.post(
            BASE,
            json={"target_price": 2000.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 422

    def test_create_with_pct_drop(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(
            BASE,
            json={"apartment_id": apt_id, "price_drop_pct": 5.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["price_drop_pct"] == 5.0

    def test_create_with_city_scope_rejected(self, client: TestClient, user_headers):
        """Area-level subscriptions are disabled (bug #5) — city alone → 422."""
        resp = client.post(
            BASE,
            json={"city": "Oakland", "target_price": 2000.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 422
        assert "temporarily disabled" in resp.json()["detail"]

    def test_pct_drop_out_of_range(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(
            BASE,
            json={"apartment_id": apt_id, "price_drop_pct": 150.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /subscriptions
# ---------------------------------------------------------------------------

class TestListSubscriptions:
    def test_list_own_subscriptions(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        # Create two subscriptions for regular user
        for _ in range(2):
            client.post(BASE, json=_sub_payload(apt_id), headers=user_headers)
        resp = client.get(BASE, headers=user_headers)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_ownership_scoping(self, client: TestClient, admin_headers, user_headers, other_headers):
        """Users can only see their own subscriptions."""
        apt_id = _make_apartment(client, admin_headers)
        client.post(BASE, json=_sub_payload(apt_id), headers=user_headers)
        client.post(BASE, json=_sub_payload(apt_id), headers=other_headers)

        # Each user should see only their own subscription
        user_resp = client.get(BASE, headers=user_headers)
        other_resp = client.get(BASE, headers=other_headers)
        assert len(user_resp.json()) == 1
        assert len(other_resp.json()) == 1
        assert user_resp.json()[0]["id"] != other_resp.json()[0]["id"]

    def test_list_requires_auth(self, client: TestClient):
        resp = client.get(BASE)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PUT /subscriptions/{id}
# ---------------------------------------------------------------------------

class TestUpdateSubscription:
    def test_update_own_subscription(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        created = client.post(BASE, json=_sub_payload(apt_id), headers=user_headers).json()
        resp = client.put(
            f"{BASE}/{created['id']}",
            json={"target_price": 1800.0},
            headers=user_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["target_price"] == 1800.0

    def test_cannot_update_other_users_subscription(
        self, client: TestClient, admin_headers, user_headers, other_headers
    ):
        apt_id = _make_apartment(client, admin_headers)
        created = client.post(BASE, json=_sub_payload(apt_id), headers=user_headers).json()
        resp = client.put(
            f"{BASE}/{created['id']}",
            json={"target_price": 999.0},
            headers=other_headers,
        )
        assert resp.status_code == 404

    def test_update_not_found(self, client: TestClient, user_headers):
        resp = client.put(f"{BASE}/99999", json={"target_price": 1000.0}, headers=user_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /subscriptions/{id}
# ---------------------------------------------------------------------------

class TestDeleteSubscription:
    def test_delete_own_subscription(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        created = client.post(BASE, json=_sub_payload(apt_id), headers=user_headers).json()
        resp = client.delete(f"{BASE}/{created['id']}", headers=user_headers)
        assert resp.status_code == 204
        # Confirm gone
        assert client.get(BASE, headers=user_headers).json() == []

    def test_cannot_delete_other_users_subscription(
        self, client: TestClient, admin_headers, user_headers, other_headers
    ):
        apt_id = _make_apartment(client, admin_headers)
        created = client.post(BASE, json=_sub_payload(apt_id), headers=user_headers).json()
        resp = client.delete(f"{BASE}/{created['id']}", headers=other_headers)
        assert resp.status_code == 404
        # Original subscription still exists
        assert len(client.get(BASE, headers=user_headers).json()) == 1

    def test_delete_requires_auth(self, client: TestClient):
        resp = client.delete(f"{BASE}/1")
        assert resp.status_code == 401

    def test_delete_not_found(self, client: TestClient, user_headers):
        resp = client.delete(f"{BASE}/99999", headers=user_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Bug #5: area-level subscription fields rejected at API layer
# ---------------------------------------------------------------------------

class TestAreaLevelRejected:
    """Any payload containing city, zipcode, min_bedrooms, or max_bedrooms
    must be rejected with 422 (area-level subscriptions temporarily disabled)."""

    def test_city_rejected(self, client: TestClient, user_headers):
        resp = client.post(
            BASE,
            json={"city": "San Jose", "target_price": 2000.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 422
        assert "temporarily disabled" in resp.json()["detail"]

    def test_zipcode_rejected(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(
            BASE,
            json={
                "apartment_id": apt_id,
                "zipcode": "94102",
                "target_price": 2000.0,
                "notify_email": True,
            },
            headers=user_headers,
        )
        assert resp.status_code == 422
        assert "temporarily disabled" in resp.json()["detail"]

    def test_min_bedrooms_rejected(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(
            BASE,
            json={
                "apartment_id": apt_id,
                "min_bedrooms": 1.0,
                "target_price": 2000.0,
                "notify_email": True,
            },
            headers=user_headers,
        )
        assert resp.status_code == 422

    def test_max_bedrooms_rejected(self, client: TestClient, admin_headers, user_headers):
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(
            BASE,
            json={
                "apartment_id": apt_id,
                "max_bedrooms": 2.0,
                "target_price": 2000.0,
                "notify_email": True,
            },
            headers=user_headers,
        )
        assert resp.status_code == 422

    def test_apartment_without_area_fields_accepted(
        self, client: TestClient, admin_headers, user_headers
    ):
        """Apartment-level sub with no area fields must still work."""
        apt_id = _make_apartment(client, admin_headers)
        resp = client.post(
            BASE,
            json={"apartment_id": apt_id, "target_price": 2000.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Baseline price capture (Phase A, Bug-2 pre-requisite)
# ---------------------------------------------------------------------------

def _seed_apartment_with_plan(db: Session, price: float = 3000.0) -> tuple:
    """Insert an Apartment + Plan directly and return (apartment_id, plan_id)."""
    from app.models.apartment import Apartment, Plan

    apt = Apartment(
        title="Baseline Test Apts", city="San Jose", state="CA",
        zipcode="95110", property_type="apartment", is_available=True,
    )
    db.add(apt)
    db.flush()

    plan = Plan(
        apartment_id=apt.id, name="1BR", bedrooms=1, bathrooms=1,
        area_sqft=600, price=price, is_available=True,
    )
    db.add(plan)
    db.flush()
    return apt.id, plan.id


def _seed_price_history(db: Session, plan_id: int, prices: list) -> None:
    """Insert PlanPriceHistory rows newest-first (prices[0] is most recent)."""
    from datetime import datetime, timedelta, timezone
    from app.models.apartment import PlanPriceHistory

    now = datetime.now(timezone.utc)
    for i, price in enumerate(prices):
        db.add(PlanPriceHistory(
            plan_id=plan_id,
            price=price,
            recorded_at=now - timedelta(days=i),
        ))
    db.flush()


class TestCreateSubscriptionBaseline:
    """Verify that create_subscription correctly captures baseline_price."""

    def test_explicit_baseline_from_frontend(
        self, client: TestClient, db: Session, admin_headers, user_headers
    ):
        """Frontend passes baseline_price explicitly — must be stored as-is."""
        apt_id, _ = _seed_apartment_with_plan(db, price=3000.0)
        resp = client.post(
            BASE,
            json={
                "apartment_id": apt_id,
                "target_price": 2500.0,
                "baseline_price": 3100.0,  # frontend-supplied
                "notify_email": True,
            },
            headers=user_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["baseline_price"] == 3100.0
        assert data["baseline_recorded_at"] is not None

    def test_inferred_baseline_from_price_history(
        self, client: TestClient, db: Session, user_headers
    ):
        """No baseline_price supplied — server infers from latest PlanPriceHistory."""
        apt_id, plan_id = _seed_apartment_with_plan(db, price=3000.0)
        _seed_price_history(db, plan_id, prices=[2900.0, 3000.0, 3100.0])

        resp = client.post(
            BASE,
            json={"plan_id": plan_id, "price_drop_pct": 5.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        # Most recent history price is 2900.0 (index 0 = newest)
        assert data["baseline_price"] == 2900.0
        assert data["baseline_recorded_at"] is not None

    def test_inferred_baseline_falls_back_to_plan_price(
        self, client: TestClient, db: Session, user_headers
    ):
        """No price history → server falls back to Plan.price."""
        apt_id, plan_id = _seed_apartment_with_plan(db, price=2750.0)
        # No PlanPriceHistory rows seeded

        resp = client.post(
            BASE,
            json={"plan_id": plan_id, "price_drop_pct": 5.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["baseline_price"] == 2750.0

    def test_baseline_none_when_no_price_data(
        self, client: TestClient, db: Session, user_headers
    ):
        """Plan exists with no price and no history — baseline should be None."""
        from app.models.apartment import Apartment, Plan

        apt = Apartment(
            title="No Price Apts", city="Oakland", state="CA",
            zipcode="94612", property_type="apartment", is_available=True,
        )
        db.add(apt)
        db.flush()
        plan = Plan(
            apartment_id=apt.id, name="TBD", bedrooms=1, bathrooms=1,
            area_sqft=500, price=None, is_available=True,
        )
        db.add(plan)
        db.flush()

        resp = client.post(
            BASE,
            json={"plan_id": plan.id, "price_drop_pct": 5.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["baseline_price"] is None
        assert data["baseline_recorded_at"] is None

    def test_inferred_baseline_apartment_level(
        self, client: TestClient, db: Session, user_headers
    ):
        """Apartment-level sub infers baseline as min available plan price."""
        from app.models.apartment import Apartment, Plan

        apt = Apartment(
            title="Multi Plan Apts", city="Fremont", state="CA",
            zipcode="94538", property_type="apartment", is_available=True,
        )
        db.add(apt)
        db.flush()
        for price in [2800.0, 3200.0, 3600.0]:
            db.add(Plan(
                apartment_id=apt.id, name=f"Plan {price}", bedrooms=1,
                bathrooms=1, area_sqft=600, price=price, is_available=True,
            ))
        db.flush()

        resp = client.post(
            BASE,
            json={"apartment_id": apt.id, "price_drop_pct": 10.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 201
        # Min available plan price
        assert resp.json()["baseline_price"] == 2800.0

    def test_update_does_not_change_baseline(
        self, client: TestClient, db: Session, user_headers
    ):
        """PUT /subscriptions/{id} must not expose or alter baseline_price."""
        apt_id, _ = _seed_apartment_with_plan(db, price=3000.0)
        created = client.post(
            BASE,
            json={"apartment_id": apt_id, "target_price": 2500.0, "notify_email": True},
            headers=user_headers,
        ).json()
        original_baseline = created["baseline_price"]

        updated = client.put(
            f"{BASE}/{created['id']}",
            json={"target_price": 2000.0},
            headers=user_headers,
        ).json()

        assert updated["target_price"] == 2000.0
        assert updated["baseline_price"] == original_baseline
