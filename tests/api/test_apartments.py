from __future__ import annotations

"""Tests for /api/v1/apartments endpoints."""

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1"


def _create_apartment(client, headers, payload=None):
    if payload is None:
        payload = {
            "title": "Test Apartments",
            "city": "Oakland",
            "state": "CA",
            "zipcode": "94612",
        }
    resp = client.post(f"{BASE}/apartments", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# GET /apartments (list)
# ---------------------------------------------------------------------------

class TestListApartments:
    def test_empty_list(self, client: TestClient):
        resp = client.get(f"{BASE}/apartments")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_created(self, client: TestClient, admin_headers):
        _create_apartment(client, admin_headers)
        resp = client.get(f"{BASE}/apartments")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_city(self, client: TestClient, admin_headers):
        _create_apartment(client, admin_headers, {
            "title": "SF Place", "city": "San Francisco", "state": "CA", "zipcode": "94102",
        })
        _create_apartment(client, admin_headers, {
            "title": "Oakland Place", "city": "Oakland", "state": "CA", "zipcode": "94612",
        })
        resp = client.get(f"{BASE}/apartments?city=san+francisco")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["city"] == "San Francisco"

    def test_filter_by_zipcode(self, client: TestClient, admin_headers):
        _create_apartment(client, admin_headers, {
            "title": "A", "city": "Oakland", "state": "CA", "zipcode": "94612",
        })
        _create_apartment(client, admin_headers, {
            "title": "B", "city": "Oakland", "state": "CA", "zipcode": "94607",
        })
        resp = client.get(f"{BASE}/apartments?zipcode=94612")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["zipcode"] == "94612"

    def test_pagination(self, client: TestClient, admin_headers):
        for i in range(3):
            _create_apartment(client, admin_headers, {
                "title": f"Apt {i}", "city": "Oakland", "state": "CA", "zipcode": "94612",
            })
        resp = client.get(f"{BASE}/apartments?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp = client.get(f"{BASE}/apartments?skip=2&limit=10")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# POST /apartments
# ---------------------------------------------------------------------------

class TestCreateApartment:
    def test_create_requires_admin(self, client: TestClient, user_headers):
        resp = client.post(
            f"{BASE}/apartments",
            json={"title": "X", "city": "SF", "state": "CA", "zipcode": "94102"},
            headers=user_headers,
        )
        assert resp.status_code == 403

    def test_create_requires_auth(self, client: TestClient):
        resp = client.post(
            f"{BASE}/apartments",
            json={"title": "X", "city": "SF", "state": "CA", "zipcode": "94102"},
        )
        assert resp.status_code == 401

    def test_create_success(self, client: TestClient, admin_headers):
        payload = {
            "title": "New Apartments",
            "city": "Fremont",
            "state": "CA",
            "zipcode": "94538",
            "source_url": "https://example.com",
        }
        resp = client.post(f"{BASE}/apartments", json=payload, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "New Apartments"
        assert data["city"] == "Fremont"
        assert "id" in data

    def test_create_with_plans(self, client: TestClient, admin_headers, sample_apartment_payload):
        resp = client.post(
            f"{BASE}/apartments", json=sample_apartment_payload, headers=admin_headers
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["plans"]) == 1
        assert data["plans"][0]["name"] == "Studio A"
        assert data["plans"][0]["price"] == 2500.0

    def test_create_missing_required_fields(self, client: TestClient, admin_headers):
        resp = client.post(
            f"{BASE}/apartments",
            json={"title": "Incomplete"},
            headers=admin_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /apartments/{id}
# ---------------------------------------------------------------------------

class TestGetApartment:
    def test_get_existing(self, client: TestClient, admin_headers):
        created = _create_apartment(client, admin_headers)
        resp = client.get(f"{BASE}/apartments/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["id"] == created["id"]

    def test_get_not_found(self, client: TestClient):
        resp = client.get(f"{BASE}/apartments/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /apartments/{id}
# ---------------------------------------------------------------------------

class TestUpdateApartment:
    def test_update_success(self, client: TestClient, admin_headers):
        created = _create_apartment(client, admin_headers)
        resp = client.put(
            f"{BASE}/apartments/{created['id']}",
            json={"title": "Renamed"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Renamed"

    def test_update_requires_admin(self, client: TestClient, admin_headers, user_headers):
        created = _create_apartment(client, admin_headers)
        resp = client.put(
            f"{BASE}/apartments/{created['id']}",
            json={"title": "Hack"},
            headers=user_headers,
        )
        assert resp.status_code == 403

    def test_update_not_found(self, client: TestClient, admin_headers):
        resp = client.put(
            f"{BASE}/apartments/99999",
            json={"title": "Ghost"},
            headers=admin_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /apartments/{id}
# ---------------------------------------------------------------------------

class TestDeleteApartment:
    def test_delete_success(self, client: TestClient, admin_headers):
        created = _create_apartment(client, admin_headers)
        resp = client.delete(
            f"{BASE}/apartments/{created['id']}", headers=admin_headers
        )
        assert resp.status_code == 200
        # Confirm it's gone
        assert client.get(f"{BASE}/apartments/{created['id']}").status_code == 404

    def test_delete_requires_admin(self, client: TestClient, admin_headers, user_headers):
        created = _create_apartment(client, admin_headers)
        resp = client.delete(
            f"{BASE}/apartments/{created['id']}", headers=user_headers
        )
        assert resp.status_code == 403

    def test_delete_not_found(self, client: TestClient, admin_headers):
        resp = client.delete(f"{BASE}/apartments/99999", headers=admin_headers)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_by_title(self, client: TestClient, admin_headers):
        _create_apartment(client, admin_headers, {
            "title": "Sunset Tower", "city": "Oakland", "state": "CA", "zipcode": "94612",
        })
        _create_apartment(client, admin_headers, {
            "title": "Harbor View", "city": "Oakland", "state": "CA", "zipcode": "94612",
        })
        resp = client.get(f"{BASE}/search?query=sunset")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert "Sunset" in data[0]["title"]

    def test_search_no_results(self, client: TestClient):
        resp = client.get(f"{BASE}/search?query=nonexistentxyz")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_missing_query(self, client: TestClient):
        resp = client.get(f"{BASE}/search")
        assert resp.status_code == 422
