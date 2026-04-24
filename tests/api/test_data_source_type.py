"""Tests for data_source_type on ScrapeSiteRegistry and Apartment.

Verifies:
  - Default value is 'brand_site' for both models.
  - Round-trip write/read for 'unscrapeable'.
  - API response for apartments includes data_source_type.
"""
from __future__ import annotations

from app.models.apartment import Apartment
from app.models.site_registry import ScrapeSiteRegistry


class TestDataSourceTypeDefault:
    def test_registry_default(self, db):
        reg = ScrapeSiteRegistry(
            domain="testdefault.com",
            is_active=True,
        )
        db.add(reg)
        db.flush()
        db.refresh(reg)
        assert reg.data_source_type == "brand_site"

    def test_apartment_default(self, db):
        apt = Apartment(
            title="Test",
            city="Oakland",
            state="CA",
            zipcode="94601",
            source_url="https://testdefault.com/floorplans",
            is_available=True,
        )
        db.add(apt)
        db.flush()
        db.refresh(apt)
        assert apt.data_source_type == "brand_site"


class TestDataSourceTypeUnscrapeable:
    def test_registry_roundtrip(self, db):
        reg = ScrapeSiteRegistry(
            domain="parkmerced.com",
            is_active=True,
            data_source_type="unscrapeable",
        )
        db.add(reg)
        db.flush()
        fetched = db.get(ScrapeSiteRegistry, reg.id)
        assert fetched.data_source_type == "unscrapeable"

    def test_apartment_roundtrip(self, db):
        apt = Apartment(
            title="Parkmerced",
            city="San Francisco",
            state="CA",
            zipcode="94132",
            source_url="https://www.parkmerced.com/floor-plans/",
            is_available=True,
            data_source_type="unscrapeable",
        )
        db.add(apt)
        db.flush()
        fetched = db.get(Apartment, apt.id)
        assert fetched.data_source_type == "unscrapeable"


class TestDataSourceTypeInAPIResponse:
    def test_apartment_list_includes_data_source_type(self, client, db):
        """GET /apartments returns data_source_type on each apartment."""
        apt = Apartment(
            title="Parkmerced SF",
            city="San Francisco",
            state="CA",
            zipcode="94132",
            source_url="https://www.parkmerced.com/floor-plans/",
            is_available=True,
            data_source_type="unscrapeable",
        )
        db.add(apt)
        db.commit()

        resp = client.get("/api/v1/apartments/")
        assert resp.status_code == 200
        data = resp.json()
        apartments = data if isinstance(data, list) else data.get("items", data.get("apartments", []))
        parkmerced = next((a for a in apartments if "Parkmerced" in a.get("title", "")), None)
        assert parkmerced is not None, "Parkmerced not found in response"
        assert parkmerced.get("data_source_type") == "unscrapeable"
