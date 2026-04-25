-- ============================================================
-- Batch 2: Archive Group A true duplicates (same building, two seed URLs)
--
-- Root cause: Google Maps GMB links and canonical /floor-plans URLs
-- seeded separately under the new path-based slug, producing two DB
-- rows for the same physical building.
--
-- Strategy: soft-archive kill side. Keep side retains all active plans.
-- Kill-side plans archived (is_available=false, name prefixed).
--
-- Subscription migration: verified no subscriptions or favorites on any
-- kill-side apartment. Sub 18 (Miro, cxmbill) is already on apt 11
-- (keeper) with plan 41 under apt 11 — no reassignment needed.
-- ============================================================

BEGIN;

-- ---------------------------------------------------------------
-- Pair A1: Avalon at Cahill Park
--   Keep: 181  .../avalon-at-cahill-park/floor-plans (canonical URL)
--   Kill: 195  .../avalon-at-cahill-park GMB UTM dup
--   Plans: 4 / 4 tied — canonical URL preferred
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 195;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 181] ' || title
WHERE id = 195;

-- ---------------------------------------------------------------
-- Pair A2: Avalon Mountain View
--   Keep: 183  .../avalon-mountain-view/floor-plans (canonical URL)
--   Kill: 200  .../avalon-mountain-view GMB UTM dup
--   Plans: 1 / 1 tied — canonical URL preferred
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 200;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 183] ' || title
WHERE id = 200;

-- ---------------------------------------------------------------
-- Pair A3: Avalon on the Alameda
--   Keep: 203  .../avalon-on-the-alameda GMB UTM (4 plans — more data)
--   Kill: 185  .../avalon-on-the-alameda/floor-plans (3 plans)
--   Plans: 4 > 3 — keeper has more plans
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 185;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 203] ' || title
WHERE id = 185;

-- ---------------------------------------------------------------
-- Pair A4: Avalon Silicon Valley
--   Keep: 182  .../avalon-silicon-valley/floor-plans (canonical URL)
--   Kill: 201  .../avalon-silicon-valley GMB UTM dup
--   Plans: 6 / 6 tied — canonical URL preferred
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 201;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 182] ' || title
WHERE id = 201;

-- ---------------------------------------------------------------
-- Pair A5: Avalon Towers on the Peninsula
--   Keep: 204  .../avalon-towers-on-the-peninsula GMB UTM (4 plans — more data)
--   Kill: 186  .../avalon-towers-on-the-peninsula/floor-plans (3 plans)
--   Plans: 4 > 3 — keeper has more plans
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 186;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 204] ' || title
WHERE id = 186;

-- ---------------------------------------------------------------
-- Pair A6: Avalon Willow Glen
--   Keep: 180  .../avalon-willow-glen/floor-plans (canonical URL)
--   Kill: 199  .../avalon-willow-glen GMB UTM dup
--   Plans: 1 / 1 tied — canonical URL preferred
--   Note: both have only 1 plan; re-scrape of 180 queued in Task 3
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 199;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 180] ' || title
WHERE id = 199;

-- ---------------------------------------------------------------
-- Pair A7: Miro
--   Keep: 11   rentmiro.com/floorplans (20 plans, subscription sub=18)
--   Kill: 246  rentmiro.com GMB UTM dup (17 plans)
--   Sub 18 (cxmbill, plan_id=41) already on apt 11 — no migration needed
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 246;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 11] ' || title
WHERE id = 246;

-- ---------------------------------------------------------------
-- Pair A8: Apex Milpitas
--   Keep: 216  .../milpitas/apex GMB (7 plans — more data)
--   Kill: 187  .../milpitas/apex/floor-plans (4 plans)
--   No subscriptions on either side
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 187;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 216] ' || title
WHERE id = 187;

-- ---------------------------------------------------------------
-- Pair A9: The Asher Fremont
--   Keep: 9    theasherfremont.com/floorplans (22 plans, 1-row-per-floor-plan,
--              has deep-link external_urls, correct plan granularity)
--   Kill: 283  theasherfremont.com path-cache rerun via prc_scrape.py
--              (42 rows = per-unit pollution: 7x "Blacow", 8x "Cherry", etc.
--               _match_plan scalar_one_or_none() would crash on next Celery run)
--   No subscriptions on either side
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 283;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 9] ' || title
WHERE id = 283;

-- ---------------------------------------------------------------
-- Pair A10: Sofia Apartments
--   Keep: 69   sofiaaptliving.com (10 plans)
--   Kill: 275  sofiaaptliving.com GMB UTM dup (2 plans)
--   No subscriptions on either side
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 275;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 69] ' || title
WHERE id = 275;

-- ---------------------------------------------------------------
-- Pair A11: The Marc, Palo Alto
--   Keep: 8    themarc-pa.com/.../floor-plans (5 plans, canonical URL)
--   Kill: 256  themarc-pa.com GMB UTM dup (2 plans)
--   No subscriptions on either side
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 256;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 8] ' || title
WHERE id = 256;

COMMIT;
