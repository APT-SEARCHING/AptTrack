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


# ---------------------------------------------------------------------------
# POST /request-password-reset  +  POST /reset-password  (B5)
# ---------------------------------------------------------------------------

class TestPasswordReset:
    def test_request_known_email_returns_204(self, client: TestClient, regular_user, db):
        resp = client.post(f"{BASE}/request-password-reset", json={"email": "user@test.example"})
        assert resp.status_code == 204

    def test_request_known_email_writes_token_row(self, client: TestClient, regular_user, db):
        from app.models.password_reset_token import PasswordResetToken
        client.post(f"{BASE}/request-password-reset", json={"email": "user@test.example"})
        tokens = db.query(PasswordResetToken).filter_by(user_id=regular_user.id).all()
        assert len(tokens) == 1
        assert tokens[0].used_at is None
        assert tokens[0].token  # non-empty

    def test_request_unknown_email_returns_204_no_token(self, client: TestClient, db):
        from app.models.password_reset_token import PasswordResetToken
        resp = client.post(f"{BASE}/request-password-reset", json={"email": "ghost@nowhere.example"})
        assert resp.status_code == 204
        assert db.query(PasswordResetToken).count() == 0

    def test_reset_with_valid_token_changes_password(self, client: TestClient, regular_user, db):
        import secrets
        from datetime import datetime, timedelta, timezone
        from app.models.password_reset_token import PasswordResetToken
        from app.core.security import verify_password

        tok = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=regular_user.id,
            token=tok,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ))
        db.flush()

        resp = client.post(f"{BASE}/reset-password", json={"token": tok, "new_password": "newpassword99"})
        assert resp.status_code == 204

        db.refresh(regular_user)
        assert verify_password("newpassword99", regular_user.hashed_password)

    def test_reset_marks_token_used(self, client: TestClient, regular_user, db):
        import secrets
        from datetime import datetime, timedelta, timezone
        from app.models.password_reset_token import PasswordResetToken

        tok = secrets.token_urlsafe(32)
        prt = PasswordResetToken(
            user_id=regular_user.id,
            token=tok,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(prt)
        db.flush()

        client.post(f"{BASE}/reset-password", json={"token": tok, "new_password": "newpassword99"})
        db.refresh(prt)
        assert prt.used_at is not None

    def test_reset_expired_token_returns_400(self, client: TestClient, regular_user, db):
        import secrets
        from datetime import datetime, timedelta, timezone
        from app.models.password_reset_token import PasswordResetToken

        tok = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=regular_user.id,
            token=tok,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # already expired
        ))
        db.flush()

        resp = client.post(f"{BASE}/reset-password", json={"token": tok, "new_password": "newpassword99"})
        assert resp.status_code == 400

    def test_reset_already_used_token_returns_400(self, client: TestClient, regular_user, db):
        import secrets
        from datetime import datetime, timedelta, timezone
        from app.models.password_reset_token import PasswordResetToken

        tok = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=regular_user.id,
            token=tok,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            used_at=datetime.now(timezone.utc),  # already consumed
        ))
        db.flush()

        resp = client.post(f"{BASE}/reset-password", json={"token": tok, "new_password": "newpassword99"})
        assert resp.status_code == 400

    def test_reset_nonexistent_token_returns_400(self, client: TestClient):
        resp = client.post(f"{BASE}/reset-password", json={"token": "does-not-exist", "new_password": "newpassword99"})
        assert resp.status_code == 400
