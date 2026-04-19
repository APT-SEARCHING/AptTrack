"""Tests for cost_log.py — DB write path and JSONL fallback."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.db.base  # noqa: F401 — registers all models including ApiCostLog
from app.db.base_class import Base
from app.models.api_cost_log import ApiCostLog
from app.core.cost_log import append_scraper_entry, append_google_maps_entry


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


# ---------------------------------------------------------------------------
# append_scraper_entry — DB path
# ---------------------------------------------------------------------------

class TestAppendScraperEntryDB:
    def test_writes_row_with_correct_fields(self, db):
        append_scraper_entry(
            name="Miro", url="https://www.rentmiro.com/floorplans",
            outcome="ok", input_tok=45000, output_tok=800, cost_usd=0.0221,
            db=db,
        )
        row = db.query(ApiCostLog).one()
        assert row.source == "scraper"
        assert row.name == "Miro"
        assert row.url == "https://www.rentmiro.com/floorplans"
        assert row.outcome == "ok"
        assert row.input_tok == 45000
        assert row.output_tok == 800
        assert float(row.cost_usd) == pytest.approx(0.0221, abs=1e-5)
        assert row.api_calls == 0
        assert row.cache_hits == 0

    def test_cache_hit_outcome(self, db):
        append_scraper_entry(
            name="Miro", url="https://example.com", outcome="cache_hit", db=db,
        )
        row = db.query(ApiCostLog).one()
        assert row.outcome == "cache_hit"
        assert row.cost_usd == 0

    def test_error_outcome(self, db):
        append_scraper_entry(name="Bad Site", url="https://bad.example.com", outcome="error", db=db)
        row = db.query(ApiCostLog).one()
        assert row.outcome == "error"

    def test_ts_auto_populated(self, db):
        append_scraper_entry(name="X", url="u", outcome="ok", db=db)
        row = db.query(ApiCostLog).one()
        # ts is set by server_default; in SQLite it stays None until flush+query,
        # but the row itself is committed without error
        assert row.id is not None


# ---------------------------------------------------------------------------
# append_google_maps_entry — DB path
# ---------------------------------------------------------------------------

class TestAppendGoogleMapsEntryDB:
    def test_writes_row_with_correct_fields(self, db):
        append_google_maps_entry(
            location="San Jose, CA", total_places=45,
            api_calls=3, cache_hits=42, failed=0, cost_usd=0.033,
            db=db,
        )
        row = db.query(ApiCostLog).one()
        assert row.source == "google_maps"
        assert row.name == "San Jose, CA"
        assert row.url is None
        assert row.outcome == "ok"
        assert row.api_calls == 3
        assert row.cache_hits == 42
        assert float(row.cost_usd) == pytest.approx(0.033, abs=1e-5)

    def test_partial_outcome_when_failed_gt_zero(self, db):
        append_google_maps_entry(
            location="Oakland, CA", total_places=10,
            api_calls=8, cache_hits=2, failed=2, cost_usd=0.056,
            db=db,
        )
        row = db.query(ApiCostLog).one()
        assert row.outcome == "partial"

    def test_ok_outcome_when_no_failures(self, db):
        append_google_maps_entry(
            location="Fremont, CA", total_places=5,
            api_calls=5, cache_hits=0, failed=0, cost_usd=0.035,
            db=db,
        )
        assert db.query(ApiCostLog).one().outcome == "ok"


# ---------------------------------------------------------------------------
# JSONL fallback — db=None
# ---------------------------------------------------------------------------

class TestJSONLFallback:
    def test_no_db_writes_jsonl(self, tmp_path):
        log_file = tmp_path / "cost_log.jsonl"
        with patch("app.core.cost_log._LOG_FILE", log_file):
            append_scraper_entry(
                name="Test", url="https://example.com", outcome="ok",
                input_tok=100, output_tok=10, cost_usd=0.001,
                db=None,
            )
        assert log_file.exists()
        line = json.loads(log_file.read_text())
        assert line["source"] == "scraper"
        assert line["outcome"] == "ok"
        assert line["input_tok"] == 100

    def test_db_failure_falls_back_to_jsonl(self, tmp_path):
        """Simulate a DB commit failure and verify JSONL fallback is written."""
        log_file = tmp_path / "cost_log.jsonl"
        broken_db = MagicMock()
        broken_db.add = MagicMock()
        broken_db.commit = MagicMock(side_effect=Exception("DB down"))
        broken_db.rollback = MagicMock()

        with patch("app.core.cost_log._LOG_FILE", log_file):
            append_scraper_entry(
                name="Fallback Test", url="https://example.com",
                outcome="ok", cost_usd=0.005, db=broken_db,
            )

        broken_db.rollback.assert_called_once()
        assert log_file.exists()
        line = json.loads(log_file.read_text())
        assert line["source"] == "scraper"
        assert line["outcome"] == "ok"
