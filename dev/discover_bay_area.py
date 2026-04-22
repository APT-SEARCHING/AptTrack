#!/usr/bin/env python3
"""Discover Bay Area apartments via Google Maps Places API.

Searches 17 cities (Major + Mid + selected Secondary), deduplicates by
place_id, and writes results to dev/bay_area_discovered.json for review
before committing to scraping.

Usage:
    python dev/discover_bay_area.py              # discover + save JSON
    python dev/discover_bay_area.py --dry-run    # cost estimate only, no API calls
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.core.config import settings
from app.services.google_maps import GoogleMapsService

# ---------------------------------------------------------------------------
# Target cities — Major + Mid + selected Secondary
# ---------------------------------------------------------------------------
CITIES = [
    # Major (5)
    "San Francisco, CA",
    "San Jose, CA",
    "Oakland, CA",
    "Fremont, CA",
    "Hayward, CA",
    # Mid (7)
    "Sunnyvale, CA",
    "Santa Clara, CA",
    "Mountain View, CA",
    "Palo Alto, CA",
    "Milpitas, CA",
    "Berkeley, CA",
    "San Mateo, CA",
    # Selected Secondary (5)
    "Newark, CA",
    "Emeryville, CA",
    "Daly City, CA",
    "Redwood City, CA",
    "South San Francisco, CA",
]

# Cost constants (Google Places API New, Essentials tier)
_SEARCH_COST = 0.003   # per Text Search request
_QUERIES_PER_CITY = 2  # "apartment complex", "affordable housing"


async def discover_city(svc: GoogleMapsService, city: str) -> tuple[dict, str | None]:
    result, error = await svc.fetch_apartments_by_location(city)
    return result, error


async def main(dry_run: bool) -> None:
    estimated_api_calls = len(CITIES) * _QUERIES_PER_CITY
    estimated_cost = estimated_api_calls * _SEARCH_COST

    print(f"\n{'='*60}")
    print(f"Bay Area Apartment Discovery")
    print(f"{'='*60}")
    print(f"Cities      : {len(CITIES)}")
    print(f"Est. API calls: {estimated_api_calls}")
    print(f"Est. cost   : ${estimated_cost:.3f}")
    print(f"{'='*60}\n")

    if dry_run:
        print("DRY RUN — no API calls made.")
        print("\nCities to be searched:")
        for city in CITIES:
            print(f"  {city}")
        return

    if not settings.GOOGLE_MAPS_API_KEY:
        print("ERROR: GOOGLE_MAPS_API_KEY not set in .env")
        sys.exit(1)

    svc = GoogleMapsService(api_key=settings.GOOGLE_MAPS_API_KEY)
    all_places: dict[str, dict] = {}  # keyed by place_id, deduplicated
    city_counts: dict[str, int] = {}
    errors: list[str] = []
    total_cost = 0.0

    for i, city in enumerate(CITIES, 1):
        print(f"[{i:2d}/{len(CITIES)}] {city} ...", end=" ", flush=True)
        places, error = await discover_city(svc, city)

        if error and not places:
            print(f"ERROR: {error}")
            errors.append(f"{city}: {error}")
            city_counts[city] = 0
            continue

        new = 0
        for place_id, place in places.items():
            if place_id not in all_places:
                all_places[place_id] = {**place, "_city": city}
                new += 1

        city_counts[city] = len(places)
        city_cost = _QUERIES_PER_CITY * _SEARCH_COST
        total_cost += city_cost
        print(f"{len(places):3d} found  ({new} new after dedup)  ${city_cost:.3f}")

    # Summary
    print(f"\n{'='*60}")
    print(f"TOTAL UNIQUE APARTMENTS: {len(all_places)}")
    print(f"TOTAL API COST         : ${total_cost:.3f}")
    print(f"{'='*60}")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")

    # Save results
    out = ROOT / "dev" / "bay_area_discovered.json"
    out.write_text(json.dumps({
        "total": len(all_places),
        "cost_usd": round(total_cost, 4),
        "city_counts": city_counts,
        "apartments": list(all_places.values()),
    }, indent=2, ensure_ascii=False))
    print(f"\nSaved {len(all_places)} apartments → {out}")
    print("\nNext step: review dev/bay_area_discovered.json then run seed_apartments.py")

    # Print top cities by count
    print("\nTop cities by apartment count:")
    for city, count in sorted(city_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {count:3d}  {city}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Estimate cost only, no API calls")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
