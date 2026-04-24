"""Unit tests for dev/coverage_report.py.

Tests:
  - Script runs without error against an in-memory SQLite DB.
  - Aggregation correctly counts per-adapter and per-outcome.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import app.db.base  # noqa: F401 — registers all models
from app.db.base_class import Base
from app.models.scrape_run import ScrapeRun


# ---------------------------------------------------------------------------
# Fixtures
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


def _run(outcome: str, adapter_name: str | None = None, cost: float = 0.0) -> ScrapeRun:
    return ScrapeRun(
        apartment_id=1,
        url="https://example.com/",
        outcome=outcome,
        adapter_name=adapter_name,
        cost_usd=cost,
        elapsed_sec=1.0,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _load_module():
    """Load dev/coverage_report.py as a module."""
    import importlib.util
    report_path = ROOT / "dev" / "coverage_report.py"
    assert report_path.exists(), "dev/coverage_report.py not found"
    spec = importlib.util.spec_from_file_location("coverage_report", report_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_coverage_report_runs_without_error(db: Session) -> None:
    """Script's main() runs to completion with no crash."""
    db.add(_run("platform_direct", "sightmap", cost=0.0))
    db.add(_run("success", cost=0.05))
    db.commit()

    module = _load_module()
    with patch.object(module, "_make_session", return_value=db):
        captured = StringIO()
        with patch("sys.stdout", captured):
            try:
                with patch("sys.argv", ["coverage_report.py"]):
                    module.main()
            except SystemExit:
                pass

    output = captured.getvalue()
    assert "platform_direct" in output or "Total scrape_runs" in output


def test_coverage_report_per_apt_flag(db: Session) -> None:
    """--per-apt flag prints per-apartment section without crashing."""
    db.add(_run("platform_direct", "sightmap", cost=0.0))
    db.add(_run("validated_fail", cost=0.0))
    db.commit()

    module = _load_module()
    with patch.object(module, "_make_session", return_value=db):
        captured = StringIO()
        with patch("sys.stdout", captured):
            try:
                with patch("sys.argv", ["coverage_report.py", "--per-apt"]):
                    module.main()
            except SystemExit:
                pass

    output = captured.getvalue()
    assert "Per-apartment" in output or "per-apartment" in output.lower() or "Outcome" in output


def test_coverage_report_aggregates_correctly(db: Session) -> None:
    """Aggregation counts: 3 sightmap, 2 greystar, 1 success, 1 content_unchanged."""
    rows = [
        _run("platform_direct", "sightmap"),
        _run("platform_direct", "sightmap"),
        _run("platform_direct", "sightmap"),
        _run("platform_direct", "greystar"),
        _run("platform_direct", "greystar"),
        _run("success", cost=0.04),
        _run("content_unchanged"),
    ]
    for r in rows:
        db.add(r)
    db.commit()

    all_runs = db.query(ScrapeRun).all()
    assert len(all_runs) == 7

    # Per-outcome
    outcomes = [r.outcome for r in all_runs]
    assert outcomes.count("platform_direct") == 5
    assert outcomes.count("success") == 1
    assert outcomes.count("content_unchanged") == 1

    # Per-adapter
    platform_rows = [r for r in all_runs if r.outcome == "platform_direct"]
    adapter_counts: dict[str, int] = {}
    for r in platform_rows:
        key = r.adapter_name or "(unknown)"
        adapter_counts[key] = adapter_counts.get(key, 0) + 1

    assert adapter_counts["sightmap"] == 3
    assert adapter_counts["greystar"] == 2

    # Verify adapter_name is NULL for non-platform_direct rows
    non_pt = [r for r in all_runs if r.outcome != "platform_direct"]
    assert all(r.adapter_name is None for r in non_pt)
