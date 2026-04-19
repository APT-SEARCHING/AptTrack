"""ApiCostLog — persistent record of every API spend event.

Replaces the ephemeral ``logs/cost_log.jsonl`` file (wiped on Railway redeploy).
One row per scraper run or Google Maps import call.

Source values
-------------
``scraper``      — one apartment scraped via the agentic scraper
``google_maps``  — one city/location fetched from Google Maps Places API
"""

from sqlalchemy import Column, DateTime, Index, Integer, Numeric, String
from sqlalchemy.sql import func

from app.db.base_class import Base


class ApiCostLog(Base):
    __tablename__ = "api_cost_log"

    id = Column(Integer, primary_key=True)  # Integer sufficient (~2B rows); BigInteger breaks SQLite tests
    ts = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    source = Column(String(32), nullable=False, comment="'scraper' | 'google_maps'")
    name = Column(String, nullable=True, comment="apartment title or city searched")
    url = Column(String, nullable=True, comment="scraper: source URL; google_maps: null")
    outcome = Column(String(32), nullable=False, comment="ok | no_data | error | cache_hit | partial")

    # Scraper token counts (null for google_maps rows)
    input_tok = Column(Integer, default=0, nullable=False)
    output_tok = Column(Integer, default=0, nullable=False)

    # Google Maps call counts (0 for scraper rows)
    api_calls = Column(Integer, default=0, nullable=False)
    cache_hits = Column(Integer, default=0, nullable=False)

    cost_usd = Column(Numeric(10, 6), default=0, nullable=False)

    __table_args__ = (
        Index("idx_api_cost_log_source_ts", "source", "ts"),
    )
