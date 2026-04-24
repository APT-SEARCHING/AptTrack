#!/usr/bin/env python3
"""Data-quality audit for AptTrack.

Prints tidy text blocks covering plan quality, scrape outcomes,
price-history growth, notification health, API costs, and B4 symptom check.

Usage:
    python dev/audit.py                  # default: 14-day window
    python dev/audit.py --days 7
    python dev/audit.py > audit-$(date +%Y-%m-%d).txt
"""
# ---------------------------------------------------------------------------
# Target metrics (Phase 1 + Hint deployed)
#   platform_direct_static:    30-50%
#   platform_direct_rendered:  20-40%
#   content_unchanged:         10-20%
#   cache_hit:                  5-10%
#   not_apartment:              0-5%
#   no_data + hard_fail:       <5%
#   success (LLM fallback):    <5%
# ---------------------------------------------------------------------------
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def _make_session() -> Session:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    return Session(bind=engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_header(title: str) -> None:
    bar = "=" * 60
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


def _rows_to_table(rows, headers: list[str]) -> str:
    """Format a list of tuples as a fixed-width table."""
    if not rows:
        return "  (no data)"
    col_widths = [len(h) for h in headers]
    str_rows = []
    for row in rows:
        sr = [str(v) if v is not None else "NULL" for v in row]
        str_rows.append(sr)
        for i, cell in enumerate(sr):
            col_widths[i] = max(col_widths[i], len(cell))
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    sep = "  " + "  ".join("-" * w for w in col_widths)
    lines = [fmt.format(*headers), sep]
    for sr in str_rows:
        lines.append(fmt.format(*sr))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def q_plan_quality(db: Session) -> None:
    _print_header("Plan data quality")
    row = db.execute(text("""
        SELECT
            count(*)                                                              AS total_plans,
            count(*) FILTER (WHERE area_sqft IS NOT NULL AND area_sqft > 0)      AS with_sqft,
            round(100.0 * count(*) FILTER (WHERE area_sqft IS NOT NULL AND area_sqft > 0)
                  / NULLIF(count(*), 0), 1)                                      AS sqft_pct,
            count(*) FILTER (
                WHERE name IS NOT NULL
                  AND name NOT IN ('Unit','Favorite','Tour','Tour Now','Available Now',
                                   'View Details','Select','Share','Save','')
            )                                                                    AS clean_name,
            round(100.0 * count(*) FILTER (
                WHERE name IS NOT NULL
                  AND name NOT IN ('Unit','Favorite','Tour','Tour Now','Available Now',
                                   'View Details','Select','Share','Save','')
            ) / NULLIF(count(*), 0), 1)                                          AS clean_name_pct,
            count(*) FILTER (WHERE current_price IS NOT NULL)                   AS priced,
            count(*) FILTER (WHERE external_url IS NOT NULL)                    AS with_url,
            count(*) FILTER (WHERE floor_level IS NOT NULL)                     AS with_floor
        FROM plans
    """)).one()
    headers = ["total", "with_sqft", "sqft_%", "clean_name", "clean_%", "priced", "with_url", "with_floor"]
    print(_rows_to_table([row], headers))


def q_scrape_outcomes(db: Session, days: int) -> None:
    _print_header(f"Scrape run outcomes (last {days} days)")
    rows = db.execute(text(f"""
        SELECT outcome,
               count(*)                                    AS runs,
               round(avg(cost_usd)::numeric, 4)            AS avg_cost_usd,
               round(avg(elapsed_sec)::numeric, 1)         AS avg_elapsed_sec
        FROM scrape_runs
        WHERE run_at > now() - interval '{days} days'
        GROUP BY 1
        ORDER BY 2 DESC
    """)).fetchall()
    print(_rows_to_table(rows, ["outcome", "runs", "avg_cost_usd", "avg_elapsed_sec"]))

    # Per-adapter split for platform_direct rows
    adapter_rows = db.execute(text(f"""
        SELECT coalesce(adapter_name, '(unknown)')         AS adapter,
               count(*)                                    AS runs,
               round(avg(elapsed_sec)::numeric, 1)         AS avg_elapsed_sec
        FROM scrape_runs
        WHERE run_at > now() - interval '{days} days'
          AND outcome IN ('platform_direct', 'platform_direct_static', 'platform_direct_rendered')
        GROUP BY 1
        ORDER BY 2 DESC
    """)).fetchall()
    if adapter_rows:
        print("\n  platform_direct by adapter:")
        print(_rows_to_table(adapter_rows, ["adapter", "runs", "avg_elapsed_sec"]))


def q_price_history_growth(db: Session, days: int) -> None:
    _print_header(f"PlanPriceHistory growth (last {days} days)")
    rows = db.execute(text(f"""
        SELECT date_trunc('day', recorded_at)::date  AS day,
               count(*)                              AS rows,
               count(DISTINCT plan_id)               AS distinct_plans
        FROM plan_price_history
        WHERE recorded_at > now() - interval '{days} days'
        GROUP BY 1
        ORDER BY 1
    """)).fetchall()
    print(_rows_to_table(rows, ["day", "rows", "distinct_plans"]))
    if rows:
        total = sum(r[1] for r in rows)
        days_with_data = len(rows)
        print(f"\n  Total rows: {total}   Days with data: {days_with_data}   "
              f"Avg rows/day: {total / days_with_data:.1f}")


def q_notification_health(db: Session, days: int) -> None:
    _print_header(f"Notification health (last {days} days)")
    rows = db.execute(text(f"""
        SELECT channel,
               status,
               count(*) AS events
        FROM notification_events
        WHERE sent_at > now() - interval '{days} days'
        GROUP BY 1, 2
        ORDER BY 1, 3 DESC
    """)).fetchall()
    print(_rows_to_table(rows, ["channel", "status", "events"]))


def q_cost_summary(db: Session, days: int) -> None:
    _print_header(f"API cost summary (last {days} days)")
    rows = db.execute(text(f"""
        SELECT source,
               count(*)                            AS calls,
               round(sum(cost_usd)::numeric, 4)    AS total_usd
        FROM api_cost_log
        WHERE ts > now() - interval '{days} days'
        GROUP BY 1
        ORDER BY 3 DESC
    """)).fetchall()
    print(_rows_to_table(rows, ["source", "calls", "total_usd"]))
    if rows:
        grand = sum(float(r[2]) for r in rows)
        print(f"\n  Grand total: ${grand:.4f}")


def q_suspicious_names(db: Session) -> None:
    _print_header("Suspicious plan names (B4 symptom check)")
    rows = db.execute(text("""
        SELECT name,
               count(*) AS count
        FROM plans
        WHERE lower(name) IN (
            'favorite','tour','tour now','view details','available',
            'available now','select','share','save','unit',
            'schedule tour','apply now','contact','compare','hide',
            'show more','schedule','inquire','see details'
        )
        GROUP BY name
        ORDER BY 2 DESC
    """)).fetchall()
    if rows:
        print(_rows_to_table(rows, ["name", "count"]))
        print(f"\n  *** {sum(r[1] for r in rows)} contaminated plan rows — B4 not yet applied or new data ***")
    else:
        print("  OK — no contaminated plan names found.")


def q_adapter_hint_health(db: Session) -> None:
    _print_header("Adapter hint health (sites with stale or missing last success)")
    rows = db.execute(text("""
        SELECT domain,
               coalesce(last_successful_adapter, '-')  AS adapter,
               last_adapter_success_at,
               is_active
        FROM scrape_site_registry
        WHERE is_active = true
          AND (last_adapter_success_at IS NULL
               OR last_adapter_success_at < now() - interval '7 days')
        ORDER BY last_adapter_success_at NULLS FIRST
    """)).fetchall()
    if not rows:
        print("  OK — all active sites have a fresh adapter hint (< 7 days old).")
        return
    for row in rows:
        if row.last_adapter_success_at is None:
            age = "never"
        else:
            days_old = (datetime.now(timezone.utc) - row.last_adapter_success_at).days
            age = f"{days_old}d ago"
        print(f"  {row.domain:<45}  {row.adapter:<20}  {age}")
    print(f"\n  {len(rows)} site(s) with stale/missing hints — may need manual scrape or adapter coverage.")


def q_hint_distribution(db: Session) -> None:
    _print_header("Registry Hint Distribution")
    rows = db.execute(text("""
        SELECT last_successful_adapter, count(*) AS n,
               max(last_adapter_success_at) AS last_success
        FROM scrape_site_registry
        WHERE is_active = true AND last_successful_adapter IS NOT NULL
        GROUP BY 1
        ORDER BY n DESC
    """)).all()

    if not rows:
        print("  (no hints recorded yet)")
        return

    pollution_found = False
    for r in rows:
        flag = ""
        if r.last_successful_adapter == "universal_dom":
            flag = "   ⚠ POLLUTED — should not be hint (fallback adapter)"
            pollution_found = True
        print(f"  {r.last_successful_adapter:<20} {r.n:>4}    last: {r.last_success}{flag}")

    if pollution_found:
        print("\n  ⚠ Run: UPDATE scrape_site_registry SET last_successful_adapter = NULL")
        print("         WHERE last_successful_adapter = 'universal_dom';")


def q_rendered_latency(db: Session) -> None:
    _print_header("Rendered Fetch Latency (last 3 days)")
    rows = db.execute(text("""
        SELECT
            outcome,
            adapter_name,
            count(*) AS n,
            round(avg(elapsed_sec)::numeric, 1) AS avg_s,
            round(percentile_cont(0.95) WITHIN GROUP (ORDER BY elapsed_sec)::numeric, 1) AS p95_s
        FROM scrape_runs
        WHERE run_at > now() - interval '3 days'
          AND outcome IN ('platform_direct_rendered', 'not_apartment', 'no_data')
        GROUP BY 1, 2
        HAVING count(*) >= 3
        ORDER BY avg_s DESC
    """)).all()

    if not rows:
        print("  (no rendered-fetch runs in last 3 days, or < 3 per bucket)")
        return

    for r in rows:
        flag = ""
        if r.avg_s is not None and float(r.avg_s) > 13:
            flag = "   ⚠ fetch_rendered waiting for timeout"
        print(f"  {r.outcome:<30} {(r.adapter_name or '-'):<18} n={r.n:<4} avg={r.avg_s}s p95={r.p95_s}s{flag}")


def q_outcome_24h(db: Session) -> None:
    _print_header("Scrape Outcome Distribution (last 24h)")
    rows = db.execute(text("""
        SELECT
            outcome,
            count(*) AS n,
            round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct,
            round(avg(elapsed_sec)::numeric, 1) AS avg_s,
            round(avg(cost_usd)::numeric, 4) AS avg_cost
        FROM scrape_runs
        WHERE run_at > now() - interval '24 hours'
        GROUP BY 1
        ORDER BY n DESC
    """)).all()

    if not rows:
        print("  (no scrape_runs in last 24h)")
        return

    total = sum(r.n for r in rows)
    print(f"  Total scrapes in last 24h: {total}")
    successful_outcomes = ("platform_direct_static", "platform_direct_rendered", "cache_hit", "content_unchanged")
    successful = sum(r.n for r in rows if r.outcome in successful_outcomes)
    print(f"  Successful (platform/cache/unchanged): {successful}/{total} ({100*successful/max(total,1):.1f}%)\n")
    for r in rows:
        print(f"  {r.outcome:<32} n={r.n:<4} ({r.pct:>5.1f}%) avg={r.avg_s}s ${r.avg_cost}")


def q_area_sqft_zero(db: Session) -> None:
    _print_header("Plans with area_sqft = 0 (B1 stale placeholder check)")
    rows = db.execute(text("""
        SELECT a.title, a.city,
               count(*) FILTER (WHERE p.area_sqft = 0) AS zero_sqft,
               count(*) FILTER (WHERE p.area_sqft > 0) AS good_sqft,
               count(*)                                AS total
        FROM plans p
        JOIN apartments a ON a.id = p.apartment_id
        GROUP BY a.id, a.title, a.city
        HAVING count(*) FILTER (WHERE p.area_sqft = 0) > 0
        ORDER BY 3 DESC
    """)).fetchall()
    if rows:
        print(_rows_to_table(rows, ["apartment", "city", "zero_sqft", "good_sqft", "total"]))
    else:
        print("  OK — no plans have area_sqft = 0.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="AptTrack data-quality audit")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days (default: 14)")
    args = parser.parse_args()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"AptTrack data-quality audit — {now}  (lookback: {args.days} days)")

    db = _make_session()
    try:
        q_plan_quality(db)
        q_area_sqft_zero(db)
        q_scrape_outcomes(db, args.days)
        q_outcome_24h(db)
        q_rendered_latency(db)
        q_price_history_growth(db, args.days)
        q_notification_health(db, args.days)
        q_cost_summary(db, args.days)
        q_suspicious_names(db)
        q_adapter_hint_health(db)
        q_hint_distribution(db)
    finally:
        db.close()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
