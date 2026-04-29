-- Round 1 data fixes: BUG-10, 11, 12, 13, 14B, 15
-- Generated 2026-04-28. Reviewed and approved before run.
-- Run against Railway: psql $RAILWAY_DATABASE_URL -f dev/round1_data_fixes.sql

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- BUG-11: Valley Village Retirement Community (#28)
-- Wrong type — senior retirement community wrongly seeded as regular apartment.
-- Archive so it no longer shows in the UI or scrape queue.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE apartments
SET is_available      = false,
    data_source_type  = 'unscrapeable',
    title             = '[ARCHIVED retirement] ' || title,
    description       = COALESCE(description || E'\n\n', '') ||
                        '[2026-04-28] Archived: senior retirement community wrongly seeded '
                        'as regular apartment. Per BUG-11 in scraper-bugs.md.',
    updated_at        = now()
WHERE id = 28;

-- ─────────────────────────────────────────────────────────────────────────────
-- BUG-15: Astella (#6) — fix bedrooms classification
-- A-series = 1BR, B-series = 2BR, C-series = 3BR, S-series = Studio (0)
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE plans SET bedrooms = 1, updated_at = now()
    WHERE apartment_id = 6 AND name ~ '^A\d';
UPDATE plans SET bedrooms = 2, updated_at = now()
    WHERE apartment_id = 6 AND name ~ '^B\d';
UPDATE plans SET bedrooms = 3, updated_at = now()
    WHERE apartment_id = 6 AND name ~ '^C\d';
UPDATE plans SET bedrooms = 0, updated_at = now()
    WHERE apartment_id = 6 AND name ~ '^S\d';

-- ─────────────────────────────────────────────────────────────────────────────
-- BUG-12: Metro Six55 (#156) — rename unit-number plan names to plan codes
-- LeaseStar CAPI returns codes 1x1A / 1X1B / 2x2C; seed used unit numbers.
-- Missing plans (1x1C, 2x2A, 2x2B) will be auto-created on next scrape.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE plans SET name = '1x1A', updated_at = now()
    WHERE apartment_id = 156 AND name = '1306';
UPDATE plans SET name = '1X1B', updated_at = now()
    WHERE apartment_id = 156 AND name = '2105';
UPDATE plans SET name = '2x2C', updated_at = now()
    WHERE apartment_id = 156 AND name = '2202';

-- ─────────────────────────────────────────────────────────────────────────────
-- BUG-14B: The Tolman (#7) — archive orphan legacy generic plans
-- 'Studio' and '1 Bed / 1 Bath' were LLM seed-time names (NULL sqft).
-- JD adapter now produces named plans (Dry Creek, Vista Peak, etc.).
-- _match_plan can't reconcile them → stale prices visible forever.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE plans
SET is_available = false,
    name         = '[orphan legacy] ' || name,
    updated_at   = now()
WHERE apartment_id = 7
  AND name IN ('Studio', '1 Bed / 1 Bath')
  AND area_sqft IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- BUG-13: The Enclave (#21) — archive all 28 duplicate plans
-- LLM name instability produced a new plan string on every scrape.
-- Next scrape will auto-create the correct ~9 plans (A1-A4, B1-B4, Studio).
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE plans
SET is_available = false,
    name         = '[archived dup variant] ' || name,
    updated_at   = now()
WHERE apartment_id = 21 AND is_available = true;

-- ─────────────────────────────────────────────────────────────────────────────
-- BUG-10: Cathay Lotus (#277) — Option A: real URL found
-- cathaylotus.com confirmed via Google search: "415-425 S Bernardo Ave |
-- Apartments in Sunnyvale, CA" matches DB address.
-- Also fixing: city wrongly stored as 'Palo Alto' (address is Sunnyvale).
-- Plans with implausible prices ($1,595 for 2BR) will clear on re-scrape.
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE apartments
SET source_url   = 'https://www.cathaylotus.com/',
    city         = 'Sunnyvale',
    zipcode      = '94086',
    description  = COALESCE(description || E'\n\n', '') ||
                   '[2026-04-28] source_url updated from vrent.com aggregator to '
                   'cathaylotus.com (real apartment site). City corrected Palo Alto→Sunnyvale. '
                   'Per BUG-10 in scraper-bugs.md.',
    updated_at   = now()
WHERE id = 277;

-- ─────────────────────────────────────────────────────────────────────────────
-- Verification
-- ─────────────────────────────────────────────────────────────────────────────
SELECT a.id, a.title, a.is_available, a.data_source_type, a.city,
       (SELECT count(*) FROM plans WHERE apartment_id = a.id AND is_available = true) as active_plans
FROM apartments a
WHERE id IN (28, 6, 277, 156, 7, 21)
ORDER BY id;

COMMIT;
