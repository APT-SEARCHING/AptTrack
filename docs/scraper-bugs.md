# Scraper Bug Log

Open issues found during dogfood. Fix together in a batch.

---

## BUG-01: universal_dom picks up deposit as rent price

**Status**: RESOLVED  
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

**Status**: RESOLVED  
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

**Status**: PARTIALLY RESOLVED — sanitize guard in place; underlying sites still unscrapeable  
**Affected**: Verve Mountain View (id=194), Reserve at Mountain View (id=218)  
**Evidence**: DB plans named "Marina Playa", "Birch Creek", "River Terrace", "Almaden Lake Village"
(apt 194) and "Briarwood Apartments", "Arbor Terrace Apartments", "The Arches Apartments",
"Lorien Apartments" (apt 218) — all sibling UDR/Equity properties, not floor plan names.  
**Root cause**: At seed time the LLM navigated to a multi-property comparison page and extracted
sibling property names+prices as if they were floor plans for the target apartment.  
**Fix applied (2026-04-27)**:
- `_sanitize_floor_plans()` Filter A in `backend/app/worker.py`: drops any scraped FloorPlan
  whose name contains a property-style keyword (`village`, `creek`, `terrace`, `apartments`,
  `plaza`, `heights`, `park`, `ridge`, `court`, `place`, `gardens`, `estates`, `hills`,
  `commons`, `manor`, `lake`, `pointe`, `playa`, `marina`) AND has ≥2 words AND does not match
  a plan-code prefix pattern (`^[A-Z]\d`, `^\d[xX]\d`, `^[Ss]tudio\b`, `^[Pp]lan\s`).
- Contaminated DB plans for 194 and 218 archived (`is_available=false`) via manual SQL.
- 23 unit tests in `tests/unit/test_sanitize_floor_plans.py`. All pass.
- Verified on re-scrape 2026-04-27: sibling_dropped=4 for apt 194, sibling_dropped=4 for apt 218.
- Canonical regression check (Miro, The Ryden, Atlas): sanitize silent — no false positives on
  plan names like `Chabot`, `Joaquin Miller`, `Leona Canyon`, `A1 + Den`.

**Remaining issue**: UDR (194) and Equity (218) pricing pages return only sibling-comparison data
via both LLM and universal_dom — after sanitize drops all scraped plans, DB ends up with 0 active
plans. Real fix requires a UDR/Equity platform adapter. Tracked as future work.  
**File**: `backend/app/worker.py` — `_sanitize_floor_plans()`, `_looks_like_sibling_property()`

---

## BUG-05: LLM captures "starting from $X" overview price instead of per-plan prices

**Status**: PARTIALLY RESOLVED — sanitize guard in place; Savoy self-corrected on re-scrape  
**Affected**: Savoy (id=248) — 23 DB plans all priced at $3,200 (= the "starting from" price)  
**Evidence**: Savoy's floor plans page shows "Starting From $3,200" as a headline price.
Individual plan pages show distinct prices (A1 $3,287, A2 $3,521, B1 $4,861, etc.).
DB had 23 plans all at $3,200 — clearly extracted from the overview, not the detail pages.  
**Root cause**: The LLM called `submit_findings` after seeing the overview page without navigating
into each plan's detail. The `$3,200 starting from` was used for all plans.
The Jonah Digital adapter did not fire (signal present but no hrefs extracted), so LLM took over
but didn't go deep enough.  
**Fix applied (2026-04-27)**:
- `_sanitize_floor_plans()` Filter D in `backend/app/worker.py`: if >50% of priced plans share
  the exact same `min_price` (and ≥4 plans are priced), null all prices — overview contamination.
  Threshold of 4 plans avoids false positives on small legitimate plan lists.
- 5 unit tests covering threshold boundary, same-price trigger, and distinct-price passthrough.
- On 2026-04-27 re-scrape, Savoy LLM navigated into per-plan detail and returned distinct prices
  (A1 $3,309, A1.1 $3,200, etc.) — Filter D did not trigger. DB now has real per-plan prices.

**Remaining issue**: Jonah Digital adapter hrefs extraction still fails for liveatsavoy.com.
If the LLM regresses to overview-only on a future scrape, Filter D will catch it and null all
prices rather than store the misleading single price across all 23 plans.  
**File**: `backend/app/worker.py` — `_sanitize_floor_plans()`, `_looks_like_starting_from_contamination()`

---

## BUG-06: LLM agent submits deposit amount as rent price

