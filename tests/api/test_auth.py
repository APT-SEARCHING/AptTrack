from __future__ import annotations

"""Tests for /api/v1/auth endpoints."""

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/auth"


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------

class TestRegister:
    def test_register_success(self, client: TestClient):
        resp = client.post(f"{BASE}/register", json={
            "email": "new@example.com",
            "password": "securepass123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, client: TestClient):
        payload = {"email": "dup@example.com", "password": "securepass123"}
        client.post(f"{BASE}/register", json=payload)
        resp = client.post(f"{BASE}/register", json=payload)
        assert resp.status_code == 409
        assert "already registered" in resp.json()["detail"].lower()

    def test_register_short_password(self, client: TestClient):
        resp = client.post(f"{BASE}/register", json={
            "email": "short@example.com",
            "password": "abc",
        })
        assert resp.status_code == 422

    def test_register_invalid_email(self, client: TestClient):
        resp = client.post(f"{BASE}/register", json={
            "email": "not-an-email",
            "password": "securepass123",
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /login
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success(self, client: TestClient, regular_user):
        resp = client.post(
            f"{BASE}/login",
            data={"username": "user@test.example", "password": "userpass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client: TestClient, regular_user):
        resp = client.post(
            f"{BASE}/login",
            data={"username": "user@test.example", "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_login_unknown_email(self, client: TestClient):
        resp = client.post(
            f"{BASE}/login",
            data={"username": "ghost@example.com", "password": "anything123"},
        )
        assert resp.status_code == 401

    def test_login_inactive_account(self, client: TestClient, db, regular_user):
        regular_user.is_active = False
        db.flush()
        resp = client.post(
            f"{BASE}/login",
            data={"username": "user@test.example", "password": "userpass123"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /me
# ---------------------------------------------------------------------------

class TestMe:
    def test_me_authenticated(self, client: TestClient, user_headers, regular_user):
        resp = client.get(f"{BASE}/me", headers=user_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "user@test.example"
        assert data["is_active"] is True

    def test_me_no_token(self, client: TestClient):
        resp = client.get(f"{BASE}/me")
        assert resp.status_code == 401

    def test_me_bad_token(self, client: TestClient):
        resp = client.get(f"{BASE}/me", headers={"Authorization": "Bearer bad.token.here"})
        assert resp.status_code == 401
