# AptTrack

Bay Area apartment **rental price transparency** system. Collects publicly available listing prices from individual apartment complex websites; stores full price history in PostgreSQL; serves a REST API with JWT auth consumed by a React frontend. Users subscribe to price-drop alerts delivered via email or Telegram. Celery handles scheduled scraping and alert checks.

**Live**: https://apttrack-production-6c87.up.railway.app/

> **Current phase (2026-04 end)**: Pre-dogfood polish ongoing. Original 5 dogfood blockers (B1-B5) all resolved. Two-week strict dogfood **paused** while we close out scraper data-quality bugs surfaced by `/verify-scraper` audits. Resume dogfood once `/verify-scraper` shows ≥70% CORRECT category. Track open issues in `docs/scraper-bugs.md`.

> **Positioning**: transparency + snapshot today; history chart story activates ~Q3 2026 when ≥3 months of data accumulates. Don't lean on `Recharts` price history in UI until then.

> **Compliance posture**: AptTrack respects website operators' technical signals about automated access. We do not bypass anti-bot protection (Cloudflare Under Attack, Distil, PerimeterX, Akamai) or scrape proprietary leasing platforms (Entrata, Hanover internal APIs). Anti-bot sites display in listings with a `data_source_type='legal_block'` badge ("🔒 Price data restricted") rather than being hidden — see `docs/scraper-bugs.md` BUG-09 resolution.

---

## ✅ Resolved Pre-Dogfood Blockers (2026-04 deep-review batch)

The 2026-04-22 scraper review identified 5 critical bugs blocking dogfood. All resolved before dogfood pause:

- **B1** — `_persist_scraped_prices` now updates `area_sqft`, `bedrooms`, `bathrooms`, `name` on every scrape (no longer drops schema fields silently). Commit `d12c9656`.
- **B2** — `_match_plan` rewritten with 4-strategy match (exact-name → archived-name reactivate → exact-sqft ±5 → auto-create new Plan). No silent data loss. Commit `d12c9656` initially, hardened in `ea90601d` (removed risky fuzzy strategies).
- **B3** — SightMap `extract_all_units` parses bed/bath/sqft line-by-line. Commit `39b2c18b`.
- **B4** — SightMap plan-name extraction has UI-verb blacklist + `_PLAN_NAME_REGEX`. Commit `39b2c18b` initial; **completed by BUG-16 fix** (commit `ebc0fb7a`) — added `_NOT_A_PLAN_NAME_RE`, `_UNIT_NUMBER_RE`, `"unit"` blacklist entry.
- **B5** — Token-based password reset (`PasswordResetToken` model, 1-hour TTL, single-use, 3/min rate limit on request endpoint). Commit `a7d569aa`.

These are listed for historical reference. **Active scraper-quality issues are tracked in `docs/scraper-bugs.md`**.

---

## 🔴 Active Pre-Dogfood Cleanup

Open issues blocking dogfood resume. Run `/verify-scraper` to see live counts. See `docs/scraper-bugs.md` for full details on each.

| ID | Severity | Summary | Status |
|----|----------|---------|--------|
| BUG-02 | Low | LeaseStar CAPI returns stale prices (2 apts) | Open — defer to post-dogfood (compliance edge: live API requires reverse-engineering) |
| BUG-04 | Low | Sibling-property contamination on multi-property pages | PARTIALLY RESOLVED — sanitize guard catches contamination; affected sites marked `unscrapeable` per BUG-09 |
| BUG-05 | Low | "Starting from $X" overview-price contamination | PARTIALLY RESOLVED — sanitize Filter D triggers; some sites self-correct |
| BUG-07 | Med | RentCafe HTTP 403 on httpx UA (6 apts) | Open — fix: add browser-like UA header |
| BUG-08 | Low | Essex SSL cert chain rejected by Python ssl (~10 apts) | Open — log noise only; SightMap via Playwright still extracts |
| BUG-13 | Low | Enclave LLM name instability / path-cache replay failure | RESOLVED — path-cache structural fix (commit `3c707e01`); orphan plans archived |
| BUG-15 | Low | Astella prices NULL | RESOLVED — fatwin correctly returns NULL for "contact us" site; bedrooms corrected via SQL |
| BUG-16 | Med | SightMap extracts "Available May 7th" / "E303" as plan names (Miro affected) | RESOLVED — code fix commit `ebc0fb7a`; data fix commit `901b680c`; 33 tests |

