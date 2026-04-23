#!/usr/bin/env python3
"""Fast platform-adapter coverage check: no LLM, no Playwright.

For each apartment URL, fetches the homepage with urllib, runs each
registered platform adapter's detect(), and shows which adapter fires
(or 'agent' if none match, meaning the LLM agent would handle it).

Usage:
    python dev/coverage_check.py                  # all market-rate apts
    python dev/coverage_check.py --ids 2,12,167   # specific IDs
    python dev/coverage_check.py --urls-file urls.txt
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "integration" / "agentic_scraper"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.apartment import Apartment

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)


def fetch_html(url: str, timeout: int = 12) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(600_000).decode("utf-8", errors="replace"), r.url
    except Exception as e:
        return None, str(e)


def detect_adapter(html: str, url: str) -> str:
    """Return the name of the first adapter that fires, or 'agent'."""
    from app.services.scraper_agent.platforms.registry import get_registry
    import app.services.scraper_agent.platforms.registry as _reg_mod
    # Force rebuild to pick up fresh imports
    _reg_mod._REGISTRY = None
    registry = get_registry()
    for adapter in registry:
        try:
            if adapter.detect(html or "", url):
                return adapter.name
        except Exception:
            pass
    return "agent"


def get_apartments(session: Session, ids_filter=None):
    stmt = select(Apartment).where(
        Apartment.is_available == True,
        Apartment.source_url.isnot(None),
    )
    if ids_filter:
        stmt = stmt.where(Apartment.id.in_(ids_filter))
    else:
        # Exclude government/non-profit/senior; focus on market-rate
        stmt = stmt.where(
            ~Apartment.title.ilike("%senior%"),
            ~Apartment.title.ilike("%affordable%"),
            ~Apartment.title.ilike("%housing authority%"),
            ~Apartment.source_url.ilike("%sfmohcd%"),
            ~Apartment.source_url.ilike("%sanjoseca.gov%"),
            ~Apartment.source_url.ilike("%scchousingauthority%"),
        )
    return session.execute(stmt.order_by(Apartment.id)).scalars().all()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", help="Comma-separated apartment IDs")
    parser.add_argument("--urls-file", help="File with one URL per line")
    parser.add_argument(
        "--previous-20", action="store_true",
        help="Use the exact 20 apartments from the previous crawl_new_20_results.json"
    )
    args = parser.parse_args()

    engine = create_engine(settings.DATABASE_URL)
    session = Session(bind=engine)

    ids_filter = None
    url_list = None

    if args.ids:
        ids_filter = [int(x.strip()) for x in args.ids.split(",")]
    elif args.urls_file:
        url_list = [l.strip() for l in open(args.urls_file) if l.strip()]
    elif args.previous_20:
        import json
        prev = json.load(open(ROOT / "dev" / "crawl_new_20_results.json"))
        url_list = [s["url"] for s in prev["selected"]]

    if url_list:
        # Build pseudo-apt list from URLs
        apartments = [
            type("Apt", (), {"id": i, "title": u.split("//")[1][:40], "source_url": u})()
            for i, u in enumerate(url_list, 1)
        ]
    else:
        apartments = get_apartments(session, ids_filter)

    print(f"\nChecking {len(apartments)} apartments...\n")
    print(f"{'#':>3}  {'Title':<38}  {'Adapter':<18}  {'Status'}")
    print("─" * 78)

    by_adapter: dict[str, list] = {}
    errors = []

    for apt in apartments:
        url = apt.source_url
        t0 = time.monotonic()
        html, final_url = fetch_html(url)
        elapsed = time.monotonic() - t0

        if html is None:
            adapter = "fetch_error"
            status = f"❌  {final_url[:50]}"
        else:
            adapter = detect_adapter(html, final_url or url)
            status = f"✓  ({elapsed:.1f}s)"
            if adapter == "agent":
                status = f"~  agent needed ({elapsed:.1f}s)"

        by_adapter.setdefault(adapter, []).append(apt.title[:38])
        label = f"[{adapter}]"
        print(f"{apt.id:>3}  {apt.title[:38]:<38}  {label:<18}  {status}")

    print("\n" + "═" * 78)
    print("SUMMARY BY ADAPTER")
    print("─" * 78)

    total = len(apartments)
    covered = sum(len(v) for k, v in by_adapter.items() if k not in ("agent", "fetch_error"))
    agent_count = len(by_adapter.get("agent", []))
    error_count = len(by_adapter.get("fetch_error", []))

    for adapter_name, titles in sorted(by_adapter.items(), key=lambda x: -len(x[1])):
        bar = "█" * len(titles)
        print(f"  {adapter_name:<18} {len(titles):>3}  {bar}")

    print("─" * 78)
    print(f"  Adapter coverage:  {covered}/{total}  ({100*covered//total if total else 0}%)")
    print(f"  Needs LLM agent:   {agent_count}")
    print(f"  Fetch errors:      {error_count}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
