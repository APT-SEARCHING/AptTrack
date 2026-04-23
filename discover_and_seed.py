"""Discover new Bay Area apartment complexes via Google Maps and scrape them.

Two-step workflow (recommended):
    python discover_and_seed.py --discover-only   # Step 1: find + save URL stubs to DB
    python discover_and_seed.py --scrape-pending  # Step 2: scrape all unscraped DB rows

Single-shot (discover + scrape in one go):
    python discover_and_seed.py              # discover + scrape + save
    python discover_and_seed.py --dry-run    # discover + scrape, no DB writes
    python discover_and_seed.py --limit 20   # cap at 20 new apartments
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
# Tests agent uses bare imports (e.g. `from browser_tools import …`)
sys.path.insert(0, str(ROOT / "tests" / "integration" / "agentic_scraper"))

import os

from tests.integration.agentic_scraper.agent import ApartmentAgent
from tests.integration.agentic_scraper.models import ApartmentData, FloorPlan

# ── Target cities ──────────────────────────────────────────────────────────────
BAY_AREA_CITIES = [
    "San Jose, CA",
    "San Francisco, CA",
    "Oakland, CA",
    "Berkeley, CA",
    "Fremont, CA",
    "Sunnyvale, CA",
    "Santa Clara, CA",
    "Mountain View, CA",
    "Palo Alto, CA",
    "San Mateo, CA",
    "Redwood City, CA",
    "Walnut Creek, CA",
]

# Domains we already have seeded (skip these during discovery)
_KNOWN_DOMAINS = {
    "rentmiro.com", "theryden.com", "astellaapts.com", "duboce.com",
    "atlasoakland.com", "orionoakland.com", "thetolmanapts.com",
    "theasherfremont.com", "themarc-pa.com", "legacyhayward.com",
}

# Aggregator domains to skip during discovery
_AGGREGATORS = {
    "apartments.com", "zillow", "trulia", "realtor.com",
    "hotpads", "rent.com", "apartmentlist", "craigslist",
}

# Hotel/hospitality chains to skip (Google Maps nearby search returns these)
_HOTEL_KEYWORDS = {
    "hyatt", "marriott", "hilton", "sheraton", "westin", "courtyard",
    "hampton inn", "holiday inn", "best western", "wyndham", "radisson",
    "doubletree", "embassy suites", "extended stay", "residence inn",
    "fairfield inn", "four points", "aloft", "element hotel",
    "kimpton", "intercontinental", "crowne plaza", "motel 6", "super 8",
}

# Affordable / income-restricted housing to skip
_AFFORDABLE_KEYWORDS = {
    "housing authority", "affordable housing", "community development corporation",
    "habitat for humanity", "section 8", "low income", "low-income",
    "income restricted", "income qualified", "% ami", "ami)",
    "housing development corporation", "housing foundation",
    "community land trust", "public housing",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _domain(url: str) -> str:
    return re.sub(r"^www\.", "", urlparse(url).netloc.lower())


def _slug(url: str) -> str:
    host = re.sub(r"^www\.", "", url.split("//")[-1].split("/")[0])
    return f"scraper_{host}"


def _is_available(fp: FloorPlan) -> bool:
    av = (fp.availability or "").lower()
    return "waitlist" not in av and "unavailable" not in av


def _db_session(db_url: str):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine(db_url)
    return sessionmaker(bind=engine)


# ── Step 1: save URL stub (no floor plans yet) ─────────────────────────────────

def _save_stub(c: dict, db) -> bool:
    """Insert a minimal Apartment row from a Google Maps candidate.

    Returns True if a new row was created, False if it already existed.
    """
    from sqlalchemy import select
    from app.models.apartment import Apartment

    external_id = _slug(c["url"])
    existing = db.execute(
        select(Apartment).where(Apartment.external_id == external_id)
    ).scalar_one_or_none()
    if existing:
        return False

    apt = Apartment(
        external_id=external_id,
        title=c["title"],
        address="",
        city=c["city"],
        state=c["state"],
        zipcode=c["zipcode"],
        property_type="apartment",
        bedrooms=1,
        bathrooms=1,
        source_url=c["url"],
        phone=c.get("phone") or None,
        current_price=None,
        is_available=False,  # marks "not yet scraped"
    )
    db.add(apt)
    db.commit()
    return True


# ── Step 2: update with full floor plan data ───────────────────────────────────

def _save_apartment(apt_data: ApartmentData, url: str, city: str, state: str,
                    zipcode: str, phone: str | None, db) -> None:
    from sqlalchemy import select
    from app.models.apartment import Apartment, Plan, PlanPriceHistory

    external_id = _slug(url)
    now = datetime.now(timezone.utc)

    prices = [fp.min_price for fp in apt_data.floor_plans
              if fp.min_price and _is_available(fp)]
    current_price = min(prices) if prices else None

    beds = [fp.bedrooms for fp in apt_data.floor_plans
            if fp.bedrooms is not None and _is_available(fp)]
    apt_beds = min(beds) if beds else 1.0
    baths = [fp.bathrooms for fp in apt_data.floor_plans if fp.bathrooms is not None]
    apt_baths = min(baths) if baths else 1.0

    apt = db.execute(
        select(Apartment).where(Apartment.external_id == external_id)
    ).scalar_one_or_none()

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
            phone=phone or apt_data.phone,
            current_price=current_price,
            is_available=bool(prices),
        )
        db.add(apt)
        db.flush()
        print(f"    + Created: {apt_data.name}")
    else:
        apt.title = apt_data.name
        apt.current_price = current_price
        apt.is_available = bool(prices)
        apt.updated_at = now
        print(f"    ~ Updated: {apt_data.name}")

    for fp in apt_data.floor_plans:
        plan = db.execute(
            select(Plan).where(Plan.apartment_id == apt.id, Plan.name == fp.name)
        ).scalar_one_or_none()
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

        if fp.min_price is not None:
            db.add(PlanPriceHistory(
                plan_id=plan.id,
                price=fp.min_price,
                recorded_at=now,
            ))

    db.commit()


# ── Discovery ──────────────────────────────────────────────────────────────────

async def discover(limit: int, existing_domains: set[str]) -> list[dict]:
    """Query Google Maps across Bay Area cities and return candidate apartments."""
    gm_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not gm_key:
        print("ERROR: GOOGLE_MAPS_API_KEY not set"); sys.exit(1)

    from app.services.google_maps import GoogleMapsService
    svc = GoogleMapsService(api_key=gm_key)

    seen_domains: set[str] = set(existing_domains)
    candidates: list[dict] = []

    print(f"Querying {len(BAY_AREA_CITIES)} cities …\n")

    for city in BAY_AREA_CITIES:
        if len(candidates) >= limit:
            break
        print(f"  [{city}]", end=" ", flush=True)
        apts, err = await svc.fetch_apartments_by_location(city)
        if err:
            print(f"error: {err}")
            continue

        new_this_city = 0
        for apt_id, apt in apts.items():
            url = apt.get("source_url", "").strip()
            if not url or not url.startswith("http"):
                continue
            dom = _domain(url)
            if dom in seen_domains:
                continue
            if any(agg in dom for agg in _AGGREGATORS):
                continue
            title_lower = apt.get("title", "").lower()
            if any(hotel in title_lower for hotel in _HOTEL_KEYWORDS):
                continue
            if any(kw in title_lower for kw in _AFFORDABLE_KEYWORDS):
                continue
            seen_domains.add(dom)
            candidates.append({
                "title": apt.get("title", apt.get("business_name", "Unknown")),
                "url": url,
                "city": apt.get("city", city.split(",")[0]),
                "state": apt.get("state", "CA"),
                "zipcode": apt.get("zipcode", ""),
                "phone": apt.get("phone", ""),
            })
            new_this_city += 1
            if len(candidates) >= limit:
                break

        print(f"{new_this_city} new  (total {len(candidates)})")
        await asyncio.sleep(0.5)  # gentle pacing between cities

    return candidates[:limit]


def _load_existing_domains(db_url: str) -> set[str]:
    """Load all source_url domains already in the DB."""
    existing: set[str] = set(_KNOWN_DOMAINS)
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(db_url)
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT source_url FROM apartments WHERE source_url IS NOT NULL")
            ).fetchall()
        for (url,) in rows:
            if url:
                existing.add(_domain(url))
        print(f"DB has {len(rows)} apartments with URLs — will skip their domains.\n")
    except Exception as e:
        print(f"Warning: could not load existing URLs from DB: {e}")
    return existing


# ── Scrape loop ────────────────────────────────────────────────────────────────

async def scrape_and_seed(candidates: list[dict], dry_run: bool, Session=None) -> None:
    minimax_key = os.environ.get("MINIMAX_API_KEY", "")
    if not minimax_key:
        print("ERROR: MINIMAX_API_KEY not set"); sys.exit(1)

    sem = asyncio.Semaphore(3)  # 3 concurrent scrapes
    results = {"ok": 0, "no_data": 0, "error": 0}

    async def scrape_one(c: dict) -> None:
        async with sem:
            print(f"\n[{c['title']}]  {c['url']}")
            try:
                agent = ApartmentAgent(api_key=minimax_key)
                data, metrics = await agent.scrape(c["url"], headless=True)
                if data is None or not data.floor_plans:
                    print(f"  ! No data  ({metrics.iterations} iter, ${metrics.total_cost_usd:.4f})")
                    results["no_data"] += 1
                    return
                print(
                    f"  ✓ {len(data.floor_plans)} plans  "
                    f"{metrics.iterations} iter  "
                    f"{metrics.total_tokens:,} tok  "
                    f"${metrics.total_cost_usd:.4f}"
                )
                if dry_run:
                    for fp in data.floor_plans[:4]:
                        p = f"${fp.min_price:,.0f}" if fp.min_price else "Contact"
                        print(f"    {fp.name:30s}  {int(fp.bedrooms or 0)}br  {p}")
                    if len(data.floor_plans) > 4:
                        print(f"    … +{len(data.floor_plans)-4} more")
                else:
                    db = Session()
                    try:
                        _save_apartment(data, c["url"], c["city"], c["state"],
                                        c["zipcode"], c["phone"], db)
                    finally:
                        db.close()
                results["ok"] += 1
            except Exception as exc:
                print(f"  ✗ Error: {exc}")
                results["error"] += 1

    await asyncio.gather(*[scrape_one(c) for c in candidates])

    print("\n" + "=" * 60)
    print(f"Done.  ✓ {results['ok']} saved  "
          f"! {results['no_data']} no data  "
          f"✗ {results['error']} errors")


# ── Step modes ─────────────────────────────────────────────────────────────────

async def run_discover_only(limit: int) -> None:
    """Step 1: discover via Google Maps and save URL stubs to DB."""
    db_url = os.environ.get("DATABASE_URL", "").replace("@db:", "@localhost:")
    existing_domains = _load_existing_domains(db_url)

    candidates = await discover(limit, existing_domains)
    if not candidates:
        print("No new candidates found."); return

    print(f"\nFound {len(candidates)} new apartments. Saving URL stubs to DB…\n")
    Session = _db_session(db_url)
    created = 0
    for c in candidates:
        db = Session()
        try:
            if _save_stub(c, db):
                print(f"  + {c['title']:<40} {c['city']:<18} {c['url'][:55]}")
                created += 1
            else:
                print(f"  ~ already exists: {c['title']}")
        finally:
            db.close()

    print(f"\n{created} new apartment stubs saved to DB.")
    print("Run with --scrape-pending to scrape floor plan data for them.")


async def run_scrape_pending(limit: int, dry_run: bool) -> None:
    """Step 2: scrape all apartments in DB that have no floor plans yet."""
    db_url = os.environ.get("DATABASE_URL", "").replace("@db:", "@localhost:")

    from sqlalchemy import create_engine, text
    engine = create_engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT a.id, a.title, a.source_url, a.city, a.state, a.zipcode, a.phone
            FROM apartments a
            LEFT JOIN plans p ON p.apartment_id = a.id
            WHERE a.source_url IS NOT NULL
              AND p.id IS NULL
            ORDER BY a.id
            LIMIT :lim
        """), {"lim": limit}).fetchall()

    if not rows:
        print("No pending apartments found (all have floor plans already)."); return

    candidates = [
        {"title": r[1], "url": r[2], "city": r[3] or "", "state": r[4] or "CA",
         "zipcode": r[5] or "", "phone": r[6] or ""}
        for r in rows
    ]

    print(f"Found {len(candidates)} apartments pending scrape:\n")
    for i, c in enumerate(candidates, 1):
        print(f"  {i:2d}. {c['title']:<40} {c['url'][:55]}")

    if dry_run:
        print("\n[--dry-run] Scraping but NOT writing to DB\n")
        Session = None
    else:
        print(f"\nScraping {len(candidates)} apartments…\n")
        Session = _db_session(db_url)

    await scrape_and_seed(candidates, dry_run, Session)


