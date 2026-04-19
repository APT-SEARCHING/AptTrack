"""Integration test — ScrapeRun model round-trip.

Confirms the schema is usable: write a row, query it back, verify every
field. Not testing any HTTP endpoint; uses the `db` fixture directly.
"""
from __future__ import annotations

from app.models.scrape_run import ScrapeRun


class TestScrapeRunModel:
    def test_write_and_read_success_row(self, db):
        run = ScrapeRun(
            apartment_id=None,
            url="https://www.rentmiro.com/floorplans",
            outcome="success",
            path_cache_hit=False,
            content_hash_short_circuit=False,
            iterations=12,
            llm_calls=12,
            input_tokens=45000,
            output_tokens=800,
            cost_usd=0.0221,
            elapsed_sec=38.4,
        )
        db.add(run)
        db.flush()

        fetched = db.get(ScrapeRun, run.id)
        assert fetched is not None
        assert fetched.outcome == "success"
        assert fetched.iterations == 12
        assert fetched.input_tokens == 45000
        assert fetched.output_tokens == 800
        assert abs(fetched.cost_usd - 0.0221) < 1e-5
        assert fetched.path_cache_hit is False
        assert fetched.content_hash_short_circuit is False
        assert fetched.error_message is None

    def test_write_and_read_content_unchanged_row(self, db):
        run = ScrapeRun(
            apartment_id=None,
            url="https://www.rentmiro.com/floorplans",
            outcome="content_unchanged",
            content_hash_short_circuit=True,
            elapsed_sec=0.8,
        )
        db.add(run)
        db.flush()

        fetched = db.get(ScrapeRun, run.id)
        assert fetched.outcome == "content_unchanged"
        assert fetched.content_hash_short_circuit is True
        assert fetched.cost_usd == 0.0
        assert fetched.iterations == 0

    def test_write_and_read_hard_fail_row(self, db):
        run = ScrapeRun(
            apartment_id=None,
            url="https://example.com/floorplans",
            outcome="hard_fail",
            elapsed_sec=5.1,
            error_message="TimeoutError: browser did not load within 30s",
        )
        db.add(run)
        db.flush()

        fetched = db.get(ScrapeRun, run.id)
        assert fetched.outcome == "hard_fail"
        assert "TimeoutError" in fetched.error_message

    def test_run_at_auto_populated(self, db):
        run = ScrapeRun(
            url="https://example.com/floorplans",
            outcome="cache_hit",
        )
        db.add(run)
        db.flush()

        fetched = db.get(ScrapeRun, run.id)
        assert fetched.run_at is not None

    def test_defaults_are_zero(self, db):
        run = ScrapeRun(url="https://example.com/floorplans", outcome="validated_fail")
        db.add(run)
        db.flush()

        fetched = db.get(ScrapeRun, run.id)
        assert fetched.iterations == 0
        assert fetched.llm_calls == 0
        assert fetched.input_tokens == 0
        assert fetched.output_tokens == 0
        assert fetched.cost_usd == 0.0
        assert fetched.elapsed_sec == 0.0
        assert fetched.path_cache_hit is False
        assert fetched.content_hash_short_circuit is False
