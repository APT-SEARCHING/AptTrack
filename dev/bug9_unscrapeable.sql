-- BUG-09 Phase C: mark multi-property-platform apartments unscrapeable.
-- Generated 2026-04-29. Run against Railway after review.
--
-- These apartments have source_url pointing to multi-property platform pages
-- (UDR.com, EquityApartments.com). The scraper LLM extracts sibling property
-- names as floor plans; sanitize Filter A correctly drops them, but real
-- per-apartment plan data is not reachable without a dedicated platform adapter.
-- Pre-sanitize contaminated rows are archived here.
--
-- Type 1 (multi-property platform):  194, 196, 218, 220
-- Type 3 (senior/wrong category):     26

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- apt 194: Verve (UDR) — 4 active plans are sibling UDR properties
-- "Almaden Lake Village", "Birch Creek", "Marina Playa", "River Terrace"
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE apartments
SET data_source_type = 'unscrapeable',
    description = COALESCE(description || E'\n\n', '') ||
                  '[2026-04-29] Marked unscrapeable: source_url (udr.com) is a '
                  'multi-property platform page. LLM extracts sibling UDR property '
                  'names instead of Verve floor plans. Real pricing requires a UDR '
                  'platform adapter. Per BUG-09 in scraper-bugs.md.',
    updated_at = now()
WHERE id = 194;

UPDATE plans
SET is_available = false,
    name = '[BUG-09 contamination] ' || name,
    updated_at = now()
WHERE apartment_id = 194 AND is_available = true;

-- ─────────────────────────────────────────────────────────────────────────────
-- apt 218: Reserve at Mountain View (Equity) — 4 active plans are sibling
-- Equity apartments ("Arbor Terrace", "Briarwood", "Lorien", "The Arches")
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE apartments
SET data_source_type = 'unscrapeable',
    description = COALESCE(description || E'\n\n', '') ||
                  '[2026-04-29] Marked unscrapeable: source_url (equityapartments.com) '
                  'is a multi-property platform page. LLM extracts sibling Equity '
                  'property names instead of Reserve floor plans. Real pricing requires '
                  'an Equity platform adapter. Per BUG-09 in scraper-bugs.md.',
    updated_at = now()
WHERE id = 218;

UPDATE plans
SET is_available = false,
    name = '[BUG-09 contamination] ' || name,
    updated_at = now()
WHERE apartment_id = 218 AND is_available = true;

-- ─────────────────────────────────────────────────────────────────────────────
-- apt 196: Mill Creek (Equity) — 1 generic "Unit" plan, no real data
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE apartments
SET data_source_type = 'unscrapeable',
    description = COALESCE(description || E'\n\n', '') ||
                  '[2026-04-29] Marked unscrapeable: source_url (equityapartments.com). '
                  'Equity platform adapter needed. Per BUG-09 in scraper-bugs.md.',
    updated_at = now()
WHERE id = 196;

UPDATE plans
SET is_available = false,
    name = '[BUG-09 contamination] ' || name,
    updated_at = now()
WHERE apartment_id = 196 AND is_available = true;

-- ─────────────────────────────────────────────────────────────────────────────
-- apt 220: Verve MV (UDR duplicate of 194) — 1 generic "Unit" plan
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE apartments
SET data_source_type = 'unscrapeable',
    description = COALESCE(description || E'\n\n', '') ||
                  '[2026-04-29] Marked unscrapeable: source_url (udr.com), duplicate '
                  'record of apt 194 (Verve). UDR platform adapter needed. Per BUG-09.',
    updated_at = now()
WHERE id = 220;

UPDATE plans
SET is_available = false,
    name = '[BUG-09 contamination] ' || name,
    updated_at = now()
WHERE apartment_id = 220 AND is_available = true;

-- ─────────────────────────────────────────────────────────────────────────────
-- apt 26: Monte Vista Senior — senior housing, should be archived (BUG-11 pattern)
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE apartments
SET is_available = false,
    data_source_type = 'unscrapeable',
    title = '[ARCHIVED senior] ' || title,
    description = COALESCE(description || E'\n\n', '') ||
                  '[2026-04-29] Archived: senior apartment community outside AptTrack '
                  'scope. Same pattern as BUG-11 (Valley Village). Plans show no price.',
    updated_at = now()
WHERE id = 26;

-- ─────────────────────────────────────────────────────────────────────────────
-- Verification
-- ─────────────────────────────────────────────────────────────────────────────
SELECT a.id, a.title, a.is_available, a.data_source_type,
       (SELECT count(*) FROM plans WHERE apartment_id=a.id AND is_available=true) as active_plans
FROM apartments a
WHERE a.id IN (26, 194, 196, 218, 220)
ORDER BY a.id;

COMMIT;
