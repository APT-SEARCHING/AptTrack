#!/usr/bin/env python3
"""Scrape a single apartment URL and print the result.

Usage:
    python dev/scrape_single.py <url> [--clear-cache]
"""
from __future__ import annotations
import argparse, asyncio, json, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from tests.integration.agentic_scraper.agent import ApartmentAgent

async def main(url: str, clear_cache: bool):
    import os
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY not set"); sys.exit(1)

    if clear_cache:
        from tests.integration.agentic_scraper.path_cache import invalidate_path
        invalidate_path(url)
        print(f"Cache cleared for {url}")

    agent = ApartmentAgent(api_key=api_key)
    print(f"Scraping: {url}\n{'='*60}")
    result, metrics = await agent.scrape(url)

    if result is None:
        print("No result returned.")
        return

    print(f"Iterations: {metrics.iterations}, LLM calls: {len(metrics.calls)}")
    print(f"Cost: ~${metrics.total_cost_usd:.4f}")
    print()

    plans = result.floor_plans
    if not plans:
        print("No plans found.")
        return

    print(f"{'Plan':<30} {'Beds':>4} {'Baths':>5} {'Sqft':>6} {'Price':>8}  Avail")
    print("-" * 65)
    for p in plans:
        sqft = str(int(p.size_sqft)) if p.size_sqft else "—"
        lo = p.min_price; hi = p.max_price
        price = (f"${lo:,.0f}–${hi:,.0f}" if lo and hi and lo != hi else f"${lo:,.0f}" if lo else "—")
        avail = p.availability or "Now"
        print(f"{(p.name or ''):<30} {p.bedrooms or 0:>4} {p.bathrooms or 0:>5} {sqft:>6} {price:>8}  {avail}")

    print(f"\nTotal plans: {len(plans)}")
    if result.current_special:
        print(f"Special: {result.current_special}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--clear-cache", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.url, args.clear_cache))
