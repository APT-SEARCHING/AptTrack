"""
One-shot script: geocode all apartments that have an address but no lat/lng.
Uses Google Maps Geocoding API.
"""
import asyncio
import os
import sys
import aiohttp
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://apttrack:apttrack@localhost:5432/apttrack")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "AIzaSyDHEi0JcSjGNuDt5xwyYEl_5f1TkIjvlns")

engine = create_engine(DATABASE_URL)


async def geocode_address(session: aiohttp.ClientSession, address: str) -> tuple[float, float] | None:
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_MAPS_API_KEY}
    try:
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            if data.get("status") == "OK" and data.get("results"):
                loc = data["results"][0]["geometry"]["location"]
                return loc["lat"], loc["lng"]
    except Exception as e:
        print(f"  Error geocoding '{address}': {e}")
    return None


async def main():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, title, address, city, state FROM apartments "
            "WHERE (latitude IS NULL OR longitude IS NULL) AND address IS NOT NULL"
        )).fetchall()

    print(f"Found {len(rows)} apartments to geocode")

    async with aiohttp.ClientSession() as session:
        sem = asyncio.Semaphore(5)

        async def process(row):
            apt_id, title, address, city, state = row
            full_address = f"{address}" if city in address else f"{address}, {city}, {state}"
            async with sem:
                coords = await geocode_address(session, full_address)
            if coords:
                lat, lng = coords
                with engine.connect() as conn:
                    conn.execute(text(
                        "UPDATE apartments SET latitude=:lat, longitude=:lng WHERE id=:id"
                    ), {"lat": lat, "lng": lng, "id": apt_id})
                    conn.commit()
                print(f"  ✓ {title}: {lat:.4f}, {lng:.4f}")
            else:
                print(f"  ✗ {title}: no result")

        await asyncio.gather(*[process(r) for r in rows])

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
