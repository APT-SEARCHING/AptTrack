#!/usr/bin/env python3
"""Insert Phase 1 Bay Area apartments (SJ, Sunnyvale, Santa Clara, MV, Palo Alto, Milpitas)
from dev/bay_area_discovered.json into Railway DB.

No Plans or PlanPriceHistory rows are created — the nightly scraper will add those.
Deduplicates against existing rows by source_url.
"""
import json
import os
import sys
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

RAILWAY_DB = "postgresql://postgres:NDrijYZDpKGoFRpaBbHhtZYsGvxmXKWJ@maglev.proxy.rlwy.net:34474/railway"
PHASE1_CITIES = {"San Jose", "Sunnyvale", "Santa Clara", "Mountain View", "Palo Alto", "Milpitas"}

ROOT = Path(__file__).parent.parent
data = json.loads((ROOT / "dev" / "bay_area_discovered.json").read_text())

# Filter to Phase 1, exclude seniors
candidates = [
    a for a in data["apartments"]
    if a["city"] in PHASE1_CITIES and "senior" not in a["title"].lower()
]
print(f"Candidates from discovery JSON: {len(candidates)}")

conn = psycopg2.connect(RAILWAY_DB)
cur = conn.cursor()

# Fetch existing source_urls and external_ids to avoid duplicates
cur.execute("SELECT source_url, external_id FROM apartments")
existing_urls = set()
existing_ext_ids = set()
for url, ext_id in cur.fetchall():
    if url:
        existing_urls.add(url.strip().rstrip("/"))
    if ext_id:
        existing_ext_ids.add(ext_id)

def norm_url(u):
    return (u or "").strip().rstrip("/")

new_apts = [
    a for a in candidates
    if norm_url(a.get("source_url")) not in existing_urls
    and a.get("external_id") not in existing_ext_ids
]
print(f"Already in DB: {len(candidates) - len(new_apts)}")
print(f"Net new to insert: {len(new_apts)}")

if not new_apts:
    print("Nothing to insert.")
    sys.exit(0)

rows = [
    (
        a["external_id"],
        a["title"],
        a.get("description"),
        a.get("address"),
        a["city"],
        a["state"],
        a.get("zipcode", "00000"),
        a.get("latitude"),
        a.get("longitude"),
        a.get("property_type", "apartment"),
        a.get("source_url"),
        True,   # is_available
    )
    for a in new_apts
]

execute_values(cur, """
    INSERT INTO apartments
        (external_id, title, description, address, city, state, zipcode,
         latitude, longitude, property_type, source_url, is_available,
         created_at, updated_at)
    VALUES %s
    ON CONFLICT (external_id) DO NOTHING
""", [
    (
        r[0], r[1], r[2], r[3], r[4], r[5], r[6],
        r[7], r[8], r[9], r[10], r[11],
        "now()", "now()",
    )
    for r in rows
], template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)")

conn.commit()
print(f"\nInserted {cur.rowcount} apartments into Railway DB.")

# Summary by city
from collections import Counter
city_counts = Counter(a["city"] for a in new_apts)
for city, count in sorted(city_counts.items()):
    print(f"  {count:3d}  {city}")

cur.close()
conn.close()
