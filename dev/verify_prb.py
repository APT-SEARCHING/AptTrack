#!/usr/bin/env python3
"""PR B regression verification: re-scrape 4 known-good apartments and compare outcomes."""
from __future__ import annotations
import asyncio, sys, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv; load_dotenv(ROOT / "backend" / ".env")

from app.db.session import SessionLocal
from app.models.apartment import Apartment
from sqlalchemy import select

BASELINE = {
    12:  {"plans": 47, "iter": 17, "outcome": "success"},
    41:  {"plans": 35, "iter": 14, "outcome": "success"},
    166: {"plans": 4,  "iter": 23, "outcome": "success"},
    176: {"plans": 7,  "iter": 10, "outcome": "success"},
}

APT_IDS = [12, 41, 166, 176]


async def scrape_one(apt_id: int, url: str, browser) -> dict:
    from app.services.scraper_agent.agent import ApartmentAgent

    result = {"apt_id": apt_id, "url": url, "outcome": "unknown", "plans": 0, "iter": 0, "cost": 0.0}
    try:
        agent = ApartmentAgent(_browser_instance=browser)
        data, metrics = await agent.scrape(url)
        plans_count = len(data.floor_plans) if data and data.floor_plans else 0
        result["outcome"] = "success" if plans_count > 0 else "no_data"
        result["plans"] = plans_count
        result["iter"] = metrics.iterations
        result["cost"] = metrics.total_cost_usd
    except Exception as e:
        result["outcome"] = f"error"
        print(f"  [apt {apt_id}] ERROR: {e}")
    return result


async def main():
    from app.services.scraper_agent.browser_tools import BrowserSession

    db = SessionLocal()
    rows = db.execute(
        select(Apartment.id, Apartment.source_url, Apartment.title)
        .where(Apartment.id.in_(APT_IDS))
    ).all()
    db.close()

    apt_rows = [(r.id, r.source_url, r.title) for r in rows]
    print(f"Scraping {len(apt_rows)} apartments to verify PR B:")
    for apt_id, url, title in apt_rows:
        b = BASELINE.get(apt_id, {})
        print(f"  id={apt_id}: {title!r}  (baseline: {b.get('plans')} plans, {b.get('iter')} iter)")
    print()

    # Scrape sequentially to avoid browser pool complexity in a one-off script
    results = []
    for apt_id, url, title in apt_rows:
        print(f"[{apt_id}] scraping {url} ...")
        t0 = time.monotonic()
        async with BrowserSession(headless=True) as browser:
            r = await scrape_one(apt_id, url, browser)
        elapsed = int(time.monotonic() - t0)
        r["elapsed"] = elapsed
        results.append(r)
        print(f"  → outcome={r['outcome']}  plans={r['plans']}  iter={r['iter']}  cost=${r['cost']:.4f}  elapsed={elapsed}s")

    # Comparison table
    print("\n" + "="*95)
    print(f"{'apt':>4}  {'title':<30}  {'before_out':>10}  {'after_out':>10}  {'plans_b':>7}  {'plans_a':>7}  {'iter_b':>6}  {'iter_a':>6}  verdict")
    print("-"*95)

    title_map = {r.id: r.title for r in rows}
    verdicts = []

    for r in results:
        apt_id = r["apt_id"]
        base = BASELINE.get(apt_id, {})
        b_plans = base.get("plans", 0)
        b_iter  = base.get("iter", 0)
        b_out   = base.get("outcome", "?")
        a_plans = r["plans"]
        a_iter  = r["iter"]
        a_out   = r["outcome"]
        title   = title_map.get(apt_id, "?")[:28]

        if a_out not in ("success",):
            verdict = "RED"
        elif a_plans < b_plans * 0.8:
            verdict = "RED"
        elif a_iter > b_iter * 1.5:
            verdict = "YELLOW"
        else:
            verdict = "GREEN"

        verdicts.append(verdict)
        print(f"{apt_id:>4}  {title:<30}  {b_out:>10}  {a_out:>10}  {b_plans:>7}  {a_plans:>7}  {b_iter:>6}  {a_iter:>6}  {verdict}")

    print("="*95)

    if "RED" in verdicts:
        print("\nOVERALL: RED — stop, diagnose PR B before proceeding to bulk re-scrape")
    elif "YELLOW" in verdicts:
        print("\nOVERALL: YELLOW — mostly good; review high-iter apartments before proceeding")
    else:
        print("\nOVERALL: GREEN — safe to proceed to PR C bulk re-scrape")


asyncio.run(main())
