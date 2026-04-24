#!/usr/bin/env python3
"""Run the scrape pipeline directly against a set of apartments.

Calls task_refresh_apartment_chunk.apply() — synchronous, no Celery broker
needed.  Writes ScrapeRun rows to the live DB, so coverage_report.py picks
them up immediately after.

Usage:
    # Scrape the 20 most recently added apartments
    python dev/run_scrape.py --last 20

    # Scrape specific IDs
    python dev/run_scrape.py --ids 153 154 155

    # Scrape all active apartments
    python dev/run_scrape.py --all

    # Dry-run: print which apartments would be scraped, don't scrape
    python dev/run_scrape.py --last 20 --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.apartment import Apartment


def _make_session() -> Session:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return Session(engine)


def _get_apt_ids(db: Session, mode: str, last_n: int | None, ids: list[int]) -> list[tuple[int, str, str]]:
    """Return [(id, title, source_url)] for the requested apartments."""
    q = (
        select(Apartment.id, Apartment.title, Apartment.source_url)
        .where(Apartment.is_available.is_(True), Apartment.source_url.isnot(None))
    )
    if mode == "ids":
        q = q.where(Apartment.id.in_(ids))
    elif mode == "last":
        q = q.order_by(Apartment.id.desc()).limit(last_n)
    # mode == "all" → no extra filter

    rows = db.execute(q).all()
    # For "last", reverse to ascending order so logs read chronologically
    if mode == "last":
        rows = list(reversed(rows))
    return [(r.id, r.title, r.source_url) for r in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run scrape pipeline against selected apartments")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--last", type=int, metavar="N", help="Scrape last N apartments (by id desc)")
    group.add_argument("--ids", type=int, nargs="+", metavar="ID", help="Scrape specific apartment IDs")
    group.add_argument("--all", action="store_true", help="Scrape all active apartments")
    parser.add_argument("--dry-run", action="store_true", help="Print apartments that would be scraped; don't scrape")
    args = parser.parse_args()

    db = _make_session()
    try:
        if args.last:
            apt_rows = _get_apt_ids(db, "last", args.last, [])
        elif args.ids:
            apt_rows = _get_apt_ids(db, "ids", None, args.ids)
        else:
            apt_rows = _get_apt_ids(db, "all", None, [])
    finally:
        db.close()

    if not apt_rows:
        print("No matching apartments found.")
        sys.exit(0)

    print(f"{'Apt ID':>6}  {'Title':<40}  URL")
    print("-" * 100)
    for apt_id, title, url in apt_rows:
        print(f"{apt_id:>6}  {title[:40]:<40}  {url}")
    print(f"\n{len(apt_rows)} apartment(s) selected.")

    if args.dry_run:
        print("\n--dry-run: exiting without scraping.")
        return

    print(f"\nStarting scrape at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} …\n")

    # Import inside to defer heavy Playwright/SQLAlchemy setup until confirmed
    from app.worker import task_refresh_apartment_chunk

    apt_ids = [r[0] for r in apt_rows]

    # apply() runs synchronously in this process; no broker required
    task_refresh_apartment_chunk.apply(args=[apt_ids])

    print(f"\nDone at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}.")
    print("Run 'python dev/coverage_report.py --days 1 --per-apt' to see results.")


if __name__ == "__main__":
    main()
