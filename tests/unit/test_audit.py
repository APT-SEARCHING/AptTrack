"""Unit tests for dev/audit.py — new Phase-1 monitoring sections.

Tests cover:
  - q_hint_distribution runs cleanly on empty data (no exception, header present)
  - q_hint_distribution prints POLLUTED warning when universal_dom is a stored hint
  - q_rendered_latency runs cleanly on empty data
  - q_rendered_latency flags avg_s > 13 with a timeout-wait warning
  - q_outcome_24h runs cleanly on empty data
  - q_outcome_24h prints success ratio and per-row lines on real data

All tests mock db.execute() so no real DB or PostgreSQL-specific SQL is needed.
"""
from __future__ import annotations

import importlib.util
import sys
from collections import namedtuple
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))


# ---------------------------------------------------------------------------
# Module loader
# ---------------------------------------------------------------------------

def _load_module():
    """Load dev/audit.py without executing its top-level DB connection."""
    audit_path = ROOT / "dev" / "audit.py"
    assert audit_path.exists(), "dev/audit.py not found"
    spec = importlib.util.spec_from_file_location("audit", audit_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db(rows):
    """Return a MagicMock Session whose .execute().all() returns *rows*."""
    mock_result = MagicMock()
    mock_result.all.return_value = rows
    mock_result.fetchall.return_value = rows
    mock_result.one.return_value = MagicMock(
        total_plans=0, with_sqft=0, sqft_pct=None,
        clean_name=0, clean_name_pct=None,
        priced=0, with_url=0, with_floor=0,
    )
    mock_db = MagicMock()
    mock_db.execute.return_value = mock_result
    return mock_db


# ---------------------------------------------------------------------------
# q_hint_distribution
# ---------------------------------------------------------------------------

class TestHintDistribution:
    def test_empty_db_no_exception(self, capsys):
        """q_hint_distribution runs without error and prints section header."""
        module = _load_module()
        module.q_hint_distribution(_mock_db([]))
        out = capsys.readouterr().out
        assert "Registry Hint Distribution" in out

    def test_empty_db_no_pollution_message(self, capsys):
        """No rows → no POLLUTED warning."""
        module = _load_module()
        module.q_hint_distribution(_mock_db([]))
        out = capsys.readouterr().out
        assert "POLLUTED" not in out

    def test_detects_polluted_hint(self, capsys):
        """universal_dom stored as hint → POLLUTED warning appears."""
        module = _load_module()
        Row = namedtuple("Row", ["last_successful_adapter", "n", "last_success"])
        rows = [Row(last_successful_adapter="universal_dom", n=5, last_success="2026-04-20 02:00")]
        module.q_hint_distribution(_mock_db(rows))
        out = capsys.readouterr().out
        assert "POLLUTED" in out
        assert "universal_dom" in out
        assert "UPDATE scrape_site_registry" in out

    def test_clean_hints_no_warning(self, capsys):
        """Specific adapters → no POLLUTED warning."""
        module = _load_module()
        Row = namedtuple("Row", ["last_successful_adapter", "n", "last_success"])
        rows = [
            Row(last_successful_adapter="rentcafe", n=10, last_success="2026-04-23 02:00"),
            Row(last_successful_adapter="greystar", n=4, last_success="2026-04-22 02:00"),
        ]
        module.q_hint_distribution(_mock_db(rows))
        out = capsys.readouterr().out
        assert "POLLUTED" not in out
        assert "rentcafe" in out
        assert "greystar" in out

    def test_mixed_hints_flags_only_universal_dom(self, capsys):
        """Only universal_dom row gets the POLLUTED flag, others do not."""
        module = _load_module()
        Row = namedtuple("Row", ["last_successful_adapter", "n", "last_success"])
        rows = [
            Row(last_successful_adapter="sightmap", n=8, last_success="2026-04-23 02:00"),
            Row(last_successful_adapter="universal_dom", n=2, last_success="2026-04-21 02:00"),
        ]
        module.q_hint_distribution(_mock_db(rows))
        out = capsys.readouterr().out
        lines = out.splitlines()
        sightmap_line = next(l for l in lines if "sightmap" in l)
        universal_line = next(l for l in lines if "universal_dom" in l)
        assert "POLLUTED" not in sightmap_line
        assert "POLLUTED" in universal_line


# ---------------------------------------------------------------------------
# q_rendered_latency
# ---------------------------------------------------------------------------

class TestRenderedLatency:
    def test_empty_db_no_exception(self, capsys):
        """q_rendered_latency runs without error on empty data."""
        module = _load_module()
        module.q_rendered_latency(_mock_db([]))
        out = capsys.readouterr().out
        assert "Rendered Fetch Latency" in out

    def test_fast_rows_no_flag(self, capsys):
        """avg_s ≤ 13 → no timeout-wait warning."""
        module = _load_module()
        Row = namedtuple("Row", ["outcome", "adapter_name", "n", "avg_s", "p95_s"])
        rows = [Row(outcome="platform_direct_rendered", adapter_name="rentcafe", n=5, avg_s=8.2, p95_s=11.0)]
        module.q_rendered_latency(_mock_db(rows))
        out = capsys.readouterr().out
        assert "timeout" not in out.lower()
        assert "platform_direct_rendered" in out

    def test_slow_rows_flagged(self, capsys):
        """avg_s > 13 → timeout-wait warning printed."""
        module = _load_module()
        Row = namedtuple("Row", ["outcome", "adapter_name", "n", "avg_s", "p95_s"])
        rows = [Row(outcome="no_data", adapter_name=None, n=6, avg_s=14.1, p95_s=14.9)]
        module.q_rendered_latency(_mock_db(rows))
        out = capsys.readouterr().out
        assert "waiting for timeout" in out


# ---------------------------------------------------------------------------
# q_outcome_24h
# ---------------------------------------------------------------------------

class TestOutcome24h:
    def test_empty_db_no_exception(self, capsys):
        """q_outcome_24h runs without error on empty data."""
        module = _load_module()
        module.q_outcome_24h(_mock_db([]))
        out = capsys.readouterr().out
        assert "last 24h" in out

    def test_prints_total_and_success_ratio(self, capsys):
        """Total and success ratio line appear when rows present."""
        module = _load_module()
        Row = namedtuple("Row", ["outcome", "n", "pct", "avg_s", "avg_cost"])
        rows = [
            Row(outcome="platform_direct_static", n=15, pct=50.0, avg_s=0.8, avg_cost=0.0),
            Row(outcome="platform_direct_rendered", n=10, pct=33.3, avg_s=7.2, avg_cost=0.0),
            Row(outcome="no_data", n=5, pct=16.7, avg_s=13.5, avg_cost=0.0),
        ]
        module.q_outcome_24h(_mock_db(rows))
        out = capsys.readouterr().out
        assert "Total scrapes in last 24h: 30" in out
        assert "25/30" in out  # 15+10 successful out of 30
        assert "platform_direct_static" in out
        assert "no_data" in out
