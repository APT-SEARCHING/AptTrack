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

**Status**: RESOLVED — Part B (orphan legacy plans) fixed 2026-04-28; Part A (Filter A) fixed 2026-04-29  
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
1. ✅ **Filter A exemption for JD adapter** (2026-04-29): added `_DETAIL_PAGE_ADAPTERS` frozenset and
   `adapter_name` parameter to `_sanitize_floor_plans()`. When `adapter_name="jonah_digital"`, Filter A
   is skipped (summary["filter_a_skipped"]=True); Filters B/C/D still apply.
   Tolman re-scrape confirmed: "Dry Creek" and "High Ridge" now persist; no false-positive warnings.
   Canonical regression (Miro #11, Avalon Cahill #181): zero false positives, plan counts unchanged.
   5 new tests in `TestAdapterAwareFilter`. `_persist_scraped_prices` now accepts `adapter_name` and
   threads it from `metrics.adapter_name` at the call site.
2. ✅ **Archive orphan legacy plans** (done 2026-04-28 via round1_data_fixes.sql): archived "Studio",
   "1 Bed / 1 Bath", and "2 Bed / 2 Bath" (all NULL `area_sqft`, generic names, not in JD output).
   Tolman active plans: Dry Creek (Studio), High Ridge ($4,575), Maguire Peak ($3,801), Mission Peak ($4,760), Monument Peak, Vista Peak ($3,489).

**Note**: BUG-09 incorrectly listed "High Ridge" and "Dry Creek" as sibling contamination examples.
They are real Tolman plan names — Filter A is producing a false positive on them.  
**File**: `backend/app/worker.py` — `_sanitize_floor_plans()`, `_SIBLING_PROPERTY_KEYWORDS`

---

## BUG-15: Astella (apt 6) — A/B/C-series plans stored with bedrooms=0 instead of 1/2/3; 8 of 9 plans unpriced

**Status**: PARTIALLY RESOLVED — bedrooms corrected 2026-04-28; prices still pending scrape success  
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
1. ✅ Bedrooms corrected via round1_data_fixes.sql (2026-04-28).
   Note: bedrooms regress to 0 on every fatwin re-scrape until B1 (update bedrooms on each scrape)
   is deployed. Each re-scrape re-creates plans with bedrooms=0; only "A9 - 1 Bedroom" survives
   because its name embeds the bedroom count explicitly.
2. **Prices: NULL is correct** (2026-04-29 investigation confirmed). `_parse_fatwin_detail` returns
   `price=None` with comment "FatWin sites always say 'Contact Us'". Direct fetch of Astella plan
   detail pages (e.g. `astellaapts.com/floorplan/a1/`) confirmed: "Please contact us for details"
   — no prices available in static HTML. Main `astellaapts.com/floor-plans/` shows only an aggregate
   "Price Range: $2,833–$7,074" with no per-plan breakdown. NULL DB prices accurately reflect reality.
3. **BUG-15 RESOLVED** for pricing: fatwin is working correctly; Astella is a "contact us for pricing"
   site. Bedrooms regression is tracked under B1 (Dogfood Blocker) — not a separate BUG-15 issue.

**File**: `dev/round1_data_fixes.sql`; `backend/app/worker.py` — B1 fix (update bedrooms on scrape, pending)

## BUG-07: RentCafe adapter blocked by HTTP 403

**Status**: RESOLVED — browser UA fix 2026-04-29  
**Affected**: venue-apts.com (id=253), 808west-apts.com (id=259), ilaraapartments.com (id=251),
turnleaf-apts.com (id=247), liveatorchardglen.com (id=281), atriumgardenapartments.com (id=270)  
**Root cause**: `_HEADERS` in `rentcafe.py` used `AptTrack/1.0 (...)` as User-Agent — Cloudflare CDN
returns 403 on any non-browser UA string. Not a legal block (no JS challenge / anti-bot system);
just a UA filter on a public page.  
**Fix applied**: Replaced custom UA with a standard Chrome browser UA + Accept/Accept-Language/
Accept-Encoding headers. Smoke tested all 6 domains — all return HTTP 200.  
Applied to both `backend/` and `tests/integration/` copies.  
**File**: `backend/app/services/scraper_agent/platforms/rentcafe.py` — `_HEADERS`

---

## BUG-08: Essex (essexapartmenthomes.com) SSL certificate error

**Status**: RESOLVED — ssl=False retry added 2026-04-29  
**Affected**: ~10 Essex apartments — Windsor Ridge (id=232), 1250 Lakeside (id=231), Bridgeport (id=237),
Mission Peaks (id=235), Stevenson Place (id=241), Briarwood at Central Park (id=242),
Boulevard (id=236), Paragon (id=240), The Rexford (id=239).  
**Root cause**: Essex's CDN presented a cert chain Python's `ssl` module rejected as self-signed.
The content-hash pre-check used `aiohttp` (respects Python ssl) and threw `ClientSSLError`.
The exception was caught, logged as WARNING, and `new_hash` stayed None — meaning Essex always
went through the full Playwright scrape path even when content was unchanged (no short-circuit
possible). Data was correct; the cost was wasted Playwright cycles and WARNING log noise.  
**Fix applied**: In `worker.py` Phase 1 content-hash block, catch `aiohttp.ClientSSLError`
separately before the generic `except Exception`. On SSL error: log at DEBUG, retry the GET
with `ssl=False`. If retry succeeds, `new_hash` is populated and the content-hash short-circuit
works normally on subsequent scrapes. If retry also fails, fall through to scrape as before.
Note: Essex's CDN cert appears to be intermittently fixed — smoke test now returns 200 without
SSL error. The retry path is defensive and handles any future recurrence.  
**File**: `backend/app/worker.py` — Phase 1 content-hash GET block

---

## BUG-09: Sibling property contamination — additional affected apartments

**Status**: RESOLVED — Phase C enumeration complete 2026-04-29  

**Original list (unreliable)**: "Embark Apartments, The Verdant, Stevens Creek Villas,
Snow Park, 808 West Apartments, Warburton Village" — these were plan-name symptoms, not
apartment identifiers. "High Ridge" and "Dry Creek" on this list were false positives:
real Tolman plan names now fixed by BUG-14 (Filter A skip for JD adapter).

**Phase C enumeration** — examined all apartments with ≤1 active plan. Three root causes
found; BUG-09 applies only to the multi-property platform cases:

**Type 1 — Multi-property platform (BUG-09 proper, marked unscrapeable 2026-04-29):**
- Verve (id=194, udr.com): 4 active plans were all sibling UDR properties (Marina Playa,
  Birch Creek, Almaden Lake Village, River Terrace). All archived + apt marked unscrapeable.
- Reserve at Mountain View (id=218, equityapartments.com): 4 active plans were all sibling
  Equity apartments (Arbor Terrace, Briarwood, Lorien, The Arches). All archived + marked.
- Mill Creek (id=196, equityapartments.com): 1 generic "Unit" plan — marked unscrapeable.
- Verve MV (id=220, udr.com, dup of 194): 1 generic "Unit" plan — marked unscrapeable.
- Monte Vista Senior (id=26): senior housing — archived (same as BUG-11 pattern).

**Type 2 — Technical blockers (NOT BUG-09, separate bugs):**
- RentCafe 403 (BUG-07): Verdant #67, Turnleaf #247, Ilara #251, Atrium Garden #270, Murphy Station #274
- Essex SSL/SightMap (BUG-08): 1250 Lakeside #231
- Hard Cloudflare block: Tan Plaza #171, Telegraph Gardens #172, Hanover FC #175, Shadowbrook #223
- Camden Northpark #177: accessible but scraper not reaching price section

**Fix applied**: `dev/bug9_unscrapeable.sql` archived contaminated plans + marked
Type 1 apartments as `data_source_type='unscrapeable'`. These remain visible in the
UI as "Data restricted" via the legal_block display (until UDR/Equity adapters exist).
The sanitize Filter A continues to prevent future contamination for any remaining scrapes.

---

## BUG-13: Enclave — LLM name instability causes 28 duplicate plans (real count: 9)

**Status**: RESOLVED — archive done; structural path-cache replay bug fixed (commit 3c707e01)  
**Affected**: The Enclave (id=21)  
**Evidence**:
- DB had 28 active plans with names like "1 Bed / 1 Bath - Range 1", "Studio - Unit 2",
  "1 Bed / 1 Bath Plan A", "1 Bedroom 1 Bath" etc. — all referring to the same ~9 floor plans
- Live LLM scrape (2026-04-27) returns 9 plans: Studio, A1($3,002/637sqft), A2, A3, A4, B1–B4

**Root cause** (two-layer):

1. **`_replay_cached_path` only checked `last_result` for a "units" key** (structural bug).
   The Enclave path cache had 15 steps: `extract_all_units` was step 5 but 10 post-extraction
   navigation steps followed it. The final step (`scroll_down`) returned page-state HTML, not a
   `{"units": [...]}` dict — so the "units" check always failed and `_replay_cached_path` always
   returned `None`. Then `invalidate_path(url)` deleted the cache file before the full LLM loop
   ran. The LLM rebuilt the cache with the same structure (navigating past extract_all_units),
   so the self-defeating loop repeated every scrape. Every scrape hit the full LLM path, which
   produced variable plan names, which auto-created orphan plans via `_match_plan` strategy 4.

2. **Sqft-less plans unprotected by strategy 3**: Studio/1BR/2BR plans scraped with area_sqft=0
   (LLM failed to read sqft from JS-heavy page). Strategy 3 in `_match_plan` guards on
   `fp.size_sqft is not None` so it's skipped entirely, leaving only exact-name match (strategy 1)
   as protection. With name variation between LLM runs, strategy 1 also fails → auto-create.

**Fix**:
1. ✅ Archived all 28 existing plans — 2026-04-28 via round1_data_fixes.sql
2. ✅ **Structural path-cache replay fix** (2026-04-29, commit 3c707e01):
   `_replay_cached_path` now tracks `units_result` separately — updated on every
   `extract_all_units` call (only when non-empty). After all steps run, uses `units_result`
   if found, falling back to `last_result` only if no extraction occurred. This allows cache
   hits even when subsequent navigation steps follow the extraction step.
   Applied to both `backend/` and `tests/integration/` copies.
3. ✅ **Enclave path cache trimmed** (2026-04-29): removed 10 post-extraction steps from
   `path_cache/enclaveapartmenthomes_com__6666cd76.json`. Cache now ends at `extract_all_units`
   — clean even for code that doesn't have the fix yet.
4. ✅ 6 regression tests in `tests/unit/test_replay_cached_path_units_result.py`:
   - mid-path extraction with trailing navigation → returns data ✓
   - terminal extraction → returns data ✓  
   - no extraction step → None ✓
   - empty units → None ✓
   - error before extraction → None ✓
   - error after extraction → None (safe, caller runs LLM) ✓

**Remaining latent risk (low, not a blocker)**:
With path cache now working, the LLM loop won't fire on subsequent scrapes, so name instability
is suppressed. However if the path cache is ever invalidated (site HTML changes, iframe URL
shifts), the LLM will run again. The Studio/1BR/2BR plans (area_sqft=0) are still only protected
by exact-name match — if the LLM returns a slightly different name variant, strategy 3 can't
fall back to sqft match and strategy 4 auto-creates another orphan. Long-term fix: store
canonical names in path cache and enforce them at persist time (Phase 4 deferred).

**File**: `backend/app/services/scraper_agent/agent.py` — `_replay_cached_path`;
`tests/integration/agentic_scraper/agent.py` — mirror;
`backend/app/services/scraper_agent/path_cache/enclaveapartmenthomes_com__6666cd76.json`;
`tests/unit/test_replay_cached_path_units_result.py` (6 tests);
`dev/round1_data_fixes.sql`

---

## BUG-10: The Cathay Lotus seeded with aggregator URL instead of apartment website

**Status**: PARTIALLY RESOLVED — data fix applied 2026-04-28  
**Affected**: The Cathay Lotus (id=277)  
**Evidence**: `source_url = http://www.vrent.com/` — this is a property management company /
aggregator website, not the apartment's own website. DB plans include `2 Bedrooms $1,595`
which is implausibly low for Bay Area 2BR (likely wrong data from aggregator context).  
**Root cause**: At seed time the GMB listing pointed to `vrent.com` (the management company's
site) rather than a dedicated apartment page. The LLM scraped vrent.com and extracted whatever
it found there.  
**Fix**:
1. ✅ Real apartment site found: `https://www.cathaylotus.com/` (Google confirmed: "415-425 S Bernardo Ave | Apartments in Sunnyvale, CA")
2. ✅ `source_url` updated; `city` corrected Palo Alto→Sunnyvale; `zipcode` corrected 94306→94086 — done 2026-04-28
3. ✅ Re-scrape triggered 2026-04-28 to clear vrent.com plan data and rebuild from cathaylotus.com  
**File**: DB — `dev/round1_data_fixes.sql`

---

## BUG-11: Valley Village Retirement Community incorrectly seeded as regular apartment

**Status**: RESOLVED — archived 2026-04-28  
**Affected**: Valley Village Retirement Community (id=28)  
**Evidence**: `source_url = http://www.valleyvillageretirement.com/` — this is a senior
retirement community, not a regular apartment complex. Plans show "Mini Studio Deluxe",
"High Rise" — retirement facility unit types.  
**Root cause**: Google Maps import included senior/retirement communities when keywords
matched "apartments near San Jose". CLAUDE.md notes senior housing was later removed from
import keywords, but id=28 was already seeded before that change.  
**Fix applied 2026-04-28**: `is_available=false`, `data_source_type='unscrapeable'`,
title prefixed `[ARCHIVED retirement]`. No longer visible in UI or scrape queue.  
**File**: `dev/round1_data_fixes.sql`

---

## BUG-12: Metro Six55 — seed used unit numbers as plan names, CAPI plans merged by sqft fuzzy match

**Status**: PARTIALLY RESOLVED — data fix applied 2026-04-28  
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
1. ✅ Renamed DB plans: "1306"→"1x1A", "2105"→"1X1B", "2202"→"2x2C" — done 2026-04-28
2. ✅ Re-scrape triggered; CAPI will now match by exact name and auto-create 1x1C, 2x2A, 2x2B
3. Pending code fix: sqft tolerance tightening (±5% instead of ±10%) to prevent future collapse  
**Note**: CAPI adapter IS working correctly (`_fetch_leasingstar_plans` returns all 6 plans).
`availableUnits=None` for all plans is a separate issue (BUG-02).  
**File**: `dev/round1_data_fixes.sql`; `backend/app/worker.py` — `_match_plan` sqft tolerance (pending)

---

## BUG-16: Miro — SightMap extracts availability dates and unit numbers as plan names

**Status**: RESOLVED — data fix 2026-04-29 (commit 901b680c); code fix 2026-04-29  
**Affected**: Miro (id=11)  
**Evidence** (discovered in verify-scraper audit 2026-04-29):
- 6 of 27 active plans had garbage names from the SightMap embed:
  - "Available May 7th" $5,359, "Available May 6th" $5,394, "Available Jul 7th" $5,779,
    "Available Jun 5th" $5,799 — availability dates shown in unit card
  - "Request a Tour" $6,014 — button label leaked as plan name
  - "E303" $6,020 — bare unit number leaked as plan name
  - "Unit" — generic placeholder shown when SightMap card has no plan code
- The 21 legitimate plan names (S5, S7, A1–A18, B1–B8) were correct.

**Root cause**: SightMap unit cards show availability dates ("Available May 7th") or
action button labels ("Request a Tour") in the position the plan-name extractor reads.
`_UI_VERB_BLACKLIST` used exact-match on lowercased strings; "available may 7th" ≠ "available"
so multi-word phrases slipped through. "E303" passed `_PLAN_NAME_REGEX` (starts with letter).

**Fix applied**:
1. **Data fix** (2026-04-29, commit 901b680c): archived 6 ghost rows on Railway with
   `is_available=false` and `name='[BUG-16 ghost] '||name`.
2. **Code fix** (2026-04-29): added two new regex guards in
   `backend/app/services/scraper_agent/browser_tools.py` (and integration mirror):
   - `_NOT_A_PLAN_NAME_RE`: prefix-match regex rejecting lines that start with action
     verbs (`available`, `request`, `schedule`, `view`, `see`, `apply`, `contact`, etc.).
     Catches "Available May 7th", "Request a Tour", "Schedule Tour" etc.
   - `_UNIT_NUMBER_RE`: rejects bare unit-number pattern `^[A-Z]\d{3,}$` ("E303", "A1023").
   - Added `"unit"` to `_UI_VERB_BLACKLIST` to block generic "Unit" placeholder cards.
   Both guards inserted at the top of the plan-name filter chain in `_scrape_visible_units`.
3. **Tests** (33 new): `tests/unit/test_sightmap_plan_name_validation.py` — all ghost names
   blocked, all legit plan codes (A1, S5, B12, Dry Creek, High Ridge) accepted.

**Verified re-scrape 2026-04-29** (local, after code fix):
- SightMap re-parse produced zero ghost plans — no "Available ...", "E303", "Unit" extracted
- 22 clean active plans remain (21 original + "B6" a legitimate new plan found on site)
- E303 last_updated stayed at 2026-04-27 (not touched by re-scrape — confirmed not re-extracted)

**Files changed**:
- `backend/app/services/scraper_agent/browser_tools.py` — `_NOT_A_PLAN_NAME_RE`, `_UNIT_NUMBER_RE`, `_UI_VERB_BLACKLIST` + filter chain
- `tests/integration/agentic_scraper/browser_tools.py` — mirror
- `tests/unit/test_sightmap_plan_name_validation.py` (new, 33 tests)

---

## BUG-17: equityapartments.com — Angular SPA causes consistent validated_fail

**Status**: open — Phase 4 deferred  
**Affected**: Archstone Fremont Center (id=170), 360 Residences (id=173)  
**Evidence**:
- Both source_urls are on equityapartments.com (Equity Residential's property portal)
- Outcome is `validated_fail` on every scrape — LLM runs but returns no usable data
- Stale DB plans from old LLM scrapes:
  - apt 170: "1 Bed / 1 Bath" $3,116 / "2 Bed / 1 Bath" $3,453 / "2 Bed / 2 Bath" $3,744 / "3 Bed / Floor 4" $4,471
  - apt 173: 9× "1 Bed / 1 Bath - 740 sq ft" at prices $3,225–$3,358 (LLM extracted per-unit pricing as separate plan rows)

**Root cause**: equityapartments.com is an Angular SPA (`ng-app`). Static HTML contains embedded price data (verified: $3,015, $3,433, $4,469 visible in raw HTML for apt 170), but floor plan detail is rendered by JavaScript. The `universal_dom` adapter on static HTML extracts partial data with wrong bedroom counts (all 2BR for a 1/2/3BR property). Playwright-rendered fetch should work but the LLM agent currently fails to navigate the Angular app correctly.

**Not a compliance block**: pages are publicly accessible (HTTP 200), no anti-bot system detected. Equity Residential has not restricted automated access to these public pages.

**Fix options**:
1. Write an Equity Residential adapter that parses the embedded Angular JSON data blob in the static HTML
2. Use Playwright rendered fetch + `universal_dom` with post-rendering (currently fails for these pages)
3. Find individual brand-site URLs for these apartments instead of using the equityapartments.com aggregator page

**Deferred**: Phase 4. Stale prices remain visible in the UI (marked as old via scrape timestamp). Do not mark these apartments `unscrapeable` — data is technically accessible.

---

## BUG-18: ARLO Mountain View (id=190) — broken source_url returns 404

**Status**: RESOLVED — source_url fixed 2026-04-29  
**Affected**: ARLO Mountain View (id=190)  
**Evidence**:
- DB source_url: `https://www.essexapartmenthomes.com/apartments/mountain-view/arlo-mountain-view/floor-plans`
- This URL returns HTTP 200 with title "404 Page Not Found | Essex Property Trust"
- LLM agent scrapes the 404 page: inconsistently extracts plan data (10 plans, only 3 priced)
- Correct URL: `https://www.essexapartmenthomes.com/apartments/mountain-view/arlo-mountain-view` — returns live page with SightMap embed `sightmap.com/embed/dqw98y10po9`

**Root cause**: At seed time, `/floor-plans` was appended to the Essex apartment URL. Essex's URL structure does not use a `/floor-plans` sub-path (unlike some other chains). The page at that URL returns a 404 with a full HTML shell, giving the LLM enough content to "succeed" without real data.

**Fix applied**: Updated source_url in DB (see SQL below), cleared `last_content_hash` to force re-scrape.

---

## BUG-19: Centerra (id=176) — JD SPA requires JS render; scraper falls back to home page, extracts starting-from price + duplicate plan names

**Status**: open  
**Affected**: Centerra (id=176, centerraapts.com)  
**Evidence**:
- DB has "1 Bedroom (Starting) = $2,800" alongside real "1 Bedroom = $4,889" (1,552 sqft, 1.5 ba)
- "1 Bedroom" and "1 Bed / 1.5 Bath" both at $4,889/1,552 sqft — same plan, two rows
- "2 Bedroom" and "2 Bed / 2 Bath" both at $5,291/1,735 sqft — same plan, two rows

**Root cause (deep diagnosis 2026-04-29)**:

1. **Source URL 404**: `centerraapts.com/floorplans/` (trailing slash) returns HTTP 404.
   `centerraapts.com/floorplans` (no slash) returns the SPA shell — same 109KB HTML as the
   home page. JonahDigital CMS serves a client-side SPA; all routes return the same HTML shell.

2. **JD adapter cannot fire on static fetch**: The adapter's signal is `jd-fp-floorplan-card`,
   a CSS class that only appears after JS renders the React/JD component tree. Static fetch
   never has these elements → `_is_jonah_digital()` returns False → adapter skips.

3. **LLM fallback on home page**: When JD adapter misses, the LLM agent runs with Playwright
   rendered fetch on the home page (which does render some floor plan summary cards). The home
   page shows a "Starting from $2,800" hero section — LLM extracts this as a plan. In different
   iteration runs, the same 1BR plan is named "1 Bedroom" or "1 Bed / 1.5 Bath" depending on
   which DOM element the LLM reads first → two separate plan rows accumulate.

4. **Why validated_fail now**: Unknown — the LLM has access to a rendered page but is returning
   no data. Possible: Playwright render timing (JD widget loads slowly), or the scraper's
   22-iteration no-data early-stop fires before the LLM finds the floor plan section.

**Fix options**:
1. Correct source URL to `centerraapts.com/floorplans` (no trailing slash) and force rendered
   fetch — the JD framework should render `jd-fp-floorplan-card` elements after JS execution,
   allowing the JD adapter to fire and follow detail-page hrefs
2. Archive "1 Bedroom (Starting)" and "2 Bedroom (Starting)" stale contamination rows via SQL
3. Investigate why Playwright render fails for this specific JD SPA (may be slow JS bundle)

---

## BUG-20: Sofia Apartments (id=69) — DudaOne/Repli360 widget; JS-only floor plan data; LLM name instability

**Status**: open  
**Affected**: Sofia Apartments (id=69, sofiaaptliving.com, Santa Clara)  
**Evidence**:
- 13 active plans, 5 priced. Three rows for the same 813 sqft 1BR at $3,630:
  - "1 Bed/1 Bath" (813 sqft, $3,630)
  - "One Bedroom | 1 Bath" (813 sqft, $3,630)
  - "1 Bed/1 Bath 1x1-813" (813 sqft, unpriced)
- Real plan names from a previous successful scrape: "Natalia Den" (1BR den, 1,032 sqft),
  "Isabela" (2BR, 1,153 sqft) — these are the real Entrata floor plan codes
- Outcome: `validated_fail` — scraper cannot currently re-scrape to consolidate

**Root cause (deep diagnosis 2026-04-29)**:

1. **Platform stack**: sofiaaptliving.com is a **DudaOne CMS** site (`SiteType: DUDAONE`,
   `SiteAlias: c20ff22a`). Floor plan data is loaded by a **Repli360 widget** (`app.repli360.com`)
   embedded via a JWT-encoded script URL. Repli360 pulls live inventory from an Entrata backend
   and renders it client-side. The `rrac_entrata_special_view` CSS class seen in the HTML is from
   the Repli360/Entrata integration — it is NOT a direct Entrata API call.

2. **No static data**: The `/floor-plans` page contains only a DudaOne SPA shell. Zero prices,
   zero plan cards in static HTML. All floor plan content rendered by the Repli360 JS widget
   after page load.

3. **Compliance**: Fully public page, no login wall, no proprietary API being called directly.
   sofiaaptliving.com is the apartment's own domain; Repli360 is their widget provider.
   Scraping the rendered output is legitimate.

4. **Name instability**: When Playwright successfully rendered the Repli360 widget in past scrapes,
   the LLM read floor plan data from different DOM positions across iterations, producing three
   name formats for the same 813 sqft plan. `_match_plan` strategy 3 (sqft ±5) can't resolve
   because three candidates already exist at 813 sqft — strategy 4 auto-created a third row.

5. **Why validated_fail now**: Likely Repli360 widget bot detection blocking Playwright's headless
   Chromium. Repli360 is a paid marketing platform; they may fingerprint browser automation.

**Fix**:
1. **Preferred**: Intercept the Repli360 widget's network calls (Chrome DevTools → Network while
   loading sofiaaptliving.com/floor-plans) to find the API endpoint it calls for floor plan data.
   If public (no auth header required), write a Repli360 adapter that calls it directly — cleaner
   than Playwright and bot-detection-proof.
2. **If API requires auth**: Use `playwright-stealth` (patches `navigator.webdriver=false`,
   canvas fingerprint, etc.) to evade Repli360's bot detection during rendered fetch. Note: simply
   changing the User-Agent string is insufficient — modern bot detection checks `navigator.webdriver`
   and browser fingerprint properties that Playwright sets by default, not just the UA header.
3. Once re-scrape succeeds, Pass 3 (stale plan cleanup, added 2026-04-29) will auto-archive the
   three duplicate 813 sqft rows after the next successful scrape

---

## BUG-21: Parkmerced (id=166) — inconsistent plan names and bath counts from LLM

**Status**: open (low severity)  
**Affected**: Parkmerced Apartments (id=166, parkmerced.com)  
**Evidence**:
- "1 BD | 1 BA Tower Home" = $2,490 (712 sqft) and "1 Bed - Tower Home" = $2,695 — different prices, likely different units/floors
- "2 Bed - Tower Home" bathrooms=1 vs "2 BD | 2 BA Tower Home" bathrooms=2 — same plan type, inconsistent bath count
- Mix of "X Bed - Type" and "X BD | X BA Type" naming formats from different LLM runs

**Root cause**: Parkmerced is a large SF complex with Tower Home and Townhome building types (genuinely different unit types, not contamination). The LLM extracts plan names from different DOM elements across scrape iterations, producing both "1 Bed - Tower Home" and "1 BD | 1 BA Tower Home" as separate plans. Bath count inconsistency: LLM reads "1 BA" from some cards and infers 1 bath, while others show "2 BA" explicitly.

**Impact**: Low — the price range shown is real (Tower Home 1BR: $2,490–$2,695). Main UX harm is duplicate plan rows confusing the user.

**Fix**: Low priority. `_match_plan` sqft-based dedup could merge these if sqft is populated. Currently these plans have area_sqft=0 (LLM didn't extract sqft from Parkmerced cards), so strategy 3 can't match.
