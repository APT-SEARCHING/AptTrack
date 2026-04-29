-- centerra_dedup.sql
-- Generated 2026-04-29 — BUG-19 fix for apt 176 (Centerra).
-- Archives stale / duplicate plans before re-scrape with corrected URL.
-- Pass 3 (stale-plan auto-unavailable) will also fire on re-scrape as safety net.
--
-- Background: centerraapts.com → liveatcenterra.com domain change.
-- JD adapter on liveatcenterra.com/floorplans/ returns 95 clean named plans.
-- After re-scrape:
--   - "1 Bedroom" (424) → sqft-matched to T2 by _match_plan strategy 3 → renamed T2
--   - "L/W T8"   (1252) → exact-name matched by strategy 1 → updated beds=2 correctly
--   - All other archived plans → stay unavailable (Pass 3 won't reactivate them)

-- ============================================================================
-- A. Archive starting-from contamination plans
-- ============================================================================

UPDATE plans
SET is_available = false
WHERE apartment_id = 176
  AND id IN (468, 469);
-- 468  "1 Bedroom (Starting)"  $2,800  beds=1 sqft=0  — overview price contamination
-- 469  "2 Bedroom (Starting)"  $5,300  beds=2 sqft=0  — overview price contamination

-- ============================================================================
-- B. Archive duplicate 1BR plan (keep id=424 for sqft-based re-match)
-- ============================================================================

UPDATE plans
SET is_available = false
WHERE apartment_id = 176
  AND id = 420;
-- 420  "1 Bed / 1.5 Bath"  $4,889  beds=1 sqft=1552
-- Keep 424 "1 Bedroom" — same beds+sqft, JD strategy 3 will rename to "T2"

-- ============================================================================
-- C. Archive duplicate 2BR plans (keep id=1252 "L/W T8" for exact-name match)
-- ============================================================================

UPDATE plans
SET is_available = false
WHERE apartment_id = 176
  AND id IN (421, 425);
-- 421  "2 Bed / 2 Bath"  $5,291  beds=2 sqft=1735  — stale generic name
-- 425  "2 Bedroom"       $5,291  beds=2 sqft=1735  — stale generic name
-- Keep 1252 "L/W T8" — JD exact-name match on re-scrape, corrects beds to 2

-- ============================================================================
-- D. Archive zero-sqft NULL-price 3BR plan
-- ============================================================================

UPDATE plans
SET is_available = false
WHERE apartment_id = 176
  AND id = 470;
-- 470  "3 Bedroom"  NULL price  beds=3 sqft=0  — JD will recreate if units available

-- ============================================================================
-- E. URL fix for apt 176 — centerraapts.com → liveatcenterra.com
-- ============================================================================

UPDATE apartments
SET source_url       = 'https://liveatcenterra.com/floorplans/',
    last_content_hash = NULL
WHERE id = 176;

-- ============================================================================
-- F. Verify state after archive
-- ============================================================================

SELECT id, name, bedrooms, bathrooms, area_sqft, current_price, is_available
FROM plans
WHERE apartment_id = 176
ORDER BY is_available DESC, bedrooms, area_sqft;
