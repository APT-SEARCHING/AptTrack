#!/usr/bin/env python3
"""Seed scrape_site_registry for any apartment whose domain isn't registered yet.

Safe to run multiple times — skips domains already in the table.

Usage:
    python dev/seed_registry.py              # seed all active apartment domains
    python dev/seed_registry.py --dry-run    # show what would be inserted
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.apartment import Apartment
from app.models.site_registry import ScrapeSiteRegistry


def _make_session() -> Session:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return Session(engine)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed scrape_site_registry from apartment URLs")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted")
    args = parser.parse_args()

    db = _make_session()
    try:
        apts = db.execute(
            select(Apartment).where(Apartment.source_url.isnot(None))
        ).scalars().all()

        existing = {
            r.domain
            for r in db.execute(select(ScrapeSiteRegistry)).scalars().all()
        }

        to_add: list[str] = []
        seen: set[str] = set()
        for apt in apts:
            domain = urlparse(apt.source_url).netloc.lower()
            if not domain or domain in existing or domain in seen:
                continue
            seen.add(domain)
            to_add.append(domain)

        if not to_add:
            print("All domains already in registry.")
            return

        print(f"{'Domain':<50}  action")
        print("-" * 60)
        for domain in sorted(to_add):
            print(f"  {domain:<48}  INSERT")

        if args.dry_run:
            print(f"\n--dry-run: {len(to_add)} domain(s) would be inserted.")
            return

        inserted = 0
        for domain in to_add:
            reg = ScrapeSiteRegistry(
                domain=domain,
                is_active=True,
                robots_txt_allows=None,   # not yet checked
                tos_allows_scraping=None, # not yet reviewed
                data_source_type="brand_site",
            )
            db.add(reg)
            inserted += 1

        db.commit()
        print(f"\nInserted {inserted} domain(s) into scrape_site_registry.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