**Dogfood resume gate**: BUG-16 code fix ✅ landed + `/verify-scraper` CORRECT category ≥ 70% (run to measure current state).

---

## Compliance Posture (foundational)

AptTrack scrapes **only** sites that meet all three:

1. **Public DOM-rendered or public-API** floor plan pages — no login wall, no proprietary platform endpoints
2. **No active anti-bot measures** — Cloudflare Under Attack Mode, Distil, PerimeterX, Akamai Bot Manager all signal "no automated access" and we honor that
3. **`robots.txt` allows** the path — verified at seed time via `ScrapeSiteRegistry.robots_txt_allows`

Apartments that fall in the first two exclusion categories are stored with `data_source_type='legal_block'` and displayed in listings with a "🔒 Price data restricted" badge linking to the source site. They remain searchable; we don't pretend they don't exist. This produces honest UX while preserving a defensible commercialization posture.

**Coverage tradeoff**: ~14% of seeded apartments end up `legal_block` or `unscrapeable`. Real coverage on scrapeable apartments is the meaningful metric.

---

## Architecture

```
React SPA (TypeScript, Tailwind, Recharts)  ← Vite dev / nginx prod
        │  REST + JWT
        ▼
FastAPI (Pydantic v2, SQLAlchemy 2.0, slowapi rate limit)
        │
        ├── Postgres (apartments, plans, plan_price_history, users,
        │             price_subscriptions, scrape_runs, api_cost_log,
        │             notification_event, password_reset_token, ...)
        ├── Redis (Celery broker)
        └── Celery (worker + beat)
                │
                ├── task_check_price_drops      (08:00 PT daily)
                ├── task_refresh_apartment_data (02:00 PT daily — full re-scrape)
                └── task_daily_health_report    (09:00 PT — added during dogfood)
                        │
                        ▼
                Agentic scraper (MiniMax-M2.5 + Playwright + path cache + content hash)
                        │
                        ├── Platform adapters: avalonbay, sightmap, rentcafe,
                        │   leasingstar, generic_detail, jonah_digital, universal_dom,
                        │   greystar, windsor
                        ├── _sanitize_floor_plans (BUG-04/05/06 deterministic guards)
                        ├── _match_plan (4-strategy)
                        └── _persist_scraped_prices
```

---

## Regulatory Context (2026)

- `Meta v. Bright Data` and `hiQ v. LinkedIn` confirm scraping public data is broadly defensible.
- Anti-bot bypass is a separate question — CFAA risk grows when measures are explicitly evaded.
- Bay Area state laws (Florida HB 1525, others) regulate aggregator pricing transparency, not scraping per se.
- `Craigslist v. RadPad` ($60.5M) precludes scraping aggregators with strict TOS — we don't.

See `backend/app/services/scraper_agent/compliance.py` docstring for full case citations.

---

## Current Data Reality

Seeded with ~180 Bay Area apartments after multiple seed batches and 2026-04 dedup forensics. Daily scrape at 02:00 PT.

| Time | Rows | What the data supports |
|------|------|------------------------|
| 2 weeks | ~1,300 | Current snapshot + deltas |
| 1 month | ~2,700 | 4-point trend lines |
| 3 months | ~8,000 | Meaningful history charts |
| 6 months | ~16,000 | Seasonal patterns |
| 12 months | ~33,000 | Basic forecasting possible |

