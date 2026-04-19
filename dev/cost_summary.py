#!/usr/bin/env python3
"""Print a cost summary from the api_cost_log Postgres table.

Usage:
    python dev/cost_summary.py              # full history, grouped by day
    python dev/cost_summary.py --days 7     # last 7 days only
    python dev/cost_summary.py --by source  # aggregate by source
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running from repo root without installing the package
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.api_cost_log import ApiCostLog


def _make_session() -> Session:
    url = settings.DATABASE_URL.replace("@db:", "@localhost:")
    engine = create_engine(url)
    return Session(engine)


def fmt_usd(v) -> str:
    return f"${float(v):.4f}"


def summarize_by_day(db: Session, since: datetime | None) -> None:
    q = select(ApiCostLog)
    if since:
        q = q.where(ApiCostLog.ts >= since)
    rows = db.execute(q).scalars().all()

    if not rows:
        print("No entries found.")
        return

    by_day: dict[str, dict] = {}
    for r in rows:
        day = r.ts.strftime("%Y-%m-%d") if r.ts else "unknown"
        if day not in by_day:
            by_day[day] = {"cost": 0.0, "calls": 0, "scraper": 0, "google_maps": 0}
        by_day[day]["cost"] += float(r.cost_usd or 0)
        by_day[day]["calls"] += 1
        by_day[day][r.source] = by_day[day].get(r.source, 0) + 1

    total_cost = sum(d["cost"] for d in by_day.values())

    print(f"\n{'Date':<12} {'Calls':>6} {'Scraper':>8} {'Maps':>6} {'Cost':>10}")
    print("-" * 46)
    for day in sorted(by_day):
        d = by_day[day]
        print(f"{day:<12} {d['calls']:>6} {d.get('scraper', 0):>8} {d.get('google_maps', 0):>6} {fmt_usd(d['cost']):>10}")
    print("-" * 46)
    print(f"{'TOTAL':<12} {len(rows):>6} {sum(d.get('scraper', 0) for d in by_day.values()):>8} "
          f"{sum(d.get('google_maps', 0) for d in by_day.values()):>6} {fmt_usd(total_cost):>10}")


def summarize_by_source(db: Session, since: datetime | None) -> None:
    q = select(ApiCostLog)
    if since:
        q = q.where(ApiCostLog.ts >= since)
    rows = db.execute(q).scalars().all()

    if not rows:
        print("No entries found.")
        return

    by_source: dict[str, dict] = {}
    for r in rows:
        src = r.source
        if src not in by_source:
            by_source[src] = {"cost": 0.0, "calls": 0, "outcomes": {}}
        by_source[src]["cost"] += float(r.cost_usd or 0)
        by_source[src]["calls"] += 1
        by_source[src]["outcomes"][r.outcome] = by_source[src]["outcomes"].get(r.outcome, 0) + 1

    total_cost = sum(d["cost"] for d in by_source.values())
    total_calls = sum(d["calls"] for d in by_source.values())

    print(f"\n{'Source':<14} {'Calls':>6} {'Cost':>10}  Outcomes")
    print("-" * 60)
    for src, d in sorted(by_source.items()):
        outcomes_str = "  ".join(f"{k}:{v}" for k, v in sorted(d["outcomes"].items()))
        print(f"{src:<14} {d['calls']:>6} {fmt_usd(d['cost']):>10}  {outcomes_str}")
    print("-" * 60)
    print(f"{'TOTAL':<14} {total_calls:>6} {fmt_usd(total_cost):>10}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AptTrack API cost summary")
    parser.add_argument("--days", type=int, default=None, help="Show only last N days")
    parser.add_argument("--by", choices=["day", "source"], default="day",
                        help="Group results by day (default) or source")
    args = parser.parse_args()

    since = None
    if args.days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        print(f"Showing last {args.days} day(s)")

    db = _make_session()
    try:
        # Quick row count so the user sees something before the query
        total = db.execute(
            select(func.count()).select_from(ApiCostLog).where(
                ApiCostLog.ts >= since if since else text("true")
            )
        ).scalar_one()
        print(f"Loaded {total} entries from api_cost_log")

        if args.by == "source":
            summarize_by_source(db, since)
        else:
            summarize_by_day(db, since)
    finally:
        db.close()


if __name__ == "__main__":
    main()