**Status**: RESOLVED  
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
**Fix applied (2026-04-27) — belt-and-suspenders**:
1. **LLM system prompt** (`backend/app/services/scraper_agent/agent.py` + integration mirror):
   Replaced 3-line "NEVER use deposit" rule with a full `DEPOSIT VS RENT DISAMBIGUATION` block
   containing labelled RENT vs NOT-RENT categories and 4 worked examples with explicit
   Correct/Wrong annotations. Mirrors updated in `tests/integration/agentic_scraper/agent.py`.
2. **`_sanitize_floor_plans()` Filter B** (`backend/app/worker.py`): nulls `min_price`/`max_price`
   on any FloorPlan where price < $1,500 (Bay Area rent floor). Also Filter C nulls price > $25,000.
   Applied before `_persist_scraped_prices` so deposit amounts never reach the DB.

**Verified re-scrape 2026-04-27**:
- Camden (244): LLM returned `Studio Plan A min_price=1000`, `1 Bed 1 Bath Plan B min_price=1000`.
  Filter B nulled both. DB now has 5 plans with real rents: Studio $2,055, 1BR $2,395, 2BR $2,850.
- Hazelwood (289): LLM returned `Studio min_price=500`, `1 Bedroom min_price=600`.
  Filter B nulled both. DB has 3 plans: Studio NULL, 1BR NULL, 2BR $3,340 (site shows "Call" for studio/1BR).
- Canonical regression check (Miro, The Ryden, Atlas): Filter B did not fire — no false positives.

**Files changed**:
- `backend/app/services/scraper_agent/agent.py` — SYSTEM_PROMPT deposit disambiguation block
- `tests/integration/agentic_scraper/agent.py` — mirror
- `backend/app/worker.py` — `_sanitize_floor_plans()` Filter B + Filter C, `_BAY_AREA_RENT_FLOOR`, `_BAY_AREA_RENT_CEILING`
- `tests/unit/test_sanitize_floor_plans.py` — 23 unit tests covering all 4 filters

---

<!-- Add new bugs below this line -->

## BUG-14: The Tolman (apt 7) — Filter A false-positive drops real JD plan names; orphan legacy plans persist with stale prices

**Status**: open  
**Affected**: The Tolman (id=7)  
**Evidence**:
- JonahDigital adapter detects 8 named plans via detail pages:  
  Dry Creek (Studio, 552 sqft), Vista Peak (1BR, 584 sqft, $3,489), Maguire Peak (1BR, 699 sqft, $3,816),
  Monument Peak (1BR, 910 sqft), Peak Meadow (1BR, 702 sqft, $3,926), High Ridge (2BR, 1097 sqft, $4,576),
  Mission Peak (2BR, 954 sqft, $4,761), Tolman Peak (2BR, 1202 sqft)
- These are real floor plan names — Tolman is at the base of Mission Peak in Fremont; plan names are local trail names
- DB nonetheless has: "Dry Creek (Studio)" — no price; "High Ridge" — no price. Both missing their correct values.
- DB also has two orphan legacy plans from a pre-JD LLM scrape: "Studio" ($3,200) and "1 Bed / 1 Bath" ($3,252)
  — neither name is produced by the JD adapter, so they are never updated. Live 1BR starts at $3,489 (Vista Peak).

**Root causes** (two distinct issues):

**A — Filter A false-positive**  
`_sanitize_floor_plans()` Filter A drops any plan whose name contains a sibling-property keyword
(`creek`, `ridge`, among others) AND is ≥2 words AND lacks a plan-code prefix. "Dry Creek" contains
`creek`; "High Ridge" contains `ridge` → both are silently dropped on every JD scrape. Since the JD
adapter sources plans from per-apartment detail pages (not multi-property comparison pages), Filter A's
signal is irrelevant and incorrect here.  
Impact: "Dry Creek" (only studio plan, no price currently) and "High Ridge" ($4,576) never reach the DB.

**B — Orphan legacy plans from pre-JD era**  
At initial seed time the LLM extracted generic plan names ("Studio", "1 Bed / 1 Bath"). Later, the JD
adapter was added and correctly identifies named plans (Dry Creek, Vista Peak, etc.). But `_match_plan`
strategy 1 (exact name) fails for "Studio" → "Dry Creek" (different names). Strategy 3 (sqft ±5) also
fails because the legacy plans have NULL `area_sqft`. Strategy 4 auto-creates new DB plans for JD names,
but the legacy plans persist indefinitely with their stale seed-time prices.  
"Studio $3,200" and "1 Bed / 1 Bath $3,252" are visible to users as if they were current prices.

