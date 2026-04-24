#!/usr/bin/env python3
"""Data-quality audit for AptTrack.

Prints tidy text blocks covering plan quality, scrape outcomes,
price-history growth, notification health, API costs, and B4 symptom check.

Usage:
    python dev/audit.py                  # default: 14-day window
    python dev/audit.py --days 7
    python dev/audit.py > audit-$(date +%Y-%m-%d).txt
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
          AND outcome = 'platform_direct'
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
        q_price_history_growth(db, args.days)
        q_notification_health(db, args.days)
        q_cost_summary(db, args.days)
        q_suspicious_names(db)
    finally:
        db.close()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
