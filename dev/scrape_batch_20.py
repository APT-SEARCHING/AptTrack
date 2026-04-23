#!/usr/bin/env python3
"""Scrape the previous-20 apartment list and report coverage.

Uses the ApartmentAgent (same code path as production worker) so results
reflect real adapter + LLM agent behavior.  Results written to
dev/scrape_batch_20_results.json.

Usage:
    python dev/scrape_batch_20.py
    python dev/scrape_batch_20.py --no-cache   # clear path cache first
    python dev/scrape_batch_20.py --only-adapters  # skip LLM (dry platform check)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from tests.integration.agentic_scraper.agent import ApartmentAgent
from tests.integration.agentic_scraper.path_cache import invalidate_path


PREV_20 = json.loads((ROOT / "dev" / "crawl_new_20_results.json").read_text())["selected"]


async def scrape_one(agent: ApartmentAgent, title: str, url: str) -> dict:
    t0 = time.monotonic()
    try:
        result, metrics = await agent.scrape(url)
        elapsed = time.monotonic() - t0
        if result is None or not result.floor_plans:
            return {
                "title": title, "url": url,
                "n_plans": 0, "priced": 0, "with_sqft": 0, "clean_name": 0,
                "cost_usd": metrics.total_cost_usd if metrics else 0,
                "elapsed": round(elapsed, 1),
                "outcome": "no_data",
            }
        plans = result.floor_plans
        priced = sum(1 for p in plans if p.min_price)
        with_sqft = sum(1 for p in plans if p.size_sqft)
        clean = sum(1 for p in plans if p.name and len(p.name) >= 2)
        return {
            "title": title, "url": url,
            "n_plans": len(plans),
            "priced": priced,
            "with_sqft": with_sqft,
            "clean_name": clean,
            "cost_usd": round(metrics.total_cost_usd if metrics else 0, 4),
            "elapsed": round(elapsed, 1),
            "outcome": "ok",
            "plans_sample": [
                {"name": p.name, "beds": p.bedrooms, "sqft": p.size_sqft,
                 "price": p.min_price, "avail": p.availability}
                for p in plans[:4]
            ],
        }
    except Exception as exc:
        return {
            "title": title, "url": url,
            "n_plans": 0, "priced": 0, "with_sqft": 0, "clean_name": 0,
            "cost_usd": 0, "elapsed": round(time.monotonic() - t0, 1),
            "outcome": f"error: {exc}",
        }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-cache", action="store_true", help="Clear path cache before scraping")
    args = parser.parse_args()

    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY not set in .env"); sys.exit(1)

    if args.no_cache:
        print("Clearing path cache for all 20 URLs...")
        for apt in PREV_20:
            invalidate_path(apt["url"])

    agent = ApartmentAgent(api_key=api_key)

    results = []
    total_cost = 0.0

    print(f"\nScraping {len(PREV_20)} apartments...\n")
    print(f"{'Title':<42} {'Plans':>5} {'Priced':>6} {'Sqft%':>6} {'Cost':>7}  Outcome")
    print("─" * 80)

    for apt in PREV_20:
        title = apt["title"]
        url = apt["url"]
        sys.stdout.write(f"  {title[:40]:<40} ... ")
        sys.stdout.flush()

        r = await scrape_one(agent, title, url)
        results.append(r)
        total_cost += r["cost_usd"]

        sqft_pct = f"{100 * r['with_sqft'] // r['n_plans']}%" if r["n_plans"] else "—"
        status = "✓" if r["n_plans"] > 0 else "✗"
        print(f"\r{status} {title[:40]:<40} {r['n_plans']:>5} {r['priced']:>6} {sqft_pct:>6} ${r['cost_usd']:>5.3f}  {r['outcome'][:30]}")

    # Summary
    print("\n" + "═" * 80)
    total_plans = sum(r["n_plans"] for r in results)
    total_priced = sum(r["priced"] for r in results)
    total_sqft = sum(r["with_sqft"] for r in results)
    wins = sum(1 for r in results if r["n_plans"] > 0)
    errors = sum(1 for r in results if r["outcome"].startswith("error"))

    print(f"\nResults: {wins}/{len(results)} apts returned plans")
    print(f"Plans:   {total_plans} total, {total_priced} priced ({100*total_priced//total_plans if total_plans else 0}%), "
          f"{total_sqft} with sqft ({100*total_sqft//total_plans if total_plans else 0}%)")
    print(f"Cost:    ${total_cost:.4f}")
    print(f"Errors:  {errors}")

    # Failures
    failures = [r for r in results if r["n_plans"] == 0]
    if failures:
        print(f"\nNo data ({len(failures)}):")
        for r in failures:
            print(f"  {r['title']}: {r['outcome'][:60]}")

    # Write results
    out = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "total_cost_usd": round(total_cost, 4),
        "results": results,
    }
    out_path = ROOT / "dev" / "scrape_batch_20_results.json"
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