**Fix**:
1. **Filter A exemption for JD adapter**: skip Filter A when the plan was returned by the JonahDigital
   adapter (or any adapter that fetches from per-apartment detail pages, not comparison pages).
   Simplest implementation: add `adapter_name` argument to `_sanitize_floor_plans()` and skip Filter A
   when `adapter_name == "jonah_digital"`.
2. **Archive orphan legacy plans**: after a successful JD adapter run, archive DB plans that (a) have
   NULL `area_sqft` and (b) use generic names (`_GENERIC_NAME_RE`) and (c) are not matched by any plan
   in the adapter output. This is a targeted version of the broader B1+B2 fix.

**Note**: BUG-09 incorrectly listed "High Ridge" and "Dry Creek" as sibling contamination examples.
They are real Tolman plan names — Filter A is producing a false positive on them.  
**File**: `backend/app/worker.py` — `_sanitize_floor_plans()`, `_SIBLING_PROPERTY_KEYWORDS`

---

## BUG-15: Astella (apt 6) — A/B/C-series plans stored with bedrooms=0 instead of 1/2/3; 8 of 9 plans unpriced

**Status**: open  
**Affected**: Astella Apartments (id=6), source_url=`https://astellaapts.com/floor-plans/`  
**Evidence**:
- DB has 9 plans. Only "A9 - 1 Bedroom" has a price ($3,912) and correct bedrooms=1.
- 8 other plans (S3-Studio, A1, A6, A11, B1, B5, C1, C2) all stored as bedrooms=0 with no price.
- Live page shows clearly: A-series = 1 BR, B-series = 2 BR, C-series = 3 BR, S-series = Studio.
  E.g. "1 BEDROOM 1 BATH 571 SF" for A1, "2 BEDROOM 2 BATH 811 SF" for B1, "3 BEDROOM 2 BATH 1,050 SF" for C1.
- Live 1BR base rent starts at $4,192 (DB shows $3,912 for A9, Δ+$280 stale).
- Live 2BR base rent from $5,320; 3BR from $7,074 — all 8 plans in DB have NULL current_price.
- Scrape history: only 2 runs recorded (both `skipped_negative_cache`); negative cache table is
  currently empty (cleared in prior session), so next daily scrape will retry.
- Astella site is NOT JonahDigital (1.6 MB HTML, custom CMS). Plans are rendered in plain text in the
  DOM — LLM agent should be able to extract them if it can navigate the page.

**Root cause**:
1. **Bedrooms mis-classification at seed/initial-scrape time**: Plan names A1, A6, A11, B1, B5, C1, C2
   are opaque codes with no bedroom count embedded. The scraper defaulted to 0 (studio) when it couldn't
   infer from the plan name. Only "A9 - 1 Bedroom" was correctly classified because the name explicitly
   contains "1 Bedroom". The B1 fix (B1 from CLAUDE.md Dogfood Blockers) would update bedrooms on each
   scrape, but the scraper hasn't successfully run yet to apply that.
2. **Stale price**: The $3,912 for A9 was from an old LLM scrape; live 1BR now starts at $4,192 (+$280).
   All other plan prices are NULL — never successfully scraped.

**Fix**:
1. Manual SQL to correct bedrooms: A-series → 1, B-series → 2, C-series → 3, S-series → 0.
   ```sql
   UPDATE plans SET bedrooms=1 WHERE apartment_id=6 AND name ~ '^A\d';
   UPDATE plans SET bedrooms=2 WHERE apartment_id=6 AND name ~ '^B\d';
   UPDATE plans SET bedrooms=3 WHERE apartment_id=6 AND name ~ '^C\d';
   ```
2. Trigger a fresh scrape (negative cache is clear); monitor that the LLM agent successfully
   navigates to per-plan prices and updates all 9 plans.
3. If LLM scrape continues to fail, investigate whether the site blocks headless browsers
   (1.6 MB page with heavy client-side JS may not fully render prices for Playwright).

**File**: DB — manual bedrooms SQL; `backend/app/worker.py` — B1 fix (update bedrooms on scrape)

## BUG-07: RentCafe adapter blocked by HTTP 403