After Phase 1+2 dogfood data cleanup (Round 1 + Round 2 SQL fixes, Phase A/B/C archive), real coverage on scrapeable apartments is approximately 134/156 = 86%. Use `/verify-scraper` for current accurate measurement.

**Product rules**:
- **No price prediction / forecasting yet.** Revisit Q4 2026.
- **Don't feature price-history chart prominently** until ≥3 months data. Chart is kept in UI but subdued when points are few.
- **Do prefer snapshot-value features** — market comparisons, similar apartments, cheapest-in-city, etc.

---

## Completed Work

### Pre-dogfood blocker fixes (2026-04)
- **B1+B2** (commit `d12c9656`): `_persist_scraped_prices` updates schema fields; `_match_plan` 4-strategy with auto-create. Hardened in `ea90601d` (removed risky fuzzy ±10% strategy after BUG-12/13 collisions).
- **B3+B4** (commit `39b2c18b`): SightMap line-by-line parse + UI verb blacklist.
- **B5** (commit `a7d569aa`): Token-based password reset.

### Forensic data cleanup (2026-04)
- 23 archived apartments via Phase 1 SQL (Group A duplicates from `_slug()` collision pre-fix; Group B contaminated cross-REIT records). All non-destructive (soft-archive with audit trail in `notes`).
- 17 apartments marked `unscrapeable`/`legal_block` per dogfood pre-launch policy: senior living, boutique contact-only, Cloudflare-protected, Prometheus anti-bot, Entrata/Hanover proprietary, multi-property comparison pages.
- 39 plans relative-URL → absolute via CTE-based UPDATE.
- Round 1 SQL: BUG-10/11/12/13/14B/15 manual cleanups (commit `33b24cbc`).
- Round 2 Phase A: BUG-14 Filter A adapter-aware skip (commit `49655a97`).
- Round 2 Phase C: BUG-09 multi-property pages marked unscrapeable (commit `41438464`).

### Scraper architecture
- **Multi-stage pipeline**: negative cache → corporate parent redirect → content-hash short-circuit → static fetch + try_platforms → rendered fetch + try_platforms → path cache replay → LLM agent ReAct loop fallback.
- **`_sanitize_floor_plans`** (commit `31ff9b16`): 4 deterministic filters — sibling-property names (Filter A, adapter-aware after BUG-14), Bay Area $1500 rent floor (Filter B), $25k ceiling (Filter C), starting-from contamination (Filter D, >50% same-price detection).
- **AvalonBay per-unit data** (commit `432476af`): adapter returns one dict per unit with `unit_number`, `floor_level`, availability date — matches LINQ-style multi-row UI design.
- **`legal_block` UI badge** (commit `6d420d01`): listings show 🔒 + "Terms of service restrict data collection" footer for sites we don't scrape.
- **NoticeAvailable units priced** (commit `74b24405`): AvalonBay `is_available` whitelist now includes `NoticeAvailable` (tenant gave notice, listed for leasing).

### Phase A (price alerts correctness)
- `target_price` fires only on ≥→< crossing, auto-pauses, increments `trigger_count`.
- `price_drop_pct` anchored to `baseline_price` (subscription-time snapshot).
- `last_notified_at` timezone uses `astimezone`.
- Plan-level reads `PlanPriceHistory` (no stale `Plan.price` fallback).
- Apartment-level reads `Plan.current_price`.
- Area-level subscriptions rejected 422.
- Re-arm refreshes baseline.
- `target_price >= baseline_price` rejected 422.

### Phase B (notification quality + observability)
- Rich email + Telegram templates with links and context.
- `PriceSubscription.unsubscribe_token` + one-click unsubscribe endpoint (CAN-SPAM).
- `AlertsPage` shows real apartment title + plan spec + latest price.
- `NotificationEvent` table + SendGrid webhook (bounce/open/click tracking) + Telegram 403 auto-disable.
- Pause/Resume button with optimistic UI.

