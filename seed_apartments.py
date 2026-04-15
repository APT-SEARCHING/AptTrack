"""Seed the database with real apartment data from the agentic scraper.

Scrapes the 10 Bay Area apartments defined below, then writes Apartment +
Plan + PlanPriceHistory rows to the local Postgres database.

Usage:
    python seed_apartments.py              # scrape all
    python seed_apartments.py --dry-run   # scrape but don't write to DB
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

import os

from tests.integration.agentic_scraper.agent import ApartmentAgent
from tests.integration.agentic_scraper.models import ApartmentData, FloorPlan

# ── apartment list ─────────────────────────────────────────────────────────────
APARTMENTS = [
    ("Miro",          "https://www.rentmiro.com/floorplans",                              "San Jose",  "CA", "95110"),
    ("The Ryden",     "https://www.theryden.com/floorplans",                              "San Jose",  "CA", "95128"),
    ("Astella SF",    "https://astellaapts.com/floor-plans/",                             "San Francisco", "CA", "94103"),
    ("Duboce SF",     "https://duboce.com/floorplans/",                                   "San Francisco", "CA", "94117"),
    ("Atlas Oakland", "https://www.atlasoakland.com/floorplans",                          "Oakland",   "CA", "94612"),
    ("Orion Oakland", "https://orionoakland.com/floorplans/",                             "Oakland",   "CA", "94607"),
    ("The Tolman",    "https://thetolmanapts.com/floorplans/",                            "Oakland",   "CA", "94612"),
    ("The Asher",     "https://www.theasherfremont.com/floorplans",                       "Fremont",   "CA", "94538"),
    ("The Marc PA",   "https://www.themarc-pa.com/apartments/ca/palo-alto/floor-plans",   "Palo Alto", "CA", "94301"),
    ("Legacy Hayward","https://legacyhayward.com/floorplans/",                            "Hayward",   "CA", "94541"),
]


# ── helpers ────────────────────────────────────────────────────────────────────

def _slug(url: str) -> str:
    """Derive a stable external_id from a URL."""
    host = re.sub(r"^www\.", "", url.split("//")[-1].split("/")[0])
    return f"scraper_{host}"


def _is_available(fp: FloorPlan) -> bool:
    av = (fp.availability or "").lower()
    return "waitlist" not in av and "unavailable" not in av


def _save_apartment(apt_data: ApartmentData, url: str, city: str, state: str,
                    zipcode: str, db) -> None:
    """Upsert one Apartment + its Plans + PlanPriceHistory rows."""
    from app.models.apartment import Apartment, Plan, PlanPriceHistory

    external_id = _slug(url)
    now = datetime.now(timezone.utc)

    # Cheapest available plan → apartment-level price
    prices = [fp.min_price for fp in apt_data.floor_plans
              if fp.min_price and _is_available(fp)]
    current_price = min(prices) if prices else None

    # Representative bedroom count for the Apartment row (minimum available)
    beds = [fp.bedrooms for fp in apt_data.floor_plans
            if fp.bedrooms is not None and _is_available(fp)]
    apt_beds = min(beds) if beds else 1.0
    baths = [fp.bathrooms for fp in apt_data.floor_plans
             if fp.bathrooms is not None]
    apt_baths = min(baths) if baths else 1.0

    # Upsert apartment
    apt = db.query(Apartment).filter(Apartment.external_id == external_id).first()
    if apt is None:
        apt = Apartment(
            external_id=external_id,
            title=apt_data.name,
            address=apt_data.address or "",
            city=city,
            state=state,
            zipcode=zipcode,
            property_type="apartment",
            bedrooms=apt_beds,
            bathrooms=apt_baths,
            source_url=url,
            phone=apt_data.phone,
            current_price=current_price,
            is_available=bool(prices),
        )
        db.add(apt)
        db.flush()  # get apt.id
        print(f"  + Created apartment: {apt_data.name}")
    else:
        apt.title = apt_data.name
        apt.current_price = current_price
        apt.updated_at = now
        print(f"  ~ Updated apartment: {apt_data.name}")

    # Upsert plans
    for fp in apt_data.floor_plans:
        if fp.min_price is None:
            continue
        plan = (db.query(Plan)
                .filter(Plan.apartment_id == apt.id, Plan.name == fp.name)
                .first())
        if plan is None:
            plan = Plan(
                apartment_id=apt.id,
                name=fp.name,
                bedrooms=fp.bedrooms or 0,
                bathrooms=fp.bathrooms or 1,
                area_sqft=fp.size_sqft,
                price=fp.min_price,
                is_available=_is_available(fp),
            )
            db.add(plan)
            db.flush()
        else:
            plan.price = fp.min_price
            plan.is_available = _is_available(fp)
            plan.area_sqft = fp.size_sqft or plan.area_sqft

        # Always append a price-history snapshot
        db.add(PlanPriceHistory(
            plan_id=plan.id,
            price=fp.min_price,
            recorded_at=now,
        ))

    db.commit()


# ── scraper loop ───────────────────────────────────────────────────────────────

async def scrape_all(dry_run: bool) -> None:
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if not api_key:
        print("ERROR: MINIMAX_API_KEY not set in .env"); sys.exit(1)

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set in .env"); sys.exit(1)
    # Rewrite Docker hostname → localhost when running outside Docker
    db_url = db_url.replace("@db:", "@localhost:")

    if not dry_run:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)

    sem = asyncio.Semaphore(2)  # 2 concurrent to be polite

    async def scrape_one(name, url, city, state, zipcode):
        async with sem:
            print(f"\n[{name}] Scraping {url} …")
            try:
                agent = ApartmentAgent(api_key=api_key)
                data, metrics = await agent.scrape(url, headless=True)
                if data is None:
                    print(f"  ! No data returned for {name}")
                    return
                print(
                    f"  ✓ {len(data.floor_plans)} floor plans  "
                    f"{metrics.total_tokens:,} tok  ${metrics.total_cost_usd:.4f}"
                )
                if dry_run:
                    for fp in data.floor_plans:
                        print(f"    {fp.name:30s} beds={fp.bedrooms} ${fp.min_price}")
                else:
                    db = Session()
                    try:
                        _save_apartment(data, url, city, state, zipcode, db)
                    finally:
                        db.close()
            except Exception as exc:
                print(f"  ✗ Error scraping {name}: {exc}")

    tasks = [scrape_one(n, u, c, s, z) for n, u, c, s, z in APARTMENTS]
    await asyncio.gather(*tasks)
    print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape but don't write to the database")
    args = parser.parse_args()
    asyncio.run(scrape_all(args.dry_run))
