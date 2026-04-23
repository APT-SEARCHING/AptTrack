"""API tests for GET /admin/negative-cache and POST /admin/negative-cache/clear."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.negative_scrape_cache import NegativeScrapeCache

URL_A = "https://www.site-a.com/floorplans"
URL_B = "https://www.site-b.com/"


def _future(days=7):
    return datetime.now(timezone.utc) + timedelta(days=days)


def _past(days=1):
    return datetime.now(timezone.utc) - timedelta(days=days)


def _add_entry(db, url, reason="validated_fail", attempt_count=1, future=True):
    db.add(NegativeScrapeCache(
        url=url,
        last_reason=reason,
        attempt_count=attempt_count,
        retry_after=_future() if future else _past(),
    ))
    db.flush()


class TestListNegativeCache:
    def test_requires_admin(self, client, user_headers):
        r = client.get("/api/v1/admin/negative-cache", headers=user_headers)
        assert r.status_code == 403

    def test_requires_auth(self, client):
        r = client.get("/api/v1/admin/negative-cache")
        assert r.status_code == 401

    def test_empty_list(self, client, admin_headers):
        r = client.get("/api/v1/admin/negative-cache", headers=admin_headers)
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_entries(self, client, db, admin_headers):
        _add_entry(db, URL_A, reason="validated_fail", attempt_count=1)
        _add_entry(db, URL_B, reason="hard_fail", attempt_count=3)
        r = client.get("/api/v1/admin/negative-cache", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2
        urls = {e["url"] for e in data}
        assert urls == {URL_A, URL_B}

    def test_response_shape(self, client, db, admin_headers):
        _add_entry(db, URL_A, reason="hard_fail", attempt_count=2)
        r = client.get("/api/v1/admin/negative-cache", headers=admin_headers)
        entry = r.json()[0]
        assert entry["url"] == URL_A
        assert entry["last_reason"] == "hard_fail"
        assert entry["attempt_count"] == 2
        assert "retry_after" in entry
        assert "first_failed_at" in entry
        assert "last_failed_at" in entry

    def test_ordered_by_last_failed_desc(self, client, db, admin_headers):
        # Insert A first, then B — B should appear first (more recent flush)
        _add_entry(db, URL_A)
        _add_entry(db, URL_B)
        # Force URL_A to have an older last_failed_at
        db.execute(
            NegativeScrapeCache.__table__.update()
            .where(NegativeScrapeCache.url == URL_A)
            .values(last_failed_at=_past(days=2))
        )
        db.flush()
        r = client.get("/api/v1/admin/negative-cache", headers=admin_headers)
        data = r.json()
        assert data[0]["url"] == URL_B


class TestClearNegativeCache:
    def test_requires_admin(self, client, user_headers):
        r = client.post(
            "/api/v1/admin/negative-cache/clear",
            json={"url": URL_A},
            headers=user_headers,
        )
        assert r.status_code == 403

    def test_requires_auth(self, client):
        r = client.post("/api/v1/admin/negative-cache/clear", json={"url": URL_A})
        assert r.status_code == 401

    def test_404_when_not_found(self, client, admin_headers):
        r = client.post(
            "/api/v1/admin/negative-cache/clear",
            json={"url": "https://nothere.com/"},
            headers=admin_headers,
        )
        assert r.status_code == 404

    def test_clears_entry(self, client, db, admin_headers):
        _add_entry(db, URL_A)
        r = client.post(
            "/api/v1/admin/negative-cache/clear",
            json={"url": URL_A},
            headers=admin_headers,
        )
        assert r.status_code == 200
        assert r.json()["cleared"] == URL_A
        # Verify gone
        r2 = client.get("/api/v1/admin/negative-cache", headers=admin_headers)
        assert r2.json() == []

    def test_clear_only_removes_target(self, client, db, admin_headers):
        _add_entry(db, URL_A)
        _add_entry(db, URL_B)
        client.post(
            "/api/v1/admin/negative-cache/clear",
            json={"url": URL_A},
            headers=admin_headers,
        )
        r = client.get("/api/v1/admin/negative-cache", headers=admin_headers)
        remaining = [e["url"] for e in r.json()]
        assert URL_B in remaining
        assert URL_A not in remaining
