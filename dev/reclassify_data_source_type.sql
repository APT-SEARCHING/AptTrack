-- reclassify_data_source_type.sql
-- Generated 2026-04-29 as part of pre-dogfood Step 2 cleanup.
-- Approved deviations from original step plan:
--   apt 270 (Atrium Garden): stays brand_site — RentCafe gzip bug (engineering,
--     not policy). Gzip fix applied in rentcafe.py; re-scrape will succeed.
--   apt 175 (Hanover FC): unscrapeable (not legal_block) — domain parked/sold,
--     operator website no longer exists. Distinct from anti-bot policy cases.
-- Run blocks A-D in order. Each is independently safe.
-- ============================================================================

-- ============================================================================
-- A. Equity/Essex URL fixes — 3 apts going from unscrapeable/wrong-url → brand_site
--    All verified 2026-04-29 with EquityAdapter (196, 218) and SightMap (173).
-- ============================================================================

-- apt 196: Mill Creek Apartments (Milpitas) — was unscrapeable, now has working
-- equityapartments.com detail page with ea5.unitAvailability JSON.
UPDATE apartments
SET source_url       = 'https://www.equityapartments.com/san-francisco-bay/milpitas/mill-creek-apartments',
    data_source_type = 'brand_site',
    last_content_hash = NULL
WHERE id = 196;

-- apt 218: Reserve at Mountain View — same situation as Mill Creek.
UPDATE apartments
SET source_url       = 'https://www.equityapartments.com/san-francisco-bay/mountain-view/reserve-at-mountain-view-apartments',
    data_source_type = 'brand_site',
    last_content_hash = NULL
WHERE id = 218;

-- apt 173: 360 Residences — property transferred Equity→Essex. New URL has
-- SightMap embed (embed ID: 4d7p1dngpkx). SightMapAdapter.detect() confirmed.
UPDATE apartments
SET source_url       = 'https://www.essexapartmenthomes.com/apartments/san-jose/360-residences',
    data_source_type = 'brand_site',
    last_content_hash = NULL
WHERE id = 173;

-- ============================================================================
-- B. Reclassify 6 apts: brand_site → legal_block
--    POLICY: active anti-bot systems signal "no automated access"; we honor that
--    and display with 🔒 badge rather than hiding.
--    All verified 2026-04-29 with live HTTP checks.
-- ============================================================================

-- Cloudflare Under Attack Mode — HTTP 403, "Just a moment..." JS challenge.
-- modesanmateo.com, viewpointbrighthaven.com: CF fingerprinting + JS challenge.
UPDATE apartments
SET data_source_type = 'legal_block'
WHERE id IN (153, 164);
-- 153  Mode Apartments       modesanmateo.com          CF Under Attack
-- 164  Viewpoint Apartments  viewpointbrighthaven.com  CF Under Attack

-- prometheusapartments.com — Cloudflare Under Attack on all 3 properties.
-- "Attention Required! | Cloudflare" with JS challenge on every path.
UPDATE apartments
SET data_source_type = 'legal_block'
WHERE id IN (68, 223, 234);
-- 68   The Benton    prometheusapartments.com/ca/santa-clara-apartments/the-benton
-- 223  Shadowbrook   prometheusapartments.com/ca/sunnyvale-apartments/shadowbrook
-- 234  The Dean      prometheusapartments.com/ca/mountain-view-apartments/the-dean

-- Sofia Apartments (69) — Repli360 widget fingerprints Playwright headless;
-- floor plan data is only accessible through Repli360 which blocks automated
-- browsers. Site (sofiaaptliving.com) is public but floor plan endpoint is not.
UPDATE apartments
SET data_source_type = 'legal_block'
WHERE id = 69;

-- ============================================================================
-- C. Hanover FC (175) — domain parked/sold, operator website no longer exists.
--    NOT legal_block: the operator has not blocked us — their website is simply
--    gone. hanoverfc.com returns a cdn-fileserver.com ad-redirect (parked domain).
--    Hanover Companies LLC no longer operates this URL.
--    Mark unscrapeable until a new URL is found for this property.
-- ============================================================================

UPDATE apartments
SET data_source_type = 'unscrapeable'
WHERE id = 175;

-- ============================================================================
-- D. UDR properties — no status change, keeping existing unscrapeable.
--    These are NOT policy-blocked (no anti-bot, no compliance issue).
--    Blocked for engineering reasons only: UDR platform adapter not yet built.
--    Note: NOT adding annotation column as it doesn't exist in schema.
-- ============================================================================
-- 194  Verve (Mountain View)                  udr.com — adapter pending
-- 220  Verve Mountain View (dup listing)      udr.com — adapter pending
-- No SQL needed; existing unscrapeable status is correct.

-- ============================================================================
-- E. Verification SELECT — run after all updates committed.
-- ============================================================================

SELECT
  count(*) FILTER (WHERE data_source_type = 'legal_block')                        AS legal_block,
  count(*) FILTER (WHERE data_source_type = 'unscrapeable' AND is_available = true) AS unscrapeable_visible,
  count(*) FILTER (WHERE data_source_type = 'brand_site' OR data_source_type IS NULL) AS scrapeable
FROM apartments
WHERE is_available = true;
