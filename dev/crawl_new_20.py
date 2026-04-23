#!/usr/bin/env python3
"""Pick 20 new market-rate apartments from bay_area_discovered.json, seed them,
run two scrape passes (pass-1 = fresh, pass-2 = cache replay), and print a
side-by-side coverage report.

Usage:
    python dev/crawl_new_20.py               # random 20, live scrape
    python dev/crawl_new_20.py --dry-run     # print selected 20, no scrape
    python dev/crawl_new_20.py --seed N      # fix random seed for reproducibility
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from textwrap import shorten
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.models.apartment import Apartment, Plan, PlanPriceHistory
from app.models.user import User
from app.db.base_class import Base
import app.db.base  # noqa: registers all models

from tests.integration.agentic_scraper.agent import ApartmentAgent

DISCOVERED_FILE = ROOT / "dev" / "bay_area_discovered.json"
RESULTS_FILE    = ROOT / "dev" / "crawl_new_20_results.json"

# ---------------------------------------------------------------------------
# Exclusion heuristics — same logic as audit filtering
# ---------------------------------------------------------------------------
EXCLUDE_NAME = [
    "senior", "retirement", "affordable", "housing authority", "section",
    "hope house", "meda", "subsidized", "memory care", "elderly",
    "eskaton", "bishop", "silverado", "sunrise", "forum at",
    "roemc", "family apartment", "mid peninsula", "bridge housing",
    "eden housing", "chinatown", "bayside", "lytton", "mid-pen",
    "fremont village", "canyon house", "age well", "community center",
    "chaparral house",
]
EXCLUDE_URL = ["altahousing", "jsco.net", "roemcorp", "bridgehousing",
               "edenhousing", "wearecch", "bishopsf", "eskaton",
               "silverado", "moldaw", "transformingage", "fremont.gov",
               "aegisliving", "redwoodcity.org", "chaparralhouse.org",
               ".gov/", "parks-recreation"]


def _make_engine():
    url = settings.DATABASE_URL.replace("@db:", "@localhost:")
    return create_engine(url, pool_pre_ping=True)


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------

def _load_candidates(db: Session) -> list[dict]:
    existing = {r[0] for r in db.execute(text("SELECT source_url FROM apartments")).fetchall()}
    data = json.loads(DISCOVERED_FILE.read_text())
    out = []
    for a in data["apartments"]:
        url = a.get("source_url", "")
        name = a.get("title", "").lower()
        if not url:
            continue
        if url in existing:
            continue
        if any(k in name for k in EXCLUDE_NAME):
            continue
        if any(k in url.lower() for k in EXCLUDE_URL):
            continue
        rating = a.get("rating") or 0
        n_ratings = a.get("user_rating_count") or 0
        if rating < 4.0 or n_ratings < 20:
            continue
        out.append(a)
    return out


def pick_20(candidates: list[dict], seed: int | None) -> list[dict]:
    rng = random.Random(seed)
    return rng.sample(candidates, min(20, len(candidates)))


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def seed_apartment(db: Session, apt_data: dict) -> Apartment:
    """Insert apartment row without plans; return the ORM object."""
    existing = db.execute(
        select(Apartment).where(Apartment.source_url == apt_data["source_url"])
    ).scalar_one_or_none()
    if existing:
        return existing

    apt = Apartment(
        external_id=apt_data.get("external_id", apt_data["source_url"]),
        title=apt_data["title"],
        city=apt_data.get("city", ""),
        state=apt_data.get("state", "CA"),
        zipcode=apt_data.get("zipcode", "") or "",
        source_url=apt_data["source_url"],
        is_available=True,
        latitude=apt_data.get("latitude"),
        longitude=apt_data.get("longitude"),
        bedrooms=0.0,   # DB NOT NULL DEFAULT 0; updated after scrape
        bathrooms=0.0,  # DB NOT NULL DEFAULT 0; updated after scrape
    )
    db.add(apt)
    db.flush()
    return apt


# ---------------------------------------------------------------------------
# Persist scraped result (mirrors production _persist_scraped_prices logic)
# ---------------------------------------------------------------------------

def persist_result(db: Session, apt_id: int, result: Any) -> dict:
    """Write floor-plan data to DB. Returns stats dict."""
    stats = {"plans_scraped": 0, "priced": 0, "with_sqft": 0, "clean_name": 0, "skipped": 0}
    if not result or not result.floor_plans:
        return stats

    BAD_NAMES = {"unit","favorite","tour","tour now","view details","available",
                 "available now","select","share","save",""}

    for fp in result.floor_plans:
        stats["plans_scraped"] += 1

        # Match or create plan
        plan = db.execute(select(Plan).where(
            Plan.apartment_id == apt_id,
            Plan.name == fp.name,
        )).scalar_one_or_none()

        if plan is None and fp.bedrooms is not None and fp.size_sqft:
            # fuzzy match
            candidates = db.execute(select(Plan).where(
                Plan.apartment_id == apt_id,
                Plan.bedrooms == fp.bedrooms,
            )).scalars().all()
            for c in candidates:
                if c.area_sqft and abs(c.area_sqft - fp.size_sqft) / fp.size_sqft < 0.10:
                    plan = c
                    break

        if plan is None:
            if fp.bedrooms is None:
                stats["skipped"] += 1
                continue
            plan = Plan(
                apartment_id=apt_id,
                name=fp.name or "Unit",
                bedrooms=fp.bedrooms,
                bathrooms=fp.bathrooms or 1.0,
                area_sqft=fp.size_sqft or 0.0,
                is_available=True,
            )
            db.add(plan)
            db.flush()

        # Backfill fields (B1 logic)
        if fp.size_sqft and (not plan.area_sqft or abs((plan.area_sqft or 0) - fp.size_sqft) > 10):
            plan.area_sqft = fp.size_sqft
        if fp.bedrooms is not None:
            plan.bedrooms = fp.bedrooms
        if fp.bathrooms is not None:
            plan.bathrooms = fp.bathrooms
        if fp.name and plan.name in (None, "", "Unit"):
            plan.name = fp.name
        if fp.min_price:
            plan.current_price = fp.min_price
        if fp.external_url:
            plan.external_url = fp.external_url

        if fp.min_price:
            db.add(PlanPriceHistory(plan_id=plan.id, price=fp.min_price,
                                    recorded_at=datetime.now(timezone.utc)))
            stats["priced"] += 1
        if plan.area_sqft and plan.area_sqft > 0:
            stats["with_sqft"] += 1
        if plan.name and plan.name.lower() not in BAD_NAMES:
            stats["clean_name"] += 1

    db.commit()
    return stats


# ---------------------------------------------------------------------------
# Coverage report
# ---------------------------------------------------------------------------

def _coverage_row(apt: Apartment, db: Session) -> dict:
    plans = db.execute(select(Plan).where(Plan.apartment_id == apt.id)).scalars().all()
    if not plans:
        return {"title": apt.title, "city": apt.city, "n_plans": 0,
                "priced": 0, "with_sqft": 0, "clean_name": 0}
    BAD = {"unit","favorite","tour","tour now","view details","available",
           "available now","select","share","save",""}
    return {
        "title": apt.title,
        "city": apt.city,
        "n_plans": len(plans),
        "priced": sum(1 for p in plans if p.current_price),
        "with_sqft": sum(1 for p in plans if p.area_sqft and p.area_sqft > 0),
        "clean_name": sum(1 for p in plans if p.name and p.name.lower() not in BAD),
    }


def print_coverage_table(rows: list[dict], label: str) -> None:
    print(f"\n{'='*72}", flush=True)
    print(f"  {label}", flush=True)
    print(f"{'='*72}", flush=True)
    hdr = f"  {'Apartment':<35} {'City':<14} {'plans':>5} {'priced':>6} {'sqft':>5} {'name':>5}"
    print(hdr)
    print("  " + "-"*68)
    for r in rows:
        title = shorten(r["title"], 34)
        n = r["n_plans"]
        pct = lambda x: f"{x}/{n}" if n else "-"
        print(f"  {title:<35} {r['city']:<14} {n:>5} {pct(r['priced']):>6} {pct(r['with_sqft']):>5} {pct(r['clean_name']):>5}")
    print("  " + "-"*68)
    totals = {
        "n_plans": sum(r["n_plans"] for r in rows),
        "priced": sum(r["priced"] for r in rows),
        "with_sqft": sum(r["with_sqft"] for r in rows),
        "clean_name": sum(r["clean_name"] for r in rows),
    }
    n = totals["n_plans"]
    pct = lambda x: f"{x}/{n} ({100*x//n if n else 0}%)"
    print(f"  {'TOTAL':<35} {'':<14} {n:>5} {pct(totals['priced']):>6} {pct(totals['with_sqft']):>5} {pct(totals['clean_name']):>5}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SCRAPE_TIMEOUT_SEC = 300  # 5-min hard cap per site


async def _scrape(url: str, title: str, pass_label: str) -> Any:
    api_key = settings.MINIMAX_API_KEY
    print(f"  [{pass_label}] Scraping {title[:50]}…", flush=True)
    t0 = time.time()
    try:
        agent = ApartmentAgent(api_key=api_key)
        data, metrics = await asyncio.wait_for(
            agent.scrape(url), timeout=SCRAPE_TIMEOUT_SEC
        )
        elapsed = time.time() - t0
        n = len(data.floor_plans) if data and data.floor_plans else 0
        cache = " (cache)" if metrics.cache_hit else ""
        print(f"         → {n} plans, {elapsed:.0f}s{cache}, "
              f"cost=${metrics.total_cost_usd:.4f}, iters={metrics.iterations}", flush=True)
        return data
    except asyncio.TimeoutError:
        elapsed = time.time() - t0
        print(f"         → TIMEOUT after {elapsed:.0f}s — skipping", flush=True)
        return None
    except Exception as exc:
        elapsed = time.time() - t0
        print(f"         → FAILED ({elapsed:.0f}s): {exc}", flush=True)
        return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    engine = _make_engine()
    db = Session(bind=engine)

    # 1. Select 20 apartments
    candidates = _load_candidates(db)
    selected = pick_20(candidates, args.seed)
    print(f"Selected {len(selected)} apartments (seed={args.seed}, pool={len(candidates)}):\n")
    for i, a in enumerate(selected, 1):
        print(f"  {i:2}. [{a.get('rating',0)} ★ {a.get('user_rating_count',0):4}] "
              f"{a.get('city',''):<15} {a['title'][:45]}")

    if args.dry_run:
        print("\n--dry-run: stopping before scrape.")
        db.close()
        return

    # 2. Seed apartments into DB
    print("\n--- Seeding apartments ---")
    apt_ids = []
    for a in selected:
        apt = seed_apartment(db, a)
        apt_ids.append(apt.id)
        print(f"  apt_id={apt.id}  {apt.title}", flush=True)
    db.commit()

    # 3. Pass 1 — fresh scrape (no cache)
    print("\n--- Pass 1: fresh scrape ---")
    pass1_results = {}
    for a in selected:
        result = await _scrape(a["source_url"], a["title"], "P1")
        pass1_results[a["source_url"]] = result

    # Persist pass-1
    db2 = Session(bind=engine)
    for a, apt_id in zip(selected, apt_ids):
        result = pass1_results[a["source_url"]]
        if result:
            persist_result(db2, apt_id, result)
    db2.close()

    # Coverage after pass 1
    db3 = Session(bind=engine)
    apts = [db3.execute(select(Apartment).where(Apartment.id == aid)).scalar_one() for aid in apt_ids]
    pass1_coverage = [_coverage_row(apt, db3) for apt in apts]
    db3.close()

    print_coverage_table(pass1_coverage, "Pass 1 coverage (fresh scrape)")

    # 4. Pass 2 — cache replay
    print("\n--- Pass 2: cache replay ---")
    pass2_results = {}
    for a in selected:
        result = await _scrape(a["source_url"], a["title"], "P2")
        pass2_results[a["source_url"]] = result

    # Persist pass-2 (merges/updates)
    db4 = Session(bind=engine)
    for a, apt_id in zip(selected, apt_ids):
        result = pass2_results[a["source_url"]]
        if result:
            persist_result(db4, apt_id, result)
    db4.close()

    # Coverage after pass 2
    db5 = Session(bind=engine)
    apts2 = [db5.execute(select(Apartment).where(Apartment.id == aid)).scalar_one() for aid in apt_ids]
    pass2_coverage = [_coverage_row(apt, db5) for apt in apts2]
    db5.close()

    print_coverage_table(pass2_coverage, "Pass 2 coverage (cache replay)")

    # 5. Delta summary
    print(f"\n{'='*72}")
    print("  Delta: Pass 2 vs Pass 1")
    print(f"{'='*72}")
    for r1, r2 in zip(pass1_coverage, pass2_coverage):
        delta_sqft = r2["with_sqft"] - r1["with_sqft"]
        delta_priced = r2["priced"] - r1["priced"]
        if delta_sqft or delta_priced or r1["n_plans"] != r2["n_plans"]:
            title = shorten(r1["title"], 34)
            print(f"  {title:<35} plans Δ{r2['n_plans']-r1['n_plans']:+d}  "
                  f"priced Δ{delta_priced:+d}  sqft Δ{delta_sqft:+d}")

    # Save JSON snapshot
    snapshot = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "selected": [{"title": a["title"], "city": a["city"], "url": a["source_url"]} for a in selected],
        "pass1": pass1_coverage,
        "pass2": pass2_coverage,
    }
    RESULTS_FILE.write_text(json.dumps(snapshot, indent=2, default=str))
    print(f"\nResults saved → {RESULTS_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