async def run_all(limit: int, dry_run: bool) -> None:
    """Original single-shot mode: discover + scrape in one go."""
    db_url = os.environ.get("DATABASE_URL", "").replace("@db:", "@localhost:")
    existing_domains = _load_existing_domains(db_url)

    candidates = await discover(limit, existing_domains)
    if not candidates:
        print("No new candidates found."); return

    print(f"\nFound {len(candidates)} new apartments to scrape:\n")
    for i, c in enumerate(candidates, 1):
        print(f"  {i:2d}. {c['title']:<35} {c['city']:<18} {c['url'][:60]}")

    Session = None
    if not dry_run:
        Session = _db_session(db_url)
        print(f"\nScraping {len(candidates)} apartments and saving to DB…\n")
    else:
        print("\n[--dry-run] Scraping but NOT writing to DB\n")

    await scrape_and_seed(candidates, dry_run, Session)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Discover Bay Area apartments via Google Maps and scrape them."
    )
    parser.add_argument("--discover-only", action="store_true",
                        help="Step 1: find via Google Maps and save URL stubs to DB (no scraping)")
    parser.add_argument("--scrape-pending", action="store_true",
                        help="Step 2: scrape all DB apartments that have no floor plans yet")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scrape but don't write to the database")
    parser.add_argument("--limit", type=int, default=50,
                        help="Max apartments to process (default 50)")
    args = parser.parse_args()

    if args.discover_only:
        asyncio.run(run_discover_only(args.limit))
    elif args.scrape_pending:
        asyncio.run(run_scrape_pending(args.limit, args.dry_run))
    else:
        asyncio.run(run_all(args.limit, args.dry_run))
