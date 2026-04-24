#!/usr/bin/env python3
"""Per-adapter scrape coverage report from scrape_runs.

Shows how many scrapes each platform adapter handled vs. the full LLM ReAct
loop — lets you see which adapters are pulling their weight and which sites
still need specific adapters written.

Usage:
    python dev/coverage_report.py              # all time
    python dev/coverage_report.py --days 7     # last 7 days
    python dev/coverage_report.py --days 30    # last 30 days
    python dev/coverage_report.py --days 1 --per-apt   # last 24h, per-apartment detail
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.apartment import Apartment
from app.models.scrape_run import ScrapeRun


def _make_session() -> Session:
    url = settings.DATABASE_URL.replace("@db:", "@localhost:")
    engine = create_engine(url)
    return Session(engine)


# Success outcomes — scrape delivered data (zero-cost or LLM)
_SUCCESS = {"success", "cache_hit", "platform_direct", "content_unchanged"}
# Hard-failure outcomes — no data, worth investigating
_FAILURES = {"validated_fail", "hard_fail", "skipped_negative_cache"}


def _print_aggregate(rows: list, since: datetime | None) -> None:
    total = len(rows)

    outcome_counts: dict[str, int] = defaultdict(int)
    for r in rows:
        outcome_counts[r.outcome] += 1

    print(f"Total scrape_runs: {total}\n")
    print(f"{'Outcome':<30} {'Count':>6}  {'%':>6}")
    print("-" * 46)
    for outcome, count in sorted(outcome_counts.items(), key=lambda x: -x[1]):
        pct = 100.0 * count / total
        print(f"  {outcome:<28} {count:>6}  {pct:>5.1f}%")

    # ── Per-adapter breakdown (platform_direct rows only) ──────────────────
    platform_rows = [r for r in rows if r.outcome == "platform_direct"]
    if not platform_rows:
        print("\nNo platform_direct rows yet.")
        return

    adapter_counts: dict[str, int] = defaultdict(int)
    for r in platform_rows:
        key = r.adapter_name or "(unknown)"
        adapter_counts[key] += 1

    pt_total = len(platform_rows)
    llm_total = outcome_counts.get("success", 0) + outcome_counts.get("cache_hit", 0)
    zero_cost = outcome_counts.get("content_unchanged", 0) + pt_total

    print(f"\n── Platform adapter breakdown ({pt_total} platform_direct runs) ──")
    print(f"\n{'Adapter':<24} {'Runs':>6}  {'% of platform':>14}  {'% of all':>10}")
    print("-" * 60)
    for adapter, count in sorted(adapter_counts.items(), key=lambda x: -x[1]):
        pct_pt = 100.0 * count / pt_total
        pct_all = 100.0 * count / total
        print(f"  {adapter:<22} {count:>6}  {pct_pt:>13.1f}%  {pct_all:>9.1f}%")

    print()
    print(f"  LLM loop runs (success + cache_hit): {llm_total:>6}  ({100.0 * llm_total / total:.1f}%)")
    print(f"  Zero-cost runs (content_unchanged + platform_direct): {zero_cost:>6}  ({100.0 * zero_cost / total:.1f}%)")

    llm_rows = [r for r in rows if r.outcome in ("success", "cache_hit")]
    if llm_rows:
        avg_llm_cost = sum(r.cost_usd or 0.0 for r in llm_rows) / len(llm_rows)
        saved = avg_llm_cost * pt_total
        print(f"\n  Avg LLM cost per scrape: ${avg_llm_cost:.4f}")
        print(f"  Estimated cost saved by adapters: ${saved:.4f}")
    print()


def _print_per_apt(db: Session, rows: list, since: datetime | None) -> None:
    """Print one line per apartment showing its last scrape outcome in the window."""
    # Build a map: apartment_id → most recent ScrapeRun in window
    latest: dict[int, ScrapeRun] = {}
    for r in rows:
        if r.apartment_id is None:
            continue
        if r.apartment_id not in latest or r.run_at > latest[r.apartment_id].run_at:
            latest[r.apartment_id] = r

    # Load apartment titles for the IDs we saw
    apt_ids = list(latest.keys())
    apts: dict[int, Apartment] = {}
    if apt_ids:
        apt_rows = db.execute(
            select(Apartment).where(Apartment.id.in_(apt_ids))
        ).scalars().all()
        apts = {a.id: a for a in apt_rows}

    # Also find apartments that had NO run in the window (were they even active?)
    all_active = db.execute(
        select(Apartment).where(Apartment.is_available == True)  # noqa: E712
    ).scalars().all()
    no_run_ids = {a.id for a in all_active if a.id not in latest}

    # Tally successes vs failures for the summary line
    success_count = sum(1 for r in latest.values() if r.outcome in _SUCCESS)
    fail_count = sum(1 for r in latest.values() if r.outcome in _FAILURES)
    skipped_count = sum(
        1 for r in latest.values()
        if r.outcome in ("skipped_unscrapeable", "skipped_negative_cache")
    )

    print(f"\n── Per-apartment last outcome ({'last 24h' if since else 'all time'}) ──\n")
    col_w = [32, 22, 14, 24, 16]
    header = f"  {'Apartment':<{col_w[0]}}  {'City':<{col_w[1]}}  {'Outcome':<{col_w[2]}}  {'Adapter':<{col_w[3]}}  {'Run at':>{col_w[4]}}"
    print(header)
    print("  " + "  ".join("-" * w for w in col_w))

    for apt_id, run in sorted(latest.items(), key=lambda kv: kv[1].outcome):
        apt = apts.get(apt_id)
        title = (apt.title[:30] + "..") if apt and len(apt.title) > 32 else (apt.title if apt else f"[apt {apt_id}]")
        city = apt.city if apt else ""
        adapter = run.adapter_name or ""
        run_at_str = run.run_at.strftime("%m-%d %H:%M") if run.run_at else ""
        flag = " ✗" if run.outcome in _FAILURES else ""
        print(f"  {title:<{col_w[0]}}  {city:<{col_w[1]}}  {run.outcome:<{col_w[2]}}  {adapter:<{col_w[3]}}  {run_at_str:>{col_w[4]}}{flag}")

    if no_run_ids:
        print(f"\n  No scrape in window ({len(no_run_ids)} active apts):")
        for a in all_active:
            if a.id in no_run_ids:
                print(f"    [{a.id:>3}] {a.title}  ({a.city})  src={a.source_url}")

    print(f"\n  Summary: {success_count} success  {fail_count} fail  "
          f"{skipped_count} skipped  {len(no_run_ids)} no-run")

    # Highlight failures for easy copy-paste into dev/set_data_source_type.py
    fail_rows = [(apt_id, r) for apt_id, r in latest.items() if r.outcome in _FAILURES]
    if fail_rows:
        print(f"\n  ── Failures to investigate ({len(fail_rows)}) ──")
        for apt_id, run in fail_rows:
            apt = apts.get(apt_id)
            title = apt.title if apt else f"[apt {apt_id}]"
            print(f"    [{apt_id:>3}] {title}  outcome={run.outcome}  url={run.url}")


def main() -> None:
    parser = argparse.ArgumentParser(description="AptTrack scraper adapter coverage report")
    parser.add_argument("--days", type=int, default=None, help="Show only last N days")
    parser.add_argument("--per-apt", action="store_true",
                        help="Also print per-apartment last-outcome table")
    args = parser.parse_args()

    since: datetime | None = None
    if args.days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
        print(f"Showing last {args.days} day(s)\n")

    db = _make_session()
    try:
        q = select(ScrapeRun)
        if since:
            q = q.where(ScrapeRun.run_at >= since)
        rows = db.execute(q).scalars().all()

        if not rows:
            print("No scrape_runs found.")
            return

        _print_aggregate(rows, since)

        if args.per_apt:
            _print_per_apt(db, rows, since)

    finally:
        db.close()


if __name__ == "__main__":
    main()