### Phase C (listing browse UX)
- Sort controls, favorites, advanced filters (pets/parking/sqft/available_before).
- Mobile plan cards + multi-plan chart switcher.
- Median rent stat (replaced avg).
- Similar apartments + market context pill.
- Dedup of plan rows by (beds, baths, sqft) — groups options under one row, dropdown for 3+.
- Listings filter hides `unscrapeable` by default with opt-in toggle (commit `5f48cd6d`).
- Apartment name search box (commit `d37e3008`).

### Phase D partial
- AuthModal `onSuccess` callback.
- sonner toasts on all mutations.
- Leaflet map view with city-colored markers.
- Alerts count badge in nav.
- Mobile responsiveness.
- Mini map on ListingDetailPage.
- Multi-select city filter (client-side).
- Real move-in dates on AvalonBay plan rows (commit `c4ba156a`).

### Onboarding (Phase 3B.2)
- Demo subscription auto-created on register.
- Welcome email.
- Empty-state CTAs on AlertsPage.

### Scraper data expansion
- Per-plan `external_url` capture.
- Per-unit `floor_level` + compass `facing` capture.
- Amenities + move-in specials capture.
- Content-hash short-circuit: SHA256 of stripped HTML; unchanged → carry forward prices, $0.00 cost.
- Per-unit availability dates parsed (commit `0a317786`, month-name format added in `3f434cf4`).

### Cost observability
- `ApiCostLog` Postgres table (replaced ephemeral JSONL, survives Railway redeploys).
- `dev/cost_summary.py` reader.
- `GooglePlaceRaw` dedup cache: re-importing a city costs $0.03 instead of $0.45.
- Google Maps keywords trimmed 15 → 3 synonyms (senior housing removed — noisy results).

### Dogfood instrumentation
- `docs/dogfood-papercuts.md` template + entries in place.
- `docs/scraper-bugs.md` — bug catalog with status, root cause, fix proposal, affected apartments.
- `seed_apartments.py --urls-file` CLI for adding new apartments.
- `dev/audit.py` — SQL audit of plan sqft/name coverage.
- `/verify-scraper` Claude Code command — re-runs 30-apartment audit with 4-state output (CORRECT / AWAITING / WRONG / CORRECTLY_NULL).

### Testing
- 39 test files: unit, API, scraper unit, live scraper integration.
- Regression suite covers sanitize filters, adapter dispatch, _match_plan strategies.

---

## Roadmap (post pre-dogfood cleanup)

### Resume dogfood when
- BUG-16 code fix landed
- `/verify-scraper` shows ≥70% CORRECT category
- Subscription health check confirms 5-7 user subs all on healthy plans (no NULL prices, baseline within 5% of current)

### Week 0 (smoke test + confirm data health)
- Trigger full re-scrape with cleared path cache.
- Run `dev/audit.py` and `/verify-scraper` — confirm CORRECT ≥ 70%, no apt with > 15 plans (dedup pollution check), all plans have area_sqft.
- Verify all subscriptions are on `data_source_type='brand_site'` apartments (not `unscrapeable` or `legal_block`).

### Weeks 1-2 (strict dogfood, no new features)
- Use AptTrack daily as actual rental-hunting tool.
- Every friction → entry in `docs/dogfood-papercuts.md`.
- `task_daily_health_report` Celery task — 09:00 PT email summary of scrape outcomes, notification health, subscription triggers, data growth.
- Weekly `dev/audit.py` + `/verify-scraper` runs.

### Week 2 checkpoint
- Review paper-cut log with full numbers from daily reports.
- Pick top 3 S1/S2 items. That's Weeks 3-4 backlog, regardless of what Phase 4 docs say.

### Weeks 3-4 (polish top-3 based on dogfood)
- Ship top 3 as separate PRs.
- Update paper-cut log with `[FIXED]` tags.

