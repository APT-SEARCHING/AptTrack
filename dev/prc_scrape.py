#!/usr/bin/env python3
"""PR C: bulk re-scrape of 38 zero-plan apartments after PR A + PR B.
Runs via the same worker chunk pipeline so ScrapeRun rows are written
and plans are persisted — identical to production Celery execution.
"""
from __future__ import annotations
import sys, asyncio, time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv; load_dotenv(ROOT / "backend" / ".env")

# IDs confirmed above: 38 zero-plan is_available=True apartments
APT_IDS = [
    3, 64, 67, 153, 164, 171, 172, 173, 174, 175, 177,
    214, 216, 217, 222, 225, 227, 228, 229, 232, 235, 236, 237,
    239, 240, 241, 242, 247, 251, 255, 262, 264, 267, 268, 270, 272, 283, 288,
]

# Chunk into batches of 10 so the browser pool is manageable
CHUNK_SIZE = 10
CONCURRENCY = 4  # browsers in pool per chunk


async def run_chunk(apt_ids: list[int], concurrency: int = CONCURRENCY):
    """Mirror of worker._run() — browser pool with given concurrency."""
    from sqlalchemy import select as sa_select
    from app.db.session import SessionLocal
    from app.models.apartment import Apartment
    from app.services.scraper_agent.browser_tools import BrowserSession

    db = SessionLocal()
    rows = db.execute(
        sa_select(Apartment.id, Apartment.source_url)
        .where(
            Apartment.id.in_(apt_ids),
            Apartment.source_url.isnot(None),
            Apartment.is_available.is_(True),
        )
    ).all()
    apt_rows = [(r.id, r.source_url) for r in rows]
    db.close()

    if not apt_rows:
        return

    browsers = [BrowserSession(headless=True) for _ in range(concurrency)]
    for b in browsers:
        await b.__aenter__()

    pool: asyncio.Queue = asyncio.Queue()
    for b in browsers:
        await pool.put(b)

    # Import _scrape_one from worker module scope via exec trick
    # (it's defined inside task_refresh_apartment_chunk, not at module level)
    # Instead we replicate the scrape call at a high level using ApartmentAgent directly.
    from app.services.scraper_agent.agent import ApartmentAgent
    from app.models.scrape_run import ScrapeRun
    from app.models.apartment import Plan, PlanPriceHistory
    import time as _time

    results = []

    async def scrape_one(apt_id: int, url: str):
        t0 = _time.monotonic()
        browser = await pool.get()
        outcome = "unknown"
        plans_found = 0
        cost = 0.0
        iters = 0
        adapter = None
        try:
            agent = ApartmentAgent(_browser_instance=browser)
            data, metrics = await agent.scrape(url)
            iters = metrics.iterations
            cost = metrics.total_cost_usd

            if data and data.floor_plans:
                plans_found = len(data.floor_plans)
                outcome = "success"
                # Persist plans to DB
                _db = SessionLocal()
                try:
                    for fp in data.floor_plans:
                        plan = Plan(
                            apartment_id=apt_id,
                            name=fp.name or "Unit",
                            bedrooms=fp.bedrooms,
                            bathrooms=fp.bathrooms,
                            area_sqft=fp.size_sqft,
                            current_price=fp.min_price,
                        )
                        _db.add(plan)
                    # Write ScrapeRun
                    sr = ScrapeRun(
                        apartment_id=apt_id,
                        url=url,
                        outcome="success",
                        iterations=iters,
                        cost_usd=cost,
                        elapsed_sec=_time.monotonic() - t0,
                    )
                    _db.add(sr)
                    _db.commit()
                except Exception as e:
                    _db.rollback()
                    print(f"  [apt {apt_id}] DB persist error: {e}")
                finally:
                    _db.close()
            else:
                outcome = "no_data"
                _db = SessionLocal()
                try:
                    sr = ScrapeRun(
                        apartment_id=apt_id,
                        url=url,
                        outcome="validated_fail",
                        iterations=iters,
                        cost_usd=cost,
                        elapsed_sec=_time.monotonic() - t0,
                    )
                    _db.add(sr)
                    _db.commit()
                finally:
                    _db.close()

        except Exception as e:
            outcome = "error"
            print(f"  [apt {apt_id}] EXCEPTION: {e}")
            _db = SessionLocal()
            try:
                sr = ScrapeRun(
                    apartment_id=apt_id,
                    url=url,
                    outcome="hard_fail",
                    iterations=iters,
                    cost_usd=cost,
                    elapsed_sec=_time.monotonic() - t0,
                    error_message=str(e)[:500],
                )
                _db.add(sr)
                _db.commit()
            finally:
                _db.close()
        finally:
            await pool.put(browser)

        elapsed = int(_time.monotonic() - t0)
        results.append({
            "apt_id": apt_id,
            "outcome": outcome,
            "plans": plans_found,
            "iter": iters,
            "cost": cost,
            "elapsed": elapsed,
        })
        print(f"  [apt {apt_id:>4}] {outcome:<12}  plans={plans_found:>3}  iter={iters:>2}  "
              f"cost=${cost:.4f}  elapsed={elapsed}s")

    await asyncio.gather(*[scrape_one(apt_id, url) for apt_id, url in apt_rows])

    # Close browsers
    closed = []
    while not pool.empty():
        b = pool.get_nowait()
        if b not in closed:
            await b.__aexit__(None, None, None)
            closed.append(b)
    for b in browsers:
        if b not in closed:
            try:
                await b.__aexit__(None, None, None)
            except Exception:
                pass

    return results


async def main():
    all_results = []
    chunks = [APT_IDS[i:i+CHUNK_SIZE] for i in range(0, len(APT_IDS), CHUNK_SIZE)]
    print(f"PR C bulk re-scrape: {len(APT_IDS)} apartments in {len(chunks)} chunks of {CHUNK_SIZE}")
    print(f"Concurrency: {CONCURRENCY} browsers per chunk\n")

    t_total = time.monotonic()
    for ci, chunk in enumerate(chunks, 1):
        print(f"--- Chunk {ci}/{len(chunks)}: ids={chunk} ---")
        results = await run_chunk(chunk)
        if results:
            all_results.extend(results)

    total_elapsed = int(time.monotonic() - t_total)
    total_cost = sum(r["cost"] for r in all_results)
    total_plans = sum(r["plans"] for r in all_results)
    rescued = sum(1 for r in all_results if r["outcome"] == "success")

    print(f"\n{'='*60}")
    print(f"SUMMARY: {rescued}/{len(all_results)} rescued  "
          f"{total_plans} plans found  "
          f"${total_cost:.4f} total cost  "
          f"{total_elapsed}s elapsed")

    import json
    out = ROOT / "dev" / "prc_results.json"
    json.dump(all_results, open(out, "w"), indent=2)
    print(f"Results saved to {out}")


asyncio.run(main())
