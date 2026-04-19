#!/usr/bin/env python3
"""Print a cost summary from logs/cost_log.jsonl.

Usage:
    python dev/cost_summary.py              # full history, grouped by day
    python dev/cost_summary.py --days 7     # last 7 days only
    python dev/cost_summary.py --by source  # aggregate by source
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG_FILE = Path(__file__).parent.parent / "logs" / "cost_log.jsonl"


def load_entries(since: datetime | None) -> list[dict]:
    if not LOG_FILE.exists():
        print(f"No log file at {LOG_FILE}")
        sys.exit(0)
    entries = []
    with LOG_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if since:
                    ts = datetime.fromisoformat(e["ts"])
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < since:
                        continue
                entries.append(e)
            except Exception:
                pass
    return entries


def fmt_usd(v: float) -> str:
    return f"${v:.4f}"


def summarize_by_day(entries: list[dict]) -> None:
    by_day: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "calls": 0, "scraper": 0, "google_maps": 0})
    for e in entries:
        day = e["ts"][:10]
        by_day[day]["cost"] += e.get("cost_usd", 0.0)
        by_day[day]["calls"] += 1
        by_day[day][e.get("source", "unknown")] += 1

    total_cost = sum(e.get("cost_usd", 0.0) for e in entries)

    print(f"\n{'Date':<12} {'Calls':>6} {'Scraper':>8} {'Maps':>6} {'Cost':>10}")
    print("-" * 46)
    for day in sorted(by_day):
        d = by_day[day]
        print(f"{day:<12} {d['calls']:>6} {d['scraper']:>8} {d['google_maps']:>6} {fmt_usd(d['cost']):>10}")
    print("-" * 46)
    print(f"{'TOTAL':<12} {len(entries):>6} {sum(d['scraper'] for d in by_day.values()):>8} "
          f"{sum(d['google_maps'] for d in by_day.values()):>6} {fmt_usd(total_cost):>10}")


def summarize_by_source(entries: list[dict]) -> None:
    by_source: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "calls": 0, "outcomes": defaultdict(int)})
    for e in entries:
        src = e.get("source", "unknown")
        by_source[src]["cost"] += e.get("cost_usd", 0.0)
        by_source[src]["calls"] += 1
        by_source[src]["outcomes"][e.get("outcome", "?")] += 1

    print(f"\n{'Source':<14} {'Calls':>6} {'Cost':>10}  Outcomes")
    print("-" * 60)
    for src, d in sorted(by_source.items()):
        outcomes_str = "  ".join(f"{k}:{v}" for k, v in sorted(d["outcomes"].items()))
        print(f"{src:<14} {d['calls']:>6} {fmt_usd(d['cost']):>10}  {outcomes_str}")

    total_cost = sum(e.get("cost_usd", 0.0) for e in entries)
    print("-" * 60)
    print(f"{'TOTAL':<14} {len(entries):>6} {fmt_usd(total_cost):>10}")


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

    entries = load_entries(since)
    print(f"Loaded {len(entries)} entries from {LOG_FILE}")

    if not entries:
        print("No entries found.")
        return

    if args.by == "source":
        summarize_by_source(entries)
    else:
        summarize_by_day(entries)


if __name__ == "__main__":
    main()