**Status**: open  
**Affected**: venue-apts.com (id=253), 808west-apts.com (id=259), ilaraapartments.com (id=251),
turnleaf-apts.com (id=247), liveatorchardglen.com (id=281), atriumgardenapartments.com (id=270)
— all newly seeded apartments using the RentCafe platform.  
**Evidence**: `RentCafe: failed to fetch https://www.venue-apts.com/floorplans: HTTP Error 403: Forbidden`
observed on all 6 sites during 2026-04-27 full re-scrape.  
**Root cause**: RentCafe's CDN (Cloudflare) blocks the scraper's default `httpx` User-Agent on the
`/floorplans` endpoint. The adapter fetches a JSON API endpoint that requires a browser-like UA or
session cookie to pass the bot check.  
**Fix options**:
1. Add a browser-like `User-Agent` header to the RentCafe adapter's HTTP client
2. Route the RentCafe fetch through Playwright (rendered fetch) instead of `httpx`
3. Find RentCafe's public API endpoint (separate from the /floorplans page) that doesn't require a session  
**File**: `backend/app/services/scraper_agent/platforms/rentcafe.py`

---

## BUG-08: Essex (essexapartmenthomes.com) SSL certificate error

**Status**: open  
**Affected**: ~10 Essex apartments — Windsor Ridge (id=232), 1250 Lakeside (id=231), Bridgeport (id=237),
Mission Peaks (id=235), Stevenson Place (id=241), Briarwood at Central Park (id=242),
Boulevard (id=236), Paragon (id=240), The Rexford (id=239), plus Essex Sunnyvale/MV properties.  
**Evidence**: `SSLCertVerificationError: certificate verify failed: self signed certificate in certificate chain`
on all `www.essexapartmenthomes.com` requests during 2026-04-27 full re-scrape.  
**Root cause**: Essex's CDN presents a certificate chain that Python 3.8's `ssl` module rejects as
self-signed. The SightMap adapter (which successfully extracted prices in earlier sessions) went through
Playwright which uses Chromium's more permissive cert validation. The content-hash pre-check uses
`httpx` which respects Python's SSL context and fails.  
**Impact**: Content-hash check fails → proceeds to scrape → SightMap adapter (via Playwright) still
works. So price extraction succeeds but generates excessive SSL warning noise in logs.  
**Fix**: Add `verify=False` (or custom SSL context) to the `httpx` client used in the content-hash
pre-check for domains known to have this issue, or suppress the warning and let Playwright handle it.  
**File**: `backend/app/worker.py` — content-hash GET request, `backend/app/services/scraper_agent/fetch.py`

---

## BUG-09: Sibling property contamination — additional affected apartments

**Status**: open (BUG-04 extension)  
**Affected**: Multiple newly seeded apartments — confirmed on 2026-04-27 full re-scrape:
- `Embark Apartments` (3 occurrences) — sibling of Reserve at Mountain View (id=218)
- `The Verdant Apartments` — newly seeded apt with multi-property comparison page
- `Stevens Creek Villas` — sibling property contamination
- `Snow Park` (2 occurrences) — sibling of some Oakland/Bay Area multi-property page
- `808 West Apartments` — sibling of another apt on same platform page
- `Warburton Village Apartments` — sibling contamination
- `High Ridge`, `Dry Creek` — sibling names from UDR-style comparison pages  
**Sanitize status**: All of the above were correctly dropped by `_sanitize_floor_plans()` Filter A.
However the affected apartments end up with 0 active plans — the real floor plan data is not being
retrieved because the scraper keeps landing on multi-property comparison pages.  
**Fix**: Same root fix as BUG-04 — these sites need platform-specific adapters (UDR, Equity, etc.)
that target the per-property pricing widget directly. Until then, sanitize correctly prevents
contamination but cannot recover the missing real data.

---

## BUG-13: Enclave — LLM name instability causes 28 duplicate plans (real count: 9)

**Status**: open  
**Affected**: The Enclave (id=21)  
**Evidence**:
- DB has 28 active plans with names like "1 Bed / 1 Bath - Range 1", "Studio - Unit 2",
  "1 Bed / 1 Bath Plan A", "1 Bedroom 1 Bath" etc. — all referring to the same ~9 floor plans
- Live LLM scrape (2026-04-27) returns 9 plans with clear codes: Studio, A1($3,002/637sqft),
  A2($3,116/730sqft), A3($3,196/734sqft), A4($3,358/820sqft), B1($3,895/1003sqft),
  B2($3,769/1008sqft), B3($3,874/1040sqft), B4($3,911/1091sqft)
