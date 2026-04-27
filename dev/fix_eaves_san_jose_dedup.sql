-- Fix: archive eaves San Jose (id=198, GMB UTM URL) as duplicate of id=179 (canonical /floor-plans URL)
-- Surfaced in scraper-price-audit-2026-04-25.md — missed in Group A dedup pass.
-- Zero subscriptions and favorites on 198 — no migration required.

BEGIN;

-- No subscriptions to migrate (confirmed 0), but included defensively
UPDATE price_subscriptions
SET apartment_id = 179,
    plan_id = NULL,
    baseline_price = (SELECT MIN(current_price) FROM plans
                      WHERE apartment_id = 179 AND is_available = true
                        AND current_price IS NOT NULL)
WHERE apartment_id = 198;

-- No favorites to migrate (confirmed 0), included defensively
UPDATE apartment_favorites
SET apartment_id = 179
WHERE apartment_id = 198;

-- Archive plans on kill side
UPDATE plans
SET is_available = false,
    name = '[archived dup] ' || name,
    updated_at = now()
WHERE apartment_id = 198;

-- Archive apartment with audit trail
UPDATE apartments
SET is_available = false,
    data_source_type = 'unscrapeable',
    title = '[ARCHIVED dup of 179] ' || title,
    updated_at = now()
WHERE id = 198;

-- Verify
SELECT id, title, is_available, data_source_type FROM apartments WHERE id IN (179, 198);

COMMIT;
