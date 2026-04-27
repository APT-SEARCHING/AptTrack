---
description: Verify scraper accuracy for one or more apartments by comparing DB prices against live website prices
allowed-tools: Bash, Read
---

Verify whether AptTrack's scraper is producing accurate prices for the given apartment(s).

**Arguments**: apartment IDs (space-separated), e.g. `/verify-scraper 228 181 9`
If no IDs given, pick 5 random recently-scraped apartments.

## Process

### Step 1 — Get DB state

For each apartment ID, query Railway production DB:

```bash
PGPASSWORD=NDrijYZDpKGoFRpaBbHhtZYsGvxmXKWJ psql \
  -h maglev.proxy.rlwy.net -p 34474 -U postgres -d railway -c "
SELECT a.id, a.title, a.source_url, sr.adapter_name, sr.outcome, sr.run_at::date,
       (SELECT string_agg(name || ' \$' || current_price::int::text, ', ' ORDER BY current_price)
        FROM plans WHERE apartment_id = a.id AND is_available = true AND current_price IS NOT NULL)
FROM apartments a
JOIN scrape_runs sr ON sr.apartment_id = a.id
  AND sr.run_at = (SELECT max(run_at) FROM scrape_runs WHERE apartment_id = a.id)
WHERE a.id IN (<ids>);
"
```

Record: title, source_url, adapter_name, last scrape date, plan prices from DB.

### Step 2 — Fetch live prices from the website

Run the appropriate adapter against the apartment's source_url **right now**:

```python
# In /Users/chenximin/AptTrack/backend/
import asyncio
from app.services.scraper_agent.fetch import fetch_static
from app.services.scraper_agent.platforms.avalonbay import _parse_avalon_global_content
from app.services.scraper_agent.platforms.sightmap import SightMapAdapter
from app.services.scraper_agent.platforms.leasingstar import LeasingStarAdapter
from app.services.scraper_agent.platforms.windsor import WindsorAdapter
from app.services.scraper_agent.platforms.universal_dom import UniversalDOMExtractor
from app.services.scraper_agent.browser_tools import BrowserSession

# Choose adapter based on adapter_name from DB:
# avalonbay  → _parse_avalon_global_content(html)
# sightmap   → SightMapAdapter().detect/extract (needs browser)
# leasingstar→ LeasingStarAdapter().detect/extract
# windsor    → WindsorAdapter().detect/extract
# universal_dom → UniversalDOMExtractor().extract (try static first, then rendered)
# success/None → use browser + extract_all_units or read rendered text for prices
```

For SightMap: group results by plan_name, keep the **minimum** price per plan (mirrors the min-price aggregation fix).

### Step 3 — Compare DB vs live

Build a side-by-side table:

| Plan | DB price | Live price | Delta | Match? |
|------|---------|-----------|-------|--------|

Flag any plan where `abs(db_price - live_price) > 50` as a potential discrepancy.

### Step 4 — For each discrepancy: force re-scrape to confirm

**Do NOT assume the difference is natural price fluctuation without verifying.**

Clear the content hash and re-scrape via the production pipeline:

```bash
# Clear hash
PGPASSWORD=... psql ... -c "UPDATE apartments SET last_content_hash = NULL WHERE id = <id>;"

# Re-scrape (runs locally but writes to Railway DB)
DATABASE_URL="postgresql://postgres:NDrijYZDpKGoFRpaBbHhtZYsGvxmXKWJ@maglev.proxy.rlwy.net:34474/railway" \
  python -c "
import sys; sys.path.insert(0, '/Users/chenximin/AptTrack/backend')
import logging; logging.basicConfig(level=logging.WARNING)
from app.worker import task_refresh_apartment_chunk
result = task_refresh_apartment_chunk.apply(args=[[<id>]])
print('succeeded' if result.successful() else 'FAILED')
"
```

Then re-query the DB prices.

### Step 5 — Classify each case

After re-scrape, compare the **new DB price** with the **live website price**:

| Result | Classification | Action |
|--------|---------------|--------|
| New DB price == live price | ✅ Scraper works — old price was natural price change | No action needed |
| New DB price != live price AND matches old DB price | ❌ Scraper bug — not reading current data | File bug in `docs/scraper-bugs.md` |
| New DB price != live price AND different from both | ❌ Scraper bug — getting wrong data entirely | File bug in `docs/scraper-bugs.md` |
| New DB price is a deposit amount (<$1,500 for Bay Area) | ❌ BUG-01 deposit contamination | Known bug |
| Plan names are other property names ("Marina Playa" etc.) | ❌ BUG-04 sibling property contamination | Known bug |
| All plans show same price | ❌ BUG-05 "starting from" overview price | Known bug |

### Step 6 — Report

Summarize per apartment:
- ✅ PASS: scraper price matches live site after re-scrape
- ⚠️ PRICE CHANGE: old DB was stale, re-scrape now correct
- ❌ FAIL: re-scrape still doesn't match — bug category + log to `docs/scraper-bugs.md`

**Key rule**: Never mark a discrepancy as "natural price change" without actually re-scraping and confirming the re-scraped value matches the site. The re-scrape is the ground truth.