- DB prices are stale/wrong: "1 Bed / 1 Bath - Range 1" = $2,921 vs live A1 = $3,002  
**Root cause**: Enclave's floor plan page is JS-heavy (no static prices). Each LLM run
navigates differently and returns slightly different plan names. `_match_plan` strategy 1
(exact name) always fails → strategy 2 (sqft ±10%) fails because sqft=NULL on first seed →
strategy 4 auto-creates a new plan every run. Over many scrapes, 28 duplicates accumulated.  
**Fix**:
1. Archive all 28 existing plans (set is_available=false)
2. Re-scrape once to create the correct 9 plans with CAPI-style codes (A1–A4, B1–B4)
3. Fix `_match_plan`: for LLM path, when exact name fails but beds+sqft match exactly → match
   instead of auto-create; tighten sqft tolerance to exact or ±2% (not ±10%)  
**File**: DB — manual archive SQL; `backend/app/worker.py` — `_match_plan`

---

## BUG-10: The Cathay Lotus seeded with aggregator URL instead of apartment website

**Status**: open  
**Affected**: The Cathay Lotus (id=277)  
**Evidence**: `source_url = http://www.vrent.com/` — this is a property management company /
aggregator website, not the apartment's own website. DB plans include `2 Bedrooms $1,595`
which is implausibly low for Bay Area 2BR (likely wrong data from aggregator context).  
**Root cause**: At seed time the GMB listing pointed to `vrent.com` (the management company's
site) rather than a dedicated apartment page. The LLM scraped vrent.com and extracted whatever
it found there.  
**Fix**:
1. Find the actual apartment website for The Cathay Lotus (manual lookup)
2. Update `source_url` in `apartments` table
3. Re-scrape to get correct floor plan data  
**File**: DB — `UPDATE apartments SET source_url='<real_url>' WHERE id=277`

---

## BUG-11: Valley Village Retirement Community incorrectly seeded as regular apartment

**Status**: open  
**Affected**: Valley Village Retirement Community (id=28)  
**Evidence**: `source_url = http://www.valleyvillageretirement.com/` — this is a senior
retirement community, not a regular apartment complex. Plans show "Mini Studio Deluxe",
"High Rise" — retirement facility unit types.  
**Root cause**: Google Maps import included senior/retirement communities when keywords
matched "apartments near San Jose". CLAUDE.md notes senior housing was later removed from
import keywords, but id=28 was already seeded before that change.  
**Fix**: Archive the apartment — `UPDATE apartments SET is_available=false,
data_source_type='unscrapeable', title='[ARCHIVED retirement] ' || title WHERE id=28`.  
**File**: DB — manual archive SQL

---

## BUG-12: Metro Six55 — seed used unit numbers as plan names, CAPI plans merged by sqft fuzzy match

**Status**: open  
**Affected**: Metro Six55 (id=156)  
**Evidence**:
- DB has 3 plans with names "1306", "2105", "2202" (unit numbers, not floor plan codes)
- CAPI returns 6 floor plans: 1x1A($1,969), 1X1B($2,169), 1x1C($2,420), 2x2C($2,597), 2x2A($2,610), 2x2B($2,787)
- DB only shows $1,969 / $2,169 / $2,597 — 1x1C($2,420), 2x2A($2,610), 2x2B($2,787) missing  
**Root cause** (two compounding issues):
1. **Seed-time**: LLM seeded Metro Six55 using unit numbers (1306, 2105, 2202) as plan names instead of
   CAPI floor plan codes. These names don't match "1x1A" etc. so strategy-1 (exact name) always fails.
2. **sqft fuzzy collapse**: `_match_plan` strategy-2 maps 1x1A(711sqft) AND 1x1C(750sqft) both to
   DB plan "1306"(711sqft) since |750-711|/711=5.5% < 10%. Similarly 2x2C/2x2A/2x2B all map to "2202"(965sqft).
   `_persist_scraped_prices` then takes `min()` across merged fps, so 1x1C's $2,420 and 2x2A's $2,610 are
   silently dropped.  
**Fix**:
1. Rename DB plans: "1306"→"1x1A", "2105"→"1X1B", "2202"→"2x2C" (manual SQL or normalization pass)
2. Auto-create the 3 missing plans: 1x1C, 2x2A, 2x2B
3. Sqft tolerance in strategy-2 for LeaseStar may need tightening (±5% instead of ±10%)  
**Note**: CAPI adapter IS working correctly (`_fetch_leasingstar_plans` returns all 6 plans).
`availableUnits=None` for all plans is a separate issue (BUG-02).  
**File**: DB — manual plan rename SQL; `backend/app/worker.py` — `_match_plan` sqft tolerance
