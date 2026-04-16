from __future__ import annotations

"""Tests for /api/v1/subscriptions endpoints."""

import pytest
from fastapi.testclient import TestClient

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

    def test_create_with_city_scope(self, client: TestClient, user_headers):
        resp = client.post(
            BASE,
            json={"city": "Oakland", "target_price": 2000.0, "notify_email": True},
            headers=user_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["city"] == "Oakland"

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
