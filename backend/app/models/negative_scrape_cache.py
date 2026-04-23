"""NegativeScrapeCache — suppression table for URLs that consistently fail scraping.

When a scrape returns validated_fail or hard_fail, a row is upserted here with
an exponential backoff window.  _scrape_one checks this table at entry and skips
the apartment until retry_after passes, saving LLM spend on known-broken URLs.

Backoff schedule (attempt_count → days until retry):
  1st failure  →  7 days
  2nd failure  → 14 days
  3rd+ failure → 30 days (capped)

Admin actions:
  - View all suppressed URLs via GET /admin/negative-cache
  - Manually clear an entry (e.g. after adding a new adapter) via
    POST /admin/negative-cache/clear

notes column is for human annotations, e.g. "Shea POST-API — needs SheaAdapter".
"""
from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base_class import Base


class NegativeScrapeCache(Base):
    __tablename__ = "negative_scrape_cache"

    url = Column(String, primary_key=True, comment="Apartment's registered URL (original_url)")

    first_failed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When this URL first entered the cache",
    )
    last_failed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Most recent failure timestamp",
    )
    last_reason = Column(
        String(32),
        nullable=False,
        comment="ScrapeRun outcome that triggered this entry: validated_fail | hard_fail",
    )
    attempt_count = Column(
        Integer,
        default=1,
        nullable=False,
        comment="Cumulative failure count — drives exponential backoff",
    )
    retry_after = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="Don't scrape this URL again until after this timestamp",
    )
    notes = Column(
        Text,
        nullable=True,
        comment="Human-written annotation, e.g. 'needs SheaAdapter'",
    )

    __table_args__ = (
        Index("ix_negative_scrape_cache_retry_after", "retry_after", "attempt_count"),
    )
