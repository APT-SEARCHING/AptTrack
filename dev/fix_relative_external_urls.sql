-- ============================================================
-- Batch 3: Fix relative external_url on plans
--
-- Root cause: scraper stored relative paths (e.g. /floorplans/1-bedroom/mission)
-- instead of absolute URLs. Frontend renders href={plan.external_url} directly;
-- relative paths resolve to apttrack-production.up.railway.app/floorplans/...
-- → 404 on every deep-link click.
--
-- Fix: prepend scheme+host extracted from apartment.source_url.
-- Handles both /path (leading slash) and path (no slash) forms.
--
-- STATUS: Already applied 2026-04-24 during Phase 1 data-fix session.
-- Verified post-run: SELECT count(*) WHERE external_url NOT LIKE 'http%' = 0.
-- Running again is a safe no-op (WHERE clause matches 0 rows).
-- File retained for audit trail and reproducibility.
--
-- Affected apartments at time of fix:
--   apt 9  The Asher Fremont       (12 plans)
--   apt 4  Atlas                   (8 plans)
--   apt 24 Redwood Seniors         (4 plans)
--   apt 28 Valley Village          (4 plans)
--   apt 20 The James               (4 plans — host mismatch noted, see below)
--   apt 57 33 8th at Trinity Place (4 plans)
--   apt 157 Pasatiempo             (2 plans)
--   apt 33 Hacienda Creek          (1 plan)
--
-- Known remaining issue (not fixed here, Week 2):
--   apt 20 The James: source_url host is jamesliving.com but floor-plan
--   URLs live on a different hostname. external_url now absolute but still
--   404s. Requires manual source_url correction.
-- ============================================================

BEGIN;

-- A: Fix relative paths → absolute URL
WITH base AS (
    SELECT a.id AS apt_id,
           regexp_replace(a.source_url, '^(https?://[^/]+).*$', '\1') AS origin
    FROM apartments a
)
UPDATE plans p
SET external_url = base.origin ||
    (CASE WHEN p.external_url LIKE '/%' THEN p.external_url
          ELSE '/' || p.external_url END)
FROM base
WHERE p.apartment_id = base.apt_id
  AND p.external_url IS NOT NULL
  AND p.external_url != ''
  AND p.external_url NOT LIKE 'http%';

-- B: Null out empty-string external_url (was plan 297, The Ryden)
UPDATE plans
SET external_url = NULL
WHERE external_url = '';

COMMIT;
