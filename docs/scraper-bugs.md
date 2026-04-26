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

<!-- Add new bugs below this line -->
