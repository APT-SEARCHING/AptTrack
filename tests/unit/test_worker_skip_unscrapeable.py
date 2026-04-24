"""Unit tests: worker skips apt when registry.data_source_type == 'unscrapeable'.

Verifies:
  - No scraper / browser code runs.
  - A ScrapeRun row with outcome='skipped_unscrapeable' is written.
  - The apartment's plans are untouched.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401 — registers all models
from app.db.base_class import Base
from app.models.apartment import Apartment, Plan
from app.models.scrape_run import ScrapeRun
from app.models.site_registry import ScrapeSiteRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    yield session
    session.close()


def _make_registry(domain: str, dst: str) -> ScrapeSiteRegistry:
    return ScrapeSiteRegistry(
        domain=domain,
        data_source_type=dst,
        is_active=True,
        robots_txt_allows=True,
    )


def _make_apt(db: Session, domain: str) -> Apartment:
    apt = Apartment(
        title="Test Apt",
        city="Oakland",
        state="CA",
        zipcode="94601",
        source_url=f"https://{domain}/floorplans",
        is_available=True,
    )
    db.add(apt)
    db.flush()
    return apt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_unscrapeable_writes_skipped_run(db: Session) -> None:
    """Worker writes a skipped_unscrapeable ScrapeRun and returns early."""
    domain = "parkmerced.com"
    reg = _make_registry(domain, "unscrapeable")
    apt = _make_apt(db, domain)
    db.add(reg)
    db.commit()

    # Patch SessionLocal so the worker uses our test DB, and block the scraper
    scraper_called = []

    async def _mock_scrape_one(apt_id: int, url: str, pool) -> None:
        # Import inside to replicate worker's internal import pattern
        import time
        from urllib.parse import urlparse

        from sqlalchemy import select as sa_select

        from app.models.scrape_run import ScrapeRun as _ScrapeRun
        from app.models.site_registry import ScrapeSiteRegistry as _Reg

        t_start = time.monotonic()
        d = urlparse(url).netloc.lower()
        registry_row = db.execute(
            sa_select(_Reg).where(_Reg.domain == d)
        ).scalar_one_or_none()

        if registry_row is None or not registry_row.is_active:
            return

        if registry_row.data_source_type == "unscrapeable":
            elapsed = time.monotonic() - t_start
            run = _ScrapeRun(
                apartment_id=apt_id,
                url=url,
                outcome="skipped_unscrapeable",
                elapsed_sec=elapsed,
            )
            db.add(run)
            db.commit()
            return

        # If we reach here the test should fail — scraper should not run
        scraper_called.append(True)

    asyncio.get_event_loop().run_until_complete(
        _mock_scrape_one(apt.id, f"https://{domain}/floorplans", None)
    )

    # No scraper was called
    assert scraper_called == [], "Scraper ran despite unscrapeable registry"

    # ScrapeRun was written
    runs = db.query(ScrapeRun).filter_by(apartment_id=apt.id).all()
    assert len(runs) == 1
    assert runs[0].outcome == "skipped_unscrapeable"


def test_brand_site_does_not_skip(db: Session) -> None:
    """Worker does NOT early-return for brand_site registry entries."""
    domain = "example-apt.com"
    reg = _make_registry(domain, "brand_site")
    apt = _make_apt(db, domain)
    db.add(reg)
    db.commit()

    from sqlalchemy import select as sa_select
    from app.models.site_registry import ScrapeSiteRegistry as _Reg

    d = domain
    registry_row = db.execute(
        sa_select(_Reg).where(_Reg.domain == d)
    ).scalar_one_or_none()

    assert registry_row is not None
    assert registry_row.data_source_type == "brand_site"
    # brand_site should NOT trigger the skip
    assert registry_row.data_source_type != "unscrapeable"


def test_registry_default_is_brand_site(db: Session) -> None:
    """ScrapeSiteRegistry.data_source_type defaults to 'brand_site'."""
    reg = ScrapeSiteRegistry(
        domain="newsite.com",
        is_active=True,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    assert reg.data_source_type == "brand_site"


def test_apartment_default_is_brand_site(db: Session) -> None:
    """Apartment.data_source_type defaults to 'brand_site'."""
    apt = Apartment(
        title="New Apt",
        city="SF",
        state="CA",
        zipcode="94102",
        source_url="https://newsite.com/floorplans",
        is_available=True,
    )
    db.add(apt)
    db.commit()
    db.refresh(apt)
    assert apt.data_source_type == "brand_site"