### Weeks 5+
- Only if dogfood stable, revisit Phase 4 items (listed below).
- Open `scraper-bugs.md` items downgraded from "open/pending" if dogfood signal warrants.

---

## Phase 4 Deferred (DO NOT START — wait for dogfood evidence)

- **BUG-02 LeaseStar live endpoint** — reverse-engineering required; compliance edge if endpoint requires auth/signature.
- **BUG-07 RentCafe UA fix** — 6 apts unblocked; defer until dogfood signals these specific apts matter.
- **BUG-08 Essex SSL** — log noise only; suppress in scrape pipeline.
- **Equity Residential / Irvine / Brookfield platform adapters** — 5 apts marked `legal_block`; build adapters only if Bay Area dogfood evidence shows demand.
- **Path cache plan-name locking** — fixes BUG-13 LLM name instability fundamentally; architectural change.
- **`alternate_url` schema field** — Apex Milpitas case noted in dedup forensics.
- **Google Places Photos** — Pro tier FieldMask + carousel UI.
- **Magic-link / passwordless auth** — infra in place after B5 (token table reusable).
- **Telegram bot bidirectional commands** (`/watch`, `/target`, `/pause`).
- **Saved Search model** — "listings matching my criteria" vs "watch this apartment".
- **Adaptive scrape cadence** — only relevant at 100+ apartments with varying change rates.
- **Price prediction** — revisit Q4 2026 with 6+ months data.
- **Celery task sharding** — irrelevant at current scale.
- **Scraper code consolidation** (dup between service dir and tests dir).

---

## Key Directories

| Path | Purpose |
|------|---------|
| `backend/app/api/api_v1/endpoints/` | REST endpoints (apartments, auth, favorites, search, statistics, subscriptions, admin, webhooks) |
| `backend/app/models/apartment.py` | `Apartment`, `Plan` (with `current_price`, `external_url`, `floor_level`, `facing`), `PlanPriceHistory`, `Unit` (per-unit pricing for AvalonBay/SightMap) |
| `backend/app/models/user.py` | `User`, `PriceSubscription` (with `baseline_price`, `trigger_count`, `is_demo`, `unsubscribe_token`) |
| `backend/app/models/notification_event.py` | Audit trail for every email/Telegram |
| `backend/app/models/favorite.py` | User shortlist |
| `backend/app/models/site_registry.py` | Compliance state per domain, `last_successful_adapter` hint |
| `backend/app/models/google_place.py` | `GooglePlace` + `GooglePlaceRaw` dedup cache |
| `backend/app/models/scrape_run.py` | Per-scrape outcome, iterations, cost, elapsed |
| `backend/app/models/api_cost_log.py` | Every LLM/Google Maps cost event |
| `backend/app/models/password_reset_token.py` | Token-based password reset (B5) |
| `backend/app/services/scraper_agent/` | Agent + browser tools + path cache + compliance + content_hash |
| `backend/app/services/scraper_agent/platforms/` | 10 adapters: avalonbay, sightmap, rentcafe, leasingstar, jonah_digital, universal_dom, generic_detail, greystar, windsor, fatwin |
| `backend/app/services/scraper_agent/content_hash.py` | SHA256 of stripped HTML for scrape short-circuit |
| `backend/app/services/google_maps.py` | Places API (New) with GooglePlaceRaw dedup |
| `backend/app/services/price_checker.py` | Price-drop detection (Phase A semantics) |
| `backend/app/services/notification.py` | SendGrid + Telegram, rich templates |
| `backend/app/worker.py` | Celery tasks, beat schedule, scrape pipeline, `_match_plan`, `_persist_scraped_prices`, `_sanitize_floor_plans`, `_normalize_avalon_plan_names` |
| `backend/alembic/versions/` | 25+ migrations |
| `app/src/pages/` | `ListingsPage`, `ListingDetailPage`, `AlertsPage`, `FavoritesPage`, `UnsubscribePage` |
| `app/src/components/` | `AlertModal`, `AuthModal`, `FilterPanel`, `ListingCard` (with legal_block badge), `MapView` |
| `dev/cost_summary.py` | CLI reader for `api_cost_log` |
| `dev/audit.py` | SQL audit of plan sqft/name coverage |
| `.claude/commands/verify-scraper.md` | Claude Code command — runs 30-apt audit with 4-state output |
| `docs/dogfood-papercuts.md` | 2-week dogfood UX tracking |
| `docs/scraper-bugs.md` | Active and resolved scraper bugs with root cause + fix |
| `docs/scraper-price-audit-2026-04-25.md` | Baseline accuracy audit pre-PR-D |

