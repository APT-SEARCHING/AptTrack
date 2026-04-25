-- ============================================================
-- Batch 1: Archive Group B contaminated apartments
--
-- Root cause: old domain-only _slug() (pre-commit 6b7ad4e5) produced
-- "scraper_essexapartmenthomes.com" for ALL Essex properties. First
-- seeded property kept its source_url; later seeds only overwrote title.
-- Result: title = last-seeded building, source_url = first-seeded building.
--
-- Strategy: soft-archive only (no DELETE). Frontend filters by
-- is_available=false and data_source_type='unscrapeable'.
--
-- Subscription migration: plan_id=NULL unconditionally — kill-side plans
-- are from the wrong building and carry no meaningful data.
-- Verified: no subscriptions or favorites reference any kill-side apartment.
-- ============================================================

BEGIN;

-- ---------------------------------------------------------------
-- Pair B1: ARLO Mountain View
--   Keep: 190  essexapartmenthomes.com/.../mountain-view/arlo-mountain-view/floor-plans
--   Kill: 41   essexapartmenthomes.com/.../emeryville/essex-emeryville (WRONG PROPERTY)
--              35 plans are Essex Emeryville data, not ARLO
--   Kill: 222  arlo-mountain-view GMB UTM — dup of 190
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id IN (41, 222);

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 190] ' || title
WHERE id = 41;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 190] ' || title
WHERE id = 222;

-- ---------------------------------------------------------------
-- Pair B2: eaves Creekside
--   Keep: 206  avaloncommunities.com/.../mountain-view-apartments/eaves-creekside
--   Kill: 12   avaloncommunities.com/.../san-francisco-apartments/ava-south-market
--              47 plans are AVA South Market (SF) data, not eaves Creekside
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 12;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 206] ' || title
WHERE id = 12;

-- ---------------------------------------------------------------
-- Pair B3: Verve Mountain View
--   Keep: 220  udr.com/.../mountain-view/verve
--   Kill: 70   udr.com/.../redwood-city/starlight (WRONG PROPERTY)
--              13 plans are Starlight Redwood City data, not Verve MV
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 70;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 220] ' || title
WHERE id = 70;

-- ---------------------------------------------------------------
-- Pair B4: Crescent Village Apartments in San Jose
--   Keep: 209  irvinecompanyapartments.com/.../san-jose/crescent-village
--   Kill: 178  irvinecompanyapartments.com/.../sunnyvale/redwood-place (WRONG PROPERTY)
--              30 plans are Redwood Place (Sunnyvale) data, not Crescent Village
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 178;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 209] ' || title
WHERE id = 178;

-- ---------------------------------------------------------------
-- Pair B5: Pavona Apartments by Windsor
--   Keep: 205  windsorcommunities.com/.../pavona-apartments
--   Kill: 14   windsorcommunities.com/.../windsor-winchester (WRONG PROPERTY)
--              7 plans are Windsor Winchester data, not Pavona
-- ---------------------------------------------------------------
UPDATE plans
SET is_available = false,
    name         = '[archived dup] ' || name
WHERE apartment_id = 14;

UPDATE apartments
SET is_available     = false,
    data_source_type = 'unscrapeable',
    title            = '[archived dup of 205] ' || title
WHERE id = 14;

COMMIT;
