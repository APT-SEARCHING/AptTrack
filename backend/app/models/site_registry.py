"""Site compliance registry — tracks per-domain robots.txt status, ToS review,
and operational state for every domain AptTrack scrapes.

See ``backend/app/services/scraper_agent/compliance.py`` for the robots.txt
checker and the Cease & Desist response protocol.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.db.base_class import Base


class ScrapeSiteRegistry(Base):
    __tablename__ = "scrape_site_registry"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(
        String,
        unique=True,
        nullable=False,
        index=True,
        comment="e.g. 'www.rentmiro.com'",
    )

    # robots.txt status
    robots_txt_allows = Column(
        Boolean,
        nullable=True,
        comment="True if robots.txt allows our UA, None if no robots.txt found",
    )
    robots_txt_checked_at = Column(DateTime(timezone=True), nullable=True)
    robots_txt_raw = Column(
        Text,
        nullable=True,
        comment="Full robots.txt content stored for audit trail",
    )

    # ToS review (must be filled in manually)
    tos_url = Column(String, nullable=True, comment="URL of the site's Terms of Service")
    tos_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    tos_allows_scraping = Column(
        Boolean,
        nullable=True,
        comment="True=no prohibition found, False=explicitly banned, None=not yet reviewed",
    )
    tos_notes = Column(
        Text,
        nullable=True,
        comment="Human reviewer notes, e.g. 'Uses Yardi platform, no scraping clause found'",
    )

    # Underlying platform (many apartment sites embed third-party iframe widgets)
    platform = Column(
        String,
        nullable=True,
        comment="e.g. 'sightmap', 'entrata', 'yardi', 'appfolio', 'custom'",
    )

    # Operational status
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Set False if C&D received or robots.txt disallow added",
    )
    ceased_reason = Column(
        String,
        nullable=True,
        comment="e.g. 'C&D received 2026-05-01', 'robots.txt disallow added'",
    )

    # Audit timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
