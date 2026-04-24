"""Tests for include_unscrapeable filter on GET /apartments."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.models.apartment import Apartment

BASE = "/api/v1"


def _make_apt(db, title: str, data_source_type: str = "brand_site") -> Apartment:
    apt = Apartment(
        title=title,
        city="San Jose",
        state="CA",
        zipcode="95101",
        source_url=f"https://example.com/{title.lower().replace(' ', '-')}",
        is_available=True,
        data_source_type=data_source_type,
    )
    db.add(apt)
    db.flush()
    return apt


class TestIncludeUnscrapeableFilter:
    def test_unscrapeable_hidden_by_default(self, client: TestClient, db):
        _make_apt(db, "Normal Place", "brand_site")
        _make_apt(db, "Cloudflare Wall", "unscrapeable")
        db.commit()

        resp = client.get(f"{BASE}/apartments")
        assert resp.status_code == 200
        titles = [a["title"] for a in resp.json()]
        assert "Normal Place" in titles
        assert "Cloudflare Wall" not in titles

    def test_unscrapeable_shown_when_opted_in(self, client: TestClient, db):
        _make_apt(db, "Normal Place", "brand_site")
        _make_apt(db, "Cloudflare Wall", "unscrapeable")
        db.commit()

        resp = client.get(f"{BASE}/apartments?include_unscrapeable=true")
        assert resp.status_code == 200
        titles = [a["title"] for a in resp.json()]
        assert "Normal Place" in titles
        assert "Cloudflare Wall" in titles

    def test_null_data_source_type_always_shown(self, client: TestClient, db):
        """Legacy apartments with data_source_type=NULL are never hidden."""
        apt = Apartment(
            title="Legacy Apt",
            city="San Jose",
            state="CA",
            zipcode="95101",
            source_url="https://legacyapt.com/floorplans",
            is_available=True,
        )
        apt.data_source_type = None
        db.add(apt)
        db.commit()

        resp = client.get(f"{BASE}/apartments")
        assert resp.status_code == 200
        titles = [a["title"] for a in resp.json()]
        assert "Legacy Apt" in titles
