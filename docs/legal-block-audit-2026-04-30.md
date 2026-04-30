# AptTrack Legal Block & Coverage Audit — 2026-04-30

Full sweep of all DB apartments to classify data access status.
Methodology: live HTTP check on every brand_site domain, anti-bot signal detection,
property-type verification. Applied three-bucket decision tree from CLAUDE.md.

## Summary

| Status | Count | Description |
|--------|-------|-------------|
| `brand_site` | **116** | Actively scraped, data current |
| `legal_block` | **17** | Active anti-bot or proprietary block; shown with 🔒 badge |
| `unscrapeable` | **4** | Engineering blocker or wrong property type; shown as "data unavailable" |
| archived (`is_available=false`) | ~30 | Duplicates, retired, senior living |

---

## legal_block (17 apartments)

Sites where the operator has deployed active anti-bot protection.
Per policy: honor the signal, display with 🔒 badge, never bypass.

### Cloudflare Under Attack Mode (HTTP 403, "Just a moment...")

| ID | Title | Domain | Reason |
|----|-------|--------|--------|
| 64 | Live Revella | liverevela.com | CF Under Attack, HTTP 403 |
| 67 | Verdant Apartments | verdant-apts.com | CF Under Attack, HTTP 403 |
| 68 | The Benton | prometheusapartments.com | CF Under Attack, HTTP 403 |
| 153 | Mode Apartments | modesanmateo.com | CF Under Attack, HTTP 403 |
| 164 | Viewpoint Apartments | viewpointbrighthaven.com | CF Under Attack, HTTP 403 |
| 171 | Tan Plaza Apartments | liveattanplaza.com | CF Under Attack, HTTP 403 |
| 172 | Telegraph Gardens Apartments | telegraphgardens.com | CF Under Attack, HTTP 403 |
| 223 | Shadowbrook | prometheusapartments.com | CF Under Attack, HTTP 403 |
| 234 | The Dean | prometheusapartments.com | CF Under Attack, HTTP 403 |

### Irvine Company — Cloudflare Under Attack (entire domain)

`irvinecompanyapartments.com` returns HTTP 403 with CF challenge on all paths.
Playwright can execute the JS challenge but that constitutes bypassing per policy.

| ID | Title |
|----|-------|
| 154 | Santa Clara Square Apartment Homes |
| 207 | Redwood Place Apartments For Rent in Sunnyvale, CA |
| 208 | North Park in San Jose |
| 209 | Crescent Village Apartments in San Jose |
| 210 | River View Apartments in San Jose, CA for Rent |
| 211 | Monticello Apartments in Santa Clara |
| 224 | Cherry Orchard in Sunnyvale |

### Repli360 Widget Fingerprinting (JS-only floor plan data)

| ID | Title | Domain | Reason |
|----|-------|--------|--------|
| 69 | Sofia Apartments | sofiaaptliving.com | DudaOne CMS + Repli360 widget fingerprints Playwright headless; floor plan data inaccessible without stealth |

---

## unscrapeable (4 apartments, visible)

Sites that are accessible but can't be scraped for engineering reasons
(not policy). Shown as "pricing unavailable" in UI.

| ID | Title | Reason |
|----|-------|--------|
| 175 | Hanover FC | Domain hanoverfc.com parked/sold; operator website gone |
| 194 | Verve | UDR platform adapter not yet built |
| 220 | Verve Mountain View | UDR platform adapter not yet built (dup listing) |
| 263 | Cezanne Apartments in Sunnyvale | deanzaproperties.com multi-property management site |

---

## Domains checked — confirmed OK (no anti-bot, brand_site retained)

These domains returned HTTP 200 with no Cloudflare/DataDome/Akamai Bot Manager
signals. Previously detected as "Akamai" but verified as CDN-only (no fingerprinting).

| Domain | Apts | Note |
|--------|------|------|
| murphystationapts.com | 274 | Akamai CDN only |
| www.481mathilda.com | 250 | Akamai CDN only |
| www.555milpitas.com | 238 | Akamai CDN only |
| www.encasaliving.com | 243 | Akamai CDN only |
| www.glenmoorgreenapartments.com | 286 | Akamai CDN only |
| www.cathaylotus.com | 277 | Timeout during check — assumed OK (prior scrapes succeeded) |
| rent.brookfieldproperties.com | 71 | HTTP 200, accessible |

---

## Archived this session (wrong property type)

| ID | Title | Reason |
|----|-------|--------|
| 24 | Redwood Seniors | Senior living facility (`redwoodseniors.com` — "Convenient Senior Apartments") |
| 59 | Coterie Cathedral Hill | Senior retirement community (`coterieseniorliving.com/luxury-retirement-communities/`) |

---

## Previously resolved (earlier sessions)

The following were reclassified before this audit:

| Batch | IDs | Reason |
|-------|-----|--------|
| 2026-04-29 Step 2 | 68, 153, 164, 223, 234 | Cloudflare Under Attack (Prometheus + individual domains) |
| 2026-04-29 Step 2 | 69 | Repli360 bot detection |
| 2026-04-30 Irvine sweep | 154, 207–211, 224 | irvinecompanyapartments.com CF Under Attack |
| 2026-04-30 this audit | 64, 67, 171, 172 | CF Under Attack (previously missed) |

---

## Notes on false positives

- **Akamai signals**: Many apartment sites use Akamai as a CDN (DDoS protection).
  The presence of `akamai` in HTML does NOT indicate bot blocking unless `_abck`
  cookie script or `bm_sv` tokens are present (Akamai Bot Manager signatures).
  Pure CDN usage is not a compliance concern.

- **De Anza Properties (deanzaproperties.com)**: Multi-property management company.
  Flora Vista (260) was marked unscrapeable after sibling-property contamination
  was confirmed (Warburton Village / Stevens Creek Villas names extracted).
  Cezanne (263) has a property-specific page that appears accessible; Filter A
  sanitize provides contamination protection if sibling names appear.

- **Cathay Lotus (277)**: Repeatedly times out during HTTP checks. Site was
  successfully scraped in the past via universal_dom. Kept as brand_site pending
  next successful scrape verification.

---

*Generated: 2026-04-30. Re-run this audit quarterly or after major seed batches.*
