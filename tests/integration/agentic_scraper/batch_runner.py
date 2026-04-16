"""Batch runner: scrape 10 Bay Area apartments and print a comparison table.

Usage:
    python -m tests.integration.agentic_scraper.batch_runner
  or:
    cd /Users/chenximin/AptTrack
    python tests/integration/agentic_scraper/batch_runner.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")
# Ensure the package root is on the path for relative imports to work
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tests.integration.agentic_scraper.agent import ApartmentAgent, ScrapeMetrics
from tests.integration.agentic_scraper.models import ApartmentData

APARTMENTS = [
    ("Miro",             "https://www.rentmiro.com/floorplans"),
    ("The Ryden",        "https://www.theryden.com/floorplans"),
    ("Astella SF",       "https://astellaapts.com/floor-plans/"),
    ("Duboce SF",        "https://duboce.com/floorplans/"),
    ("Atlas Oakland",    "https://www.atlasoakland.com/floorplans"),
    ("Orion Oakland",    "https://orionoakland.com/floorplans/"),
    ("The Tolman",       "https://thetolmanapts.com/floorplans/"),
    ("The Asher",        "https://www.theasherfremont.com/floorplans"),
    ("The Marc PA",      "https://www.themarc-pa.com/apartments/ca/palo-alto/floor-plans"),
    ("Legacy Hayward",   "https://legacyhayward.com/floorplans/"),
]

@dataclass
class ScrapeResult:
    name: str
    url: str
    data: Optional[ApartmentData] = None
    metrics: Optional[ScrapeMetrics] = None
    error: Optional[str] = None


async def scrape_one(name: str, url: str, api_key: str, sem: asyncio.Semaphore) -> ScrapeResult:
    async with sem:
        print(f"  → Starting: {name}")
        try:
            agent = ApartmentAgent(api_key=api_key)
            data, metrics = await agent.scrape(url, headless=True)
            plans = len(data.floor_plans) if data else 0
            print(
                f"  ✓ Done:     {name:<20}  {plans:>3} plans  "
                f"{metrics.iterations:>2} iter  "
                f"{metrics.total_tokens:>7,} tok  "
                f"${metrics.total_cost_usd:.4f}"
            )
            return ScrapeResult(name=name, url=url, data=data, metrics=metrics)
        except Exception as exc:
            print(f"  ✗ Error:    {name}  {exc}")
            return ScrapeResult(name=name, url=url, error=traceback.format_exc())


def print_table(results: List[ScrapeResult]):
    print("\n" + "=" * 90)
    print(f"{'COMPLEX':<20} {'PLAN':<22} {'BED':>4} {'SQFT':>6} {'MIN $':>8} {'MAX $':>8}  AVAIL")
    print("=" * 90)
    for r in results:
        if r.error:
            print(f"{'[ERROR]':<20} {r.name:<22}  {r.error.splitlines()[-1][:50]}")
            continue
        if r.data is None:
            print(f"{'[NONE]':<20} {r.name:<22}  no result returned")
            continue
        plans = r.data.floor_plans
        if not plans:
            print(f"{r.data.name[:20]:<20} {'(no plans found)':<22}")
            continue
        for i, p in enumerate(plans):
            cname = r.data.name[:20] if i == 0 else ""
            bed_str  = str(int(p.bedrooms)) if p.bedrooms is not None else "-"
            sqft_str = f"{int(p.size_sqft):,}" if p.size_sqft else "-"
            min_str  = f"${p.min_price:,.0f}" if p.min_price else "-"
            max_str  = f"${p.max_price:,.0f}" if p.max_price else "-"
            avail    = (p.availability or "")[:20]
            print(f"{cname:<20} {p.name[:22]:<22} {bed_str:>4} {sqft_str:>6} {min_str:>8} {max_str:>8}  {avail}")
    print("=" * 90)


async def main():
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY not set"); sys.exit(1)

    print(f"Scraping {len(APARTMENTS)} Bay Area apartments (max 6 concurrent)…\n")
    sem = asyncio.Semaphore(6)  # 6 concurrent — bottleneck is LLM API latency, not local CPU
    tasks = [scrape_one(name, url, api_key, sem) for name, url in APARTMENTS]
    results = await asyncio.gather(*tasks)

    print_table(list(results))

    # Save raw JSON
    out_path = Path(__file__).parent / "batch_results.json"
    raw = []
    for r in results:
        raw.append({
            "complex": r.name,
            "url": r.url,
            "data": r.data.model_dump() if r.data else None,
            "error": r.error,
        })
    out_path.write_text(json.dumps(raw, indent=2))
    print(f"\nFull results saved → {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
