#!/usr/bin/env python3
"""Re-scrape all apartments that already have plans in Railway DB.

Clears path cache for each URL so the updated LLM prompt runs fresh,
then pushes scraped prices + sqft + plan names back to Railway.

Usage:
    python dev/batch_rescrape.py [--dry-run] [--ids 2,4,15]

Options:
    --dry-run   Print what would be scraped; don't write to DB.
    --ids       Comma-separated list of apartment IDs to scrape (default: all with plans).
    --no-clear  Skip cache clearing (use existing path cache, 0 LLM calls on cache hit).
"""
from __future__ import annotations
import argparse, asyncio, os, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import psycopg2
from psycopg2.extras import execute_values

RAILWAY_DB = "postgresql://postgres:NDrijYZDpKGoFRpaBbHhtZYsGvxmXKWJ@maglev.proxy.rlwy.net:34474/railway"

from tests.integration.agentic_scraper.agent import ApartmentAgent
from tests.integration.agentic_scraper.path_cache import invalidate_path


def get_apartments_with_plans(ids_filter=None):
    conn = psycopg2.connect(RAILWAY_DB)
    cur = conn.cursor()
    if ids_filter:
        placeholders = ",".join(["%s"] * len(ids_filter))
        cur.execute(f"""
            SELECT DISTINCT a.id, a.title, a.source_url
            FROM apartments a
            JOIN plans p ON p.apartment_id = a.id
            WHERE a.is_available = true
              AND a.source_url IS NOT NULL
              AND a.id IN ({placeholders})
            ORDER BY a.id
        """, ids_filter)
    else:
        cur.execute("""
            SELECT DISTINCT a.id, a.title, a.source_url
            FROM apartments a
            JOIN plans p ON p.apartment_id = a.id
            WHERE a.is_available = true
              AND a.source_url IS NOT NULL
              AND a.title NOT ILIKE '%senior%'
            ORDER BY a.id
        """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows  # [(id, title, source_url), ...]


def get_plans_for_apt(cur, apt_id):
    cur.execute("""
        SELECT id, name, bedrooms, area_sqft
        FROM plans WHERE apartment_id = %s
    """, (apt_id,))
    return cur.fetchall()  # [(id, name, bedrooms, area_sqft), ...]


def match_plan(plans, fp_name, fp_bedrooms, fp_sqft):
    """Return plan_id matching the scraped floor plan, or None."""
    # 1. Exact name match
    for pid, pname, pbeds, psqft in plans:
        if pname == fp_name:
            return pid
    # 2. Fuzzy: same bedrooms + sqft within 10%
    if fp_bedrooms is not None and fp_sqft is not None:
        for pid, pname, pbeds, psqft in plans:
            if pbeds == fp_bedrooms and psqft is not None and psqft > 0:
                if abs(psqft - fp_sqft) / psqft < 0.10:
                    return pid
    return None


def persist_results(apt_id, result, dry_run=False):
    """Write scraped data back to Railway DB."""
    conn = psycopg2.connect(RAILWAY_DB)
    cur = conn.cursor()

    plans = get_plans_for_apt(cur, apt_id)
    now = "now()"

    updated = 0
    skipped = 0
    history_rows = []

    for fp in result.floor_plans:
        plan_id = match_plan(plans, fp.name, fp.bedrooms, fp.size_sqft)
        if plan_id is None:
            skipped += 1
            continue

        updates = {}
        if fp.size_sqft is not None:
            updates["area_sqft"] = fp.size_sqft
        if fp.min_price is not None:
            updates["current_price"] = fp.min_price
            updates["price"] = fp.min_price
            history_rows.append((plan_id, fp.min_price))
        if fp.external_url:
            updates["external_url"] = fp.external_url
        if fp.floor_level is not None:
            updates["floor_level"] = fp.floor_level
        if fp.facing:
            updates["facing"] = fp.facing

        if updates:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            vals = list(updates.values()) + [plan_id]
            if not dry_run:
                cur.execute(f"UPDATE plans SET {set_clause}, updated_at = now() WHERE id = %s", vals)
            updated += 1

    # PlanPriceHistory
    if history_rows and not dry_run:
        execute_values(cur, """
            INSERT INTO plan_price_history (plan_id, price, recorded_at)
            VALUES %s
        """, history_rows,
        template="(%s, %s, now())")

    # Apartment-level: amenities + specials
    apt_updates = {}
    if result.current_special is not None:
        apt_updates["current_special"] = result.current_special
    if result.amenities:
        for key in ("pets_allowed", "has_parking", "has_pool", "has_gym",
                    "has_dishwasher", "has_washer_dryer", "has_air_conditioning"):
            val = result.amenities.get(key)
            if val is not None:
                apt_updates[key] = val
    if apt_updates and not dry_run:
        set_clause = ", ".join(f"{k} = %s" for k in apt_updates)
        cur.execute(f"UPDATE apartments SET {set_clause}, updated_at = now() WHERE id = %s",
                    list(apt_updates.values()) + [apt_id])

    if not dry_run:
        conn.commit()
    cur.close()
    conn.close()
    return updated, skipped


async def run(ids_filter, dry_run, clear_cache):
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY not set"); sys.exit(1)

    apts = get_apartments_with_plans(ids_filter)
    print(f"{'[DRY RUN] ' if dry_run else ''}Scraping {len(apts)} apartments...\n")

    agent = ApartmentAgent(api_key=api_key)
    total_cost = 0.0
    success = fail = 0

    for i, (apt_id, title, url) in enumerate(apts, 1):
        print(f"[{i}/{len(apts)}] {title} (id={apt_id})")
        print(f"  URL: {url}")

        if clear_cache:
            invalidate_path(url)

        try:
            result, metrics = await agent.scrape(url)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            fail += 1
            time.sleep(5)
            continue

        if result is None or not result.floor_plans:
            print(f"  No plans returned — skipping")
            fail += 1
            time.sleep(5)
            continue

        plans_with_sqft = sum(1 for fp in result.floor_plans if fp.size_sqft)
        print(f"  Scraped {len(result.floor_plans)} plans ({plans_with_sqft} with sqft)  "
              f"cost=${metrics.total_cost_usd:.4f}  iters={metrics.iterations}")

        # Print plan table
        for fp in result.floor_plans:
            sqft = f"{int(fp.size_sqft)}" if fp.size_sqft else "—"
            price = f"${fp.min_price:,.0f}" if fp.min_price else "—"
            print(f"    {(fp.name or ''):<25} beds={fp.bedrooms} sqft={sqft:>6} price={price}")

        updated, skipped = persist_results(apt_id, result, dry_run=dry_run)
        print(f"  {'[DRY RUN] ' if dry_run else ''}DB: {updated} plans updated, {skipped} unmatched")
        total_cost += metrics.total_cost_usd
        success += 1

        # 5s rate limit between same-domain scrapes
        if i < len(apts):
            time.sleep(5)

    print(f"\n{'='*60}")
    print(f"Done. {success} success, {fail} failed")
    print(f"Total cost: ~${total_cost:.4f}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--ids", help="Comma-separated apartment IDs (e.g. 2,4,15)")
    parser.add_argument("--no-clear", action="store_true", help="Don't invalidate path cache")
    args = parser.parse_args()

    ids_filter = [int(x) for x in args.ids.split(",")] if args.ids else None
    asyncio.run(run(ids_filter, dry_run=args.dry_run, clear_cache=not args.no_clear))
