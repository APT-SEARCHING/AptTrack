#!/usr/bin/env python3
"""Set (or clear) the corporate_parent_url override on a ScrapeSiteRegistry row.

Usage:
    python dev/set_corporate_parent.py <domain> <corporate_url> <platform>
    python dev/set_corporate_parent.py <domain> --clear

Examples:
    python dev/set_corporate_parent.py 121tasman.com \\
        https://www.greystar.com/properties/san-jose-ca/121-tasman-apartments/floorplans \\
        greystar

    python dev/set_corporate_parent.py 121tasman.com --clear

The domain must already exist in scrape_site_registry (created when the apartment
was seeded).  If it doesn't exist yet, add the apartment first via seed_apartments.py.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.site_registry import ScrapeSiteRegistry


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Set or clear corporate_parent_url on a ScrapeSiteRegistry row."
    )
    parser.add_argument("domain", help="Domain key in scrape_site_registry, e.g. 121tasman.com")
    parser.add_argument(
        "corporate_url",
        nargs="?",
        help="Corporate platform URL to scrape instead (omit with --clear)",
    )
    parser.add_argument(
        "platform",
        nargs="?",
        help="Platform tag, e.g. 'greystar' (omit with --clear)",
    )
    parser.add_argument("--clear", action="store_true", help="Remove the corporate override")
    args = parser.parse_args()

    if not args.clear and not args.corporate_url:
        parser.error("Provide both <corporate_url> and <platform>, or use --clear")

    db = SessionLocal()
    try:
        row = db.execute(
            select(ScrapeSiteRegistry).where(ScrapeSiteRegistry.domain == args.domain)
        ).scalar_one_or_none()

        if row is None:
            print(f"ERROR: domain '{args.domain}' not found in scrape_site_registry.", file=sys.stderr)
            print("Seed the apartment first, then re-run this script.", file=sys.stderr)
            sys.exit(1)

        if args.clear:
            row.corporate_parent_url = None
            row.corporate_platform = None
            row.corporate_parent_set_at = None
            db.commit()
            print(f"Cleared corporate parent for {args.domain}")
        else:
            row.corporate_parent_url = args.corporate_url
            row.corporate_platform = args.platform
            row.corporate_parent_set_at = datetime.now(timezone.utc)
            db.commit()
            print(f"Set corporate parent for {args.domain}:")
            print(f"  corporate_parent_url = {args.corporate_url}")
            print(f"  corporate_platform   = {args.platform}")
            print(f"  set_at               = {row.corporate_parent_set_at.isoformat()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