> **Note on scraper code duplication**: `backend/app/services/scraper_agent/` and `tests/integration/agentic_scraper/` hold parallel copies of `agent.py`, `browser_tools.py`, `models.py`, `path_cache.py`. Any change must be applied to both. Consolidation is deferred tech debt.

---

## Data Model

```
User (1) ──► (N) PriceSubscription
                     │ FK to apartment/plan (area-level disabled)
                     │ baseline_price, baseline_recorded_at, trigger_count
                     │ is_demo, unsubscribe_token

User (1) ──► (N) ApartmentFavorite
User (1) ──► (N) PasswordResetToken (1-hour TTL, single-use)

Apartment (1) ──► (N) Plan (1) ──► (N) PlanPriceHistory
    │                   │              (1) ──► (N) Unit (per-unit AvalonBay/SightMap)
    │                   ├──► external_url, floor_level, facing
    │                   └──► current_price (live value, kept in sync by worker)
    │
    │   last_content_hash, last_scraped_at (scrape short-circuit)
    │   current_special (move-in offer)
    │   data_source_type: 'brand_site' | 'unscrapeable' | 'legal_block'

PriceSubscription (1) ──► (N) NotificationEvent (sent/delivered/opened/clicked/bounced)

ScrapeSiteRegistry (keyed by domain, 1:N Apartments)
    │   robots_txt_allows, last_successful_adapter (hint)

GooglePlace + GooglePlaceRaw (dedup cache, keyed by place_id)
ScrapeRun (per-scrape outcome + cost + elapsed)
ApiCostLog (every LLM / Google Maps cost event)
```

---

## Agentic Scraper

**Files**: `backend/app/services/scraper_agent/{agent.py, browser_tools.py, models.py, path_cache.py, compliance.py, content_hash.py, platforms/}`.

**Loop**: LLM sees structured page state (BeautifulSoup — never screenshots) → decides tool call → `BrowserSession` executes via Playwright → observation → repeat until `submit_findings` or 22-iter no-data early stop.

**Tools**: `navigate_to`, `click_link`, `click_button`, `scroll_down`, `read_iframe`, `extract_all_units`, `submit_findings`.

**Model**: `MiniMax-M2.5` via OpenAI-compatible API. $0.30/M input, $1.10/M output.

**Scrape flow in worker.py per apartment**:

1. **Negative cache check** — recently failed URLs skipped for 24h.
2. **Corporate parent redirect** — REIT-level URLs canonicalized.
3. **Content-hash short-circuit** — HTTP GET + `compute_content_hash`. If unchanged: `_carry_forward_prices`, write `ScrapeRun outcome="content_unchanged"`. **0 LLM, 0 Playwright**.
4. **Static fetch + `try_platforms(static_html)`** — 10 adapters tried in registry-hint order; first detect-true wins.
5. **Rendered fetch (Playwright) + `try_platforms(rendered_html)`** — only if static missed and weak signals present.
6. **Path cache replay** — if cached path for this URL exists, replay browser steps, parse via `_parse_units_to_apartment_data`. **0 LLM calls**.
7. **Full ReAct loop** — agent runs, max 35 iter, early stop at 22 no-data. <5% of scrapes reach this.
8. **`_sanitize_floor_plans(result, adapter_name)`** — 4-filter contamination guard:
   - **Filter A**: sibling-property name detection (skipped for `_DETAIL_PAGE_ADAPTERS` like `jonah_digital`)
   - **Filter B**: $1500 Bay Area rent floor — null deposit/fee values
   - **Filter C**: $25k ceiling — null typos
   - **Filter D**: >50% same-price → null all (starting-from contamination)
