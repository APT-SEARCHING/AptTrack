#!/usr/bin/env python
"""One-time script: populate scrape_site_registry for all known target domains.

Checks robots.txt for each apartment domain, inserts/updates registry rows,
and pre-fills known platform and ToS notes.  Leaves tos_reviewed_at as NULL —
a human must review each site's ToS and fill in tos_allows_scraping manually.

Usage (from repo root):
    python scripts/populate_site_registry.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Make backend importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import select

from app.db.base import *  # noqa: F401,F403 — registers all models
from app.db.session import SessionLocal
from app.models.site_registry import ScrapeSiteRegistry
from app.services.scraper_agent.compliance import check_robots_txt

# ---------------------------------------------------------------------------
# Known targets with pre-filled metadata (update as targets change)
# ---------------------------------------------------------------------------

KNOWN_SITES = [
    {
        "url": "https://www.rentmiro.com/floorplans",
        "platform": "sightmap",
        "tos_notes": "Public pricing page, no login required. Uses SightMap iframe widget. No explicit scraping prohibition observed.",
    },
    {
        "url": "https://www.theryden.com/floorplans",
        "platform": "sightmap",
        "tos_notes": "Public pricing page, no login required. Uses SightMap iframe widget.",
    },
    {
        "url": "https://astellaapts.com/floor-plans/",
        "platform": "custom",
        "tos_notes": "Custom site, public floor plans page, no login required.",
    },
    {
        "url": "https://duboce.com/floorplans/",
        "platform": "custom",
        "tos_notes": "Custom site, public floor plans page, no login required.",
    },
    {
        "url": "https://www.atlasoakland.com/floorplans",
        "platform": "sightmap",
        "tos_notes": "Public pricing page, no login required. Uses SightMap iframe widget.",
    },
    {
        "url": "https://orionoakland.com/floorplans/",
        "platform": "custom",
        "tos_notes": "Custom site, public floor plans page, no login required.",
    },
    {
        "url": "https://thetolmanapts.com/floorplans/",
        "platform": "custom",
        "tos_notes": "Custom site, public floor plans page, no login required.",
    },
    {
        "url": "https://www.theasherfremont.com/floorplans",
        "platform": "sightmap",
        "tos_notes": "Public pricing page, no login required. Uses SightMap iframe widget.",
    },
    {
        "url": "https://www.themarc-pa.com/apartments/ca/palo-alto/floor-plans",
        "platform": "custom",
        "tos_notes": "Custom site, public floor plans page, no login required.",
    },
    {
        "url": "https://legacyhayward.com/floorplans/",
        "platform": "custom",
        "tos_notes": "Custom site, public floor plans page, no login required.",
    },
]


async def main() -> None:
    db = SessionLocal()
    try:
        print(f"Checking {len(KNOWN_SITES)} target domains...\n")
        for site in KNOWN_SITES:
            url = site["url"]
            domain = urlparse(url).netloc.lower()

            print(f"  {domain}  ", end="", flush=True)
            robots = await check_robots_txt(url)

            row = db.execute(
                select(ScrapeSiteRegistry).where(ScrapeSiteRegistry.domain == domain)
            ).scalar_one_or_none()
            if row is None:
                row = ScrapeSiteRegistry(domain=domain)
                db.add(row)

            row.robots_txt_allows = robots["allowed"]
            row.robots_txt_checked_at = robots["checked_at"]
            row.robots_txt_raw = robots["raw"]
            row.platform = site["platform"]
            row.tos_notes = site["tos_notes"]
            # tos_reviewed_at intentionally left NULL — requires human review
            row.is_active = True

            status = "✓ allowed" if robots["allowed"] else "✗ BLOCKED by robots.txt"
            print(status)

        db.commit()
        print(
            "\nRegistry populated. "
            "Set tos_reviewed_at + tos_allows_scraping manually after reviewing each site's ToS."
        )

        # Also seed any other domains present in Apartment.source_url not already covered
        from app.models.apartment import Apartment

        rows = db.execute(
            select(Apartment.source_url)
            .where(Apartment.source_url.isnot(None))
            .distinct()
        ).all()
        new_domains = 0
        for (apt_url,) in rows:
            d = urlparse(apt_url).netloc.lower()
            if not db.execute(
                select(ScrapeSiteRegistry).where(ScrapeSiteRegistry.domain == d)
            ).scalar_one_or_none():
                robots = await check_robots_txt(apt_url)
                db.add(ScrapeSiteRegistry(
                    domain=d,
                    robots_txt_allows=robots["allowed"],
                    robots_txt_checked_at=robots["checked_at"],
                    robots_txt_raw=robots["raw"],
                    is_active=True,
                ))
                new_domains += 1
        if new_domains:
            db.commit()
            print(f"Added {new_domains} additional domain(s) from Apartment.source_url.")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
