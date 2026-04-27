# Scraper Bug Log

Open issues found during dogfood. Fix together in a batch.

---

## BUG-01: universal_dom picks up deposit as rent price

**Status**: RESOLVED — commit to be added  
**Affected**: Camden Village (id=244), The Hazelwood (id=289)  
**Root cause**: `_PRICE_RE = re.compile(r"\$\s*([\d,]{3,6})")` in `universal_dom.py` matched
the first `$` in card text. Camden Village / Hazelwood HTML layout:
```
Deposit: $1000   $2,055 per month
```
The deposit `$1000` appeared before the rent, so it won.  
**Fix applied**: Two-pass extraction in `_extract_price_from_card_text()`:
- Pass A (raw text): prefer `$X /mo` or `$X per month` — explicit monthly suffix is unambiguous
- Pass B (stripped text): strip deposit/fee phrases first, then take bare `$X >= $1,000`
- Bay Area rent floor ($1,000) on Pass B rejects application fees and small deposits
13 unit tests added in `tests/unit/test_universal_dom_price.py`. All pass.  
**Note**: Camden/Hazelwood production re-scrapes (2026-04-27) went through the LLM agent path
(not `universal_dom`), and the LLM also misread deposit prices. That's a separate LLM-level
issue — the `universal_dom` fix is verified by unit tests only.  
**Files changed**: 
- `backend/app/services/scraper_agent/platforms/universal_dom.py`
- `tests/integration/agentic_scraper/platforms/universal_dom.py` (mirror)
- `tests/unit/test_universal_dom_price.py` (new)

---

## BUG-02: LeaseStar CAPI returns stale prices

**Status**: open  
**Affected**: 555 Apartment Homes (id=238, property_id=8104238)  
**Evidence**: 
- CAPI `minimumMarketRent` for 1x1 Townhome → $2,746; site shows $2,874 (+$128)
- CAPI for 1x1 (635 sqft) → $2,476; site shows "Please Call" (no price / unavailable)
- CAPI `availableUnits=None`, `totalUnits=None` for all plans → data is not live
**Root cause**: `capi.myleasestar.com/v2/property/{id}/floorplans` is a static/cached endpoint
that does not reflect real-time availability or pricing. The interactive site loads live
unit data from a different API call (per-unit drill-down visible in the unit selection panel).  
**Fix options**:
1. Find the live per-unit endpoint (intercept network requests on the floor plans page
   clicking into each plan) — likely `capi.myleasestar.com/v2/property/{id}/units` or similar
2. Fall back to the LLM agent for LeaseStar sites when CAPI data is stale (detecte by
   `availableUnits=None`)  
**File**: `backend/app/services/scraper_agent/platforms/leasingstar.py`

---

## BUG-03: Avalon — generic seed plan names block specific floor plan code matching

**Status**: RESOLVED — commit to be added  
**Affected**: All Avalon/eaves/AVA properties — confirmed on Avalon Fremont (id=158), likely all ~15 Avalon keepers  
**Evidence** (Avalon Fremont):
- Fusion.globalContent contains 16 units across 5 distinct floor plan types (A2G, B3G, B1G, B4G, C2G)
- AvalonBay adapter correctly returns all 5 plans
- DB only has 3 plans with generic names: "1 Bed / 1 Bath", "2 Bed / 2 Bath", "3 Bed / 3 Bath"
- B1G ($3,615) and B4G ($3,700) — two additional 2BR variants — are missing from DB  
**Root cause**:
1. Initial seed used GMB URL → LLM extracted generic names ("1 Bed / 1 Bath") not plan codes
2. On re-scrape, `_match_plan` strategy 1 (exact name) fails: "A2G" ≠ "1 Bed / 1 Bath"
3. Strategy 2 (sqft fuzzy ±10%) may match some plans, masking others
4. When multiple 2BR candidates exist, strategy 3 is ambiguous → strategy 4 auto-creates
   — but if a prior scrape run hard_failed, the new plans were never written
**Note**: "Load More / Load All 16" on Avalon's website is UI pagination of individual units.
The Fusion.globalContent JSON in static HTML already contains all units — this is NOT a
scraper limitation; adapter sees all units regardless of Load More button.  
**Fix applied**: `_normalize_avalon_plan_names()` pre-pass added to `_persist_scraped_prices`.
For Avalon/eaves/AVA domains, renames DB plans matching `_GENERIC_NAME_RE` (e.g. "1 Bed / 1 Bath")
to the adapter-returned specific code (e.g. "A2G") when beds + sqft match within ±5%.
`db.flush()` after rename ensures `_match_plan` strategy 1 (exact name) succeeds immediately.
22 unit tests in `tests/unit/test_avalon_name_normalize.py`. All pass.