9. **`_normalize_avalon_plan_names`** — pre-pass: rename DB generic plans ("1 Bed / 1 Bath") to specific Avalon codes (A2G, B1G) when beds+sqft match.
10. **`_match_plan`** — 4-strategy:
    1. Exact name on active plans
    2. Exact name on archived plans (reactivate)
    3. Exact sqft (±5) on same-bedroom-count active plans
    4. Auto-create new Plan
11. **`_persist_scraped_prices`** — writes `PlanPriceHistory`, updates `Plan.current_price`, `area_sqft`, `bedrooms`, `bathrooms`, `name`, apartment `current_special`, `last_content_hash`.

---

## Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `task_check_price_drops` | Daily 08:00 PT | Check subscriptions, send alerts, auto-pause on fire |
| `task_refresh_apartment_data` | Daily 02:00 PT | Re-scrape all `is_available` apartments |
| `task_refresh_apartment_chunk` | Manual / on-demand | Re-scrape specific list of apt IDs (used by local re-scrape sessions) |
| `task_daily_health_report` | Daily 09:00 PT | **(to add during Week 1 dogfood)** email admin summary |

---

## Auth & Security

- JWT (HS256), 24h expiry, bcrypt passwords.
- `require_admin` on write endpoints + Google Maps import.
- `get_current_user` on subscription endpoints, scoped to own `user_id`.
- GET endpoints public.
- Rate limits: write 10/min, auth 5/min, password reset request 3/min, read 60/min, import 3/hr.
- `JWT_SECRET_KEY` validator refuses default in production.
- `unsubscribe_token` unguessable, per-subscription.
- Token-based password reset: `POST /auth/request-password-reset` creates `PasswordResetToken` (1-hour TTL, single-use), emails link; `POST /auth/reset-password {token, new_password}` consumes the token.

---

## Scraper Compliance (hard rules)

- NEVER scrape Craigslist or UGC aggregators (`Craigslist v. RadPad` $60.5M).
- NEVER scrape behind login walls.
- NEVER bypass anti-bot protection (Cloudflare Under Attack, Distil, PerimeterX, Akamai). Mark such sites `data_source_type='legal_block'` and display in UI with restriction badge.
- NEVER access proprietary leasing platform APIs (Entrata, Hanover internal endpoints) without published partnership.
- NEVER collect PII.
- Only factual data: prices, sqft, bedrooms, availability, business phone, official URL, public amenity flags.
- robots.txt checked before new domains (`ScrapeSiteRegistry.robots_txt_allows`).
- C&D protocol in `compliance.py` header docstring.
- 5s minimum between scrapes of same domain.

### Content Replication

- **Original-source images**: never stored or displayed.
- **Google Places Photos** (deferred): allowed — Google hosts, we'd store references + "Powered by Google" attribution.
- **Listing descriptions, HTML body, floor-plan artwork**: never stored.
- Derived facts (price, sqft, bed/bath, amenity flags) are fine.

---

## Environment Variables

Critical:
- `DATABASE_URL`, `REDIS_URL`
- `JWT_SECRET_KEY` (refused at startup if default)
- `MINIMAX_API_KEY`, `GOOGLE_MAPS_API_KEY`
- `SENDGRID_API_KEY`, `SENDGRID_FROM_EMAIL`
- `TELEGRAM_BOT_TOKEN` (optional)
- `APP_BASE_URL`
- `DEFAULT_DEMO_CITY`
- `CORS_ORIGINS` (must match frontend URL exactly, no wildcard with credentials)
- `ADMIN_EMAIL` (for `task_daily_health_report`)

