"""ScrapeRun model — persists every scrape attempt for cost/quality observability.

Outcome values
--------------
``success``                  agent or path-cache replay returned ≥1 floor plan
``validated_fail``           scrape completed without error but returned 0 plans
``hard_fail``                exception raised during scrape
``content_unchanged``        content-hash short-circuit — prices carried forward
``cache_hit``                path-cache replay succeeded (subset of success)
``platform_direct``          platform adapter short-circuit (0 LLM cost)
``skipped_negative_cache``   URL is within its negative-cache suppression window
``skipped_unscrapeable``     registry.data_source_type == 'unscrapeable' — site doesn't publish pricing
``stale``                    reserved for future forced-retry logic
"""

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base_class import Base


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id = Column(Integer, primary_key=True, index=True)
    apartment_id = Column(
        Integer,
        ForeignKey("apartments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK to apartments — NULL if the apartment was deleted after this run",
    )
    run_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When this scrape attempt started",
    )
    url = Column(String, nullable=False, comment="Apartment's registered URL (original, pre-redirect)")
    effective_url = Column(
        String,
        nullable=True,
        comment="Actual URL scraped when a corporate_parent_url redirect fired; NULL if no redirect",
    )

    # Outcome
    outcome = Column(
        String(32),
        nullable=False,
        comment="success|validated_fail|hard_fail|content_unchanged|cache_hit|stale",
    )
    path_cache_hit = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="True when the path-cache replay was used",
    )
    content_hash_short_circuit = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="True when the content-hash check skipped the scrape entirely",
    )

    # LLM usage
    iterations = Column(Integer, default=0, nullable=False, comment="ReAct loop iterations")
    llm_calls = Column(Integer, default=0, nullable=False, comment="Number of LLM API calls made")
    input_tokens = Column(Integer, default=0, nullable=False)
    cached_input_tokens = Column(Integer, default=0, nullable=False, comment="Prompt-cached input tokens (MiniMax/DeepSeek)")
    output_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Float, default=0.0, nullable=False)
    elapsed_sec = Column(Float, default=0.0, nullable=False)

    # Error details
    error_message = Column(Text, nullable=True, comment="Exception message for hard_fail rows")

    __table_args__ = (
        # Fast per-apartment history lookup
        Index("ix_scrape_runs_apt_run_at", "apartment_id", "run_at"),
        # Fast aggregate queries by outcome
        Index("ix_scrape_runs_outcome_run_at", "outcome", "run_at"),
    )