**Verified re-scrape 2026-04-27**:
- apt 158 (Avalon Fremont): 3 plans renamed — `1 Bed / 1 Bath`→`A2G`, `2 Bed / 2 Bath`→`B3G`, `3 Bed / 3 Bath`→`C2G`
- apt 160 (Avalon Morrison Park): 0 renames — fractional-bath names (`1.5 Bath`) not matched by regex; fuzzy strategy 2 still works correctly
- apt 167 (AVA Nob Hill): 0 renames — names include sqft (`Studio 371 sqft`), not pure generic format

**File**: `backend/app/worker.py` — `_normalize_avalon_plan_names()` + call in `_persist_scraped_prices`

---

## BUG-04: LLM extracts sibling-property names as floor plan names (UDR / multi-property domains)

**Status**: open  
**Affected**: Verve Mountain View (id=194)  
**Evidence**: DB plans named "Marina Playa", "Birch Creek", "River Terrace", "Almaden Lake Village"
— these are other UDR apartment communities in the Bay Area, not floor plan names at Verve.
Current site prices: $4,147–$5,356; DB shows $2,475–$3,506.  
**Root cause**: At seed time the LLM navigated to a page that listed similar/nearby UDR properties
and extracted their names+prices as if they were floor plans for Verve Mountain View.
`universal_dom` on the actual pricing page returns "Details" as plan name (clickable buttons,
not plan name text) and prices from $4,147–$5,356.  
**Fix**: 
1. Re-scrape Verve with LLM, explicitly starting at the `/apartments-pricing/` URL
2. Add to `_sanitize()`: reject FloorPlan entries whose `name` matches a known property
   pattern (contains "Village", "Creek", "Terrace", "Plaza" etc.) when other entries on the
   same page have real plan codes — these are sibling-property cards, not plans
3. Long-term: detect UDR's pricing widget and add a UDR adapter  
**File**: `backend/app/services/scraper_agent/agent.py` + `platforms/universal_dom.py`

---

## BUG-05: LLM captures "starting from $X" overview price instead of per-plan prices

**Status**: open  
**Affected**: Savoy (id=248) — 23 DB plans all priced at $3,200 (= the "starting from" price)  
**Evidence**: Savoy's floor plans page shows "Starting From $3,200" as a headline price.
Individual plan pages show distinct prices (A1 $3,287, A2 $3,521, B1 $4,861, etc.).
DB has 23 plans all at $3,200 — clearly extracted from the overview, not the detail pages.  
**Root cause**: The LLM called `submit_findings` after seeing the overview page without navigating
into each plan's detail. The `$3,200 starting from` was used for all plans.
The Jonah Digital adapter did not fire (signal present but no hrefs extracted), so LLM took over
but didn't go deep enough.  
**Fix**:
1. Debug why Jonah Digital hrefs extraction fails for liveatsavoy.com
2. In `_sanitize()`: reject plans where >50% share the exact same price (likely a "starting from"
   contamination) — log a warning, keep only the one with the lowest price as a single plan
3. LLM prompt: "If all plans show the same price, that's a 'starting from' aggregate. Navigate
   into individual plan detail pages to get per-plan prices before calling submit_findings."  
**File**: `backend/app/services/scraper_agent/agent.py` + `backend/app/worker.py` `_sanitize()`

---

## BUG-06: LLM agent submits deposit amount as rent price

**Status**: open  
**Affected**: Camden Village (id=244) — Studio Plan A $1,000, 1 Bed Plan J $1,000 (real rent ~$2,055/mo+)  
          The Hazelwood (id=289) — Studio $500, 1 Bedroom $600 (real rent "Call for details")  
**Root cause**: Sites like Camden Village / The Hazelwood show deposit before rent in their HTML:
```
Deposit: $1,000   $2,055 per month
```
The LLM reads both numbers and submits the deposit amount ($1,000 / $500) as `min_price` in
`submit_findings`. BUG-01 fixed this for the `universal_dom` adapter (two-pass extraction with
deposit stripping), but Camden/Hazelwood scrape via the **LLM agent path** (adapter_name=NULL in
scrape_runs), so the universal_dom fix does not apply.  
**Evidence (2026-04-27 re-scrape)**:
- Camden LLM submitted: `Studio Plan A min_price=1000`, `1 Bed Plan J min_price=1000`
- Hazelwood LLM submitted: `Studio min_price=500`, `1 Bedroom min_price=600`
- DB still reflects these deposit amounts  
**Fix options**:
1. `_sanitize()` in `worker.py`: null out `min_price` / `max_price` on any FloorPlan where
   price < $1,000 (Bay Area rent floor) before `_persist_scraped_prices` runs. Fast, safe,
   doesn't touch LLM prompt.
2. LLM system prompt: add instruction "Never use deposit amounts as rent prices. If you see
   'Deposit: $X', ignore $X — look for the rent amount labeled '/mo' or 'per month'."
3. Both: belt-and-suspenders — prompt reduces LLM errors, `_sanitize()` catches remainder.  
**File**: `backend/app/worker.py` — `_sanitize()` (option 1)  
          `backend/app/services/scraper_agent/agent.py` — system prompt (option 2)

---

<!-- Add new bugs below this line -->