---

## Development

```bash
./start.sh                    # Docker full stack (6 services)
./start.sh local              # Local dev
python seed_apartments.py --urls-file dev/my_apartments.txt   # Seed
pytest tests/unit/ -v
pytest tests/api/ -v
pytest tests/integration/agentic_scraper/ -m "not integration" -v
pytest tests/integration/agentic_scraper/ -m integration -v   # Live scraper, ~$0.10
alembic revision --autogenerate -m "description"
alembic upgrade head
ruff check backend/
python dev/cost_summary.py --days 7
python dev/audit.py
```

### Local re-scrape (writes to Railway DB synchronously)

```bash
# Verify DATABASE_URL points to Railway production
echo $DATABASE_URL | grep -qi 'railway' && echo "OK Railway" || echo "STOP wrong DB"

# Re-scrape specific apartments via Celery task in-process (no Redis needed)
python -c "
import logging; logging.basicConfig(level=logging.INFO)
from app.worker import task_refresh_apartment_chunk
result = task_refresh_apartment_chunk.apply(args=[[<apt_ids>]])
print('OK' if result.successful() else result.traceback)
"
```

---

## Coding Conventions

- Python 3.11, type hints on public functions, SQLAlchemy 2.0 ORM (`select(...)`).
- Pydantic v2 (`model_dump`, `model_validate`).
- Endpoints by domain folder, `core.py` + `__init__.py` router assembly.
- Every write endpoint: `@limiter.limit(...)` + auth dependency.
- Frontend: React functional + hooks, TypeScript strict, Tailwind, sonner toasts.
- Tests: pytest, `@pytest.mark.integration` for network.
- Lint: ruff, 120-char lines.
- Migrations: one concept per migration, descriptive names.

---

## Active Tech Debt

1. **BUG-16 code fix outstanding** — SightMap plan-name validation needs regex pattern reject (UI verb prefix + unit-number pattern), beyond current exact-match blacklist. Data fix shipped on Miro production but recurrence prevention pending.
2. **BUG-13 idempotency unverified** — Enclave plan name instability mitigated by archive + re-scrape; needs second-scrape verification to confirm `_match_plan` strategy 3 catches name variation via sqft.
3. **Scraper code duplication** between `scraper_agent/` and `tests/integration/agentic_scraper/`. Any change must be mirrored.
4. **`Plan.price` deprecated** but still populated by seed script — remove after confirming no read paths use it.
5. **`ApartmentImage` table unused** — added for future image support; will repurpose or drop.
6. **Cost log JSONL fallback** (legacy path in `cost_log.py`) — remove after `api_cost_log` proven stable in production.
7. **`extract_all_units` capped at 15 floors** — insufficient for high-rise SF (NEMA 23 floors, Austin 42). Bump to 30.
8. **Subscription baseline reset semantics** — when an apartment moves from `unscrapeable` → `brand_site` (or vice versa), or after major data migrations (Round 1/2 SQL), baselines may drift > 5% from current price. Daily cron fires fake alerts. Manual SQL reset to `MIN(current_price)` after data migrations.

---

## References

- `docs/scraper-bugs.md` — bug catalog, status, root cause, fix proposal.
- `docs/scraper-price-audit-2026-04-25.md` — baseline accuracy audit.
- `docs/dogfood-papercuts.md` — active UX log during dogfood.
- `docs/phase-a-rescue-retro.md` — retrospective of Phase A scraper recovery.
- `backend/app/services/scraper_agent/compliance.py` — legal context, C&D protocol, case citations.
- `dev/cost_summary.py` — API spend observability.
- `dev/audit.py` — plan data-quality SQL audit.
- `.claude/commands/verify-scraper.md` — 30-apt accuracy audit command.
- `.claude/prompts.md` — copy-paste prompts for ongoing maintenance.