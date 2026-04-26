# Scraper Bug Log

Open issues found during dogfood. Fix together in a batch.

---

## BUG-01: universal_dom picks up deposit as rent price

**Status**: open  
**Affected**: Camden Village (id=244) — `$1,000` shown instead of `$2,055/mo`  
**Root cause**: `_PRICE_RE = re.compile(r"\$\s*([\d,]{3,6})")` in `universal_dom.py` matches
the first `$` it finds. Camden Village HTML layout is:
```
Deposit: $1000   $2,055 per month
```
The deposit `$1000` appears before the rent, so it wins.  
**Fix**: Before running `_PRICE_RE`, strip `Deposit[:\s]+\$[\d,]+` from the card text.
Alternatively, prefer prices followed by `/mo` or `per month` over bare amounts.  
**File**: `backend/app/services/scraper_agent/platforms/universal_dom.py` — `_extract_unit_from_card()`

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

**Status**: open  
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
**Fix options**:
1. For Avalon properties: after AvalonBay adapter returns plans, check if existing DB plans
   have generic names ("X Bed / X Bath") and update them to plan codes if sqft+beds match
2. Or: delete generic-named plans for Avalon apartments and let adapter auto-create clean ones
3. Or: add a "name normalization" pass in `_persist_scraped_prices` that updates plan names
   when the existing name matches a generic pattern  
**File**: `backend/app/services/scraper_agent/platforms/avalonbay.py` + `backend/app/worker.py` `_match_plan`

---

<!-- Add new bugs below this line -->
