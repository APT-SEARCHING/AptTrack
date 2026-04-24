-- ============================================================
-- Railway DB cleanup: duplicates, numeric plan names, geo data
-- Run via: psql $DATABASE_PUBLIC_URL -f dev/fix_railway_duplicates.sql
-- ============================================================

BEGIN;

-- ---------------------------------------------------------------
-- 1. Copy lat/lng from google_places records to scraper records
-- ---------------------------------------------------------------
UPDATE apartments SET latitude=37.330937999999996, longitude=-121.90528040000001 WHERE id=280; -- Avalon at Cahill Park
UPDATE apartments SET latitude=37.3975517,          longitude=-122.08661670000001  WHERE id=282; -- Avalon Mountain View
UPDATE apartments SET latitude=37.332536399999995,  longitude=-121.91242869999999  WHERE id=284; -- Avalon on the Alameda
UPDATE apartments SET latitude=37.388618199999996,  longitude=-121.9937851         WHERE id=283; -- Avalon Silicon Valley
UPDATE apartments SET latitude=37.3991533,          longitude=-122.107092          WHERE id=288; -- Avalon Towers
UPDATE apartments SET latitude=37.3895251,          longitude=-122.07120739999999  WHERE id=289; -- eaves Creekside
UPDATE apartments SET latitude=37.398646899999996,  longitude=-122.07035909999998  WHERE id=279; -- eaves Middlefield
UPDATE apartments SET latitude=37.4022876,          longitude=-121.88095870000001  WHERE id=281; -- eaves San Jose
UPDATE apartments SET latitude=37.3855781,          longitude=-122.0845413         WHERE id=295; -- ARLO Mountain View

-- ---------------------------------------------------------------
-- 2. Migrate plans from old Avalon Willow Glen (ID=12) to new (ID=278)
--    Old: scraper_avaloncommunities.com (hostname-only slug, pre-fix)
--    New: scraper_2e4492c01903893bff1c (full-path slug, correct)
-- ---------------------------------------------------------------
-- First delete the redundant "808" plan on ID=278 (covered by plan 313 on ID=12)
DELETE FROM plan_price_history WHERE plan_id=365;
DELETE FROM plans WHERE id=365;

-- Reassign all plans from old record to new record
UPDATE plans SET apartment_id=278 WHERE apartment_id=12;

-- Update plan_price_history rows that reference the moved plans (none needed — they follow plan_id)

-- ---------------------------------------------------------------
-- 3. Delete the old/duplicate apartment records (0-plan google_places + old hostname slug)
-- ---------------------------------------------------------------
-- google_places duplicates (all have 0 plans, confirmed no subscriptions/favorites)
DELETE FROM apartments WHERE id IN (82, 186, 73, 120, 191, 174, 188, 267);

-- Old hostname-only slug for Avalon Willow Glen (plans already migrated to ID=278)
DELETE FROM apartments WHERE id=12;

-- ARLO Mountain View google_places duplicate (scraper record ID=295 kept)
DELETE FROM apartments WHERE id=183;

-- ---------------------------------------------------------------
-- 4. Fix numeric-only plan names (sqft number used as plan name)
-- ---------------------------------------------------------------
-- Avalon Willow Glen
UPDATE plans SET name='1 Bed / 1 Bath - 808 sqft' WHERE id=365; -- already deleted above, no-op
-- eaves Mountain View at Middlefield
UPDATE plans SET name='Studio - 405 sqft'          WHERE id=366;
UPDATE plans SET name='Studio - 459 sqft'          WHERE id=367;
UPDATE plans SET name='1 Bed / 1 Bath - 648 sqft'  WHERE id=368;
UPDATE plans SET name='2 Bed / 2 Bath - 972 sqft'  WHERE id=369;

-- ---------------------------------------------------------------
-- 5. Fix "Apartments and Pricing for Verve" title
-- ---------------------------------------------------------------
UPDATE apartments SET title='Verve' WHERE title='Apartments and Pricing for Verve';

COMMIT;

-- Verify
SELECT a.id, a.title, COUNT(p.id) AS plans
FROM apartments a
LEFT JOIN plans p ON p.apartment_id = a.id
WHERE a.title ILIKE ANY(ARRAY['%avalon%','%eaves%','%arlo%','%verve%'])
GROUP BY a.id, a.title ORDER BY a.title;
