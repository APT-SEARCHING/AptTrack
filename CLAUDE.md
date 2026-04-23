# AptTrack

Bay Area apartment **rental price transparency** system. Collects publicly available listing prices from individual apartment complex websites; stores full price history in PostgreSQL; serves a REST API with JWT auth consumed by a React frontend. Users subscribe to price-drop alerts delivered via email or Telegram. Celery handles scheduled scraping and alert checks.

**Live**: https://apttrack-production-6c87.up.railway.app/

> **Current phase (2026-04)**: Railway deploy complete. About to enter 2-week strict dogfood. **Before dogfood starts**, 5 critical bugs must be fixed — see "🔴 Dogfood Blockers" below. Four are scraper data-quality bugs silently destroying `PlanPriceHistory` growth; one is a security hole in password reset.

> **Positioning**: transparency + snapshot today; history chart story activates ~Q3 2026 when ≥3 months of data accumulates. Don't lean on `Recharts` price history in UI until then.

---

## 🔴 Dogfood Blockers (fix BEFORE starting 2-week dogfood)

All five surfaced in the 2026-04-22 deep scraper review. Ordered by severity. See `.claude/prompts.md` for step-by-step fix contracts.

### B1 — `_persist_scraped_prices` silently drops sqft/bedrooms/bathrooms/name updates

**File**: `backend/app/worker.py` L598-620

`_persist_scraped_prices` updates `price`, `current_price`, `external_url`, `floor_level`, `facing` from the scraped `FloorPlan` — but **does not update `area_sqft`, `bedrooms`, `bathrooms`, or `name`**. These fields are only written during initial DB seed, so daily scrapes never fix seed-time gaps.

**Downstream damage**: `_match_plan`'s fuzzy strategy relies on DB-side `c.area_sqft`. Because that column stays stale/null, fuzzy matching frequently fails → `_match_plan` returns None → `_persist_scraped_prices` hits `continue` → **the plan's price history row is silently dropped**.

This is the #1 reason `PlanPriceHistory` grows slower than the expected 30/apt/day baseline, and the reason user-visible sqft/plan-name fields look empty.

### B2 — `_match_plan` returns None instead of creating new plans

**File**: `backend/app/worker.py` L490-521

When both exact-name match fails and fuzzy (bedrooms + sqft ±10%) doesn't find a candidate, `_match_plan` returns None. Caller drops the scrape result. A new unit on the source site that doesn't match any existing DB plan is data-lost forever.

Fix adds two more strategies: (3) fuzzy by bedrooms+bathrooms when single candidate, (4) auto-create `Plan` row when sufficient info exists. Accumulation-first > drop-first.

### B3 — SightMap `extract_all_units` regex requires bed/bath/sqft on one line

**File**: `backend/app/services/scraper_agent/browser_tools.py` L585-589

The regex `(\d+)\s*Bed.*?(\d+)\s*Bath.*?([\d,]+)\s*sq` requires all three numbers to appear on the same line. Real SightMap pages frequently split them across 3-4 lines (`Studio S1` / `Studio` / `1 Bath` / `420 sq. ft.`) — regex matches 0 lines, sqft extraction yields 0%.

Fix: replace single-line regex with independent per-field regexes scanning all lines in the unit block.

### B4 — SightMap plan name extraction grabs UI labels

**File**: `backend/app/services/scraper_agent/browser_tools.py` L582-583

The heuristic "first line that isn't $ / Bed / sq. ft. / Available" treats UI affordances like `Favorite`, `Tour Now`, `View Details`, `Schedule Tour` as plan names. Results in `plan.name="Favorite"` in DB.

Fix: blacklist known UI verbs + require plan-name-shaped regex (starts with letter, 1-40 chars, mixed case allowed).

### B5 — Password reset has account-takeover vulnerability

**File**: `backend/app/api/api_v1/endpoints/auth/core.py` L89-102

Current `POST /auth/reset-password {email, new_password}` accepts any email and changes that user's password immediately — no email verification, no token. Anyone who knows your email can take over your account.

Fix: standard token-based reset — (1) `POST /auth/request-password-reset {email}` creates a `PasswordResetToken` row (1-hour TTL, single-use), emails a link. (2) `POST /auth/reset-password {token, new_password}` consumes the token.

Side benefit: the token table is reusable infrastructure for future magic-link auth.

---

## Deploy artifacts in place (2026-04 deploy complete)

**Railway services**:
- `apttrack-backend` (web) — `backend/Dockerfile` → `alembic upgrade head && uvicorn ...`
- `apttrack-worker` — `backend/Dockerfile.worker` (Playwright base image) → Celery worker
- `apttrack-beat` — `backend/Dockerfile.worker` → Celery beat
- `apttrack-frontend` — `app/Dockerfile` → nginx on port 80
- Postgres + Redis plugins

**Lessons from first deploy** (fold into `docs/railway-deploy.md` when you get a chance):
- `PYTHONPATH=/app` in both Dockerfiles.
- `alembic/env.py` must self-configure `sys.path`.
- `DATABASE_URL` must `raise` clearly if missing (sudden crash is better than silent wrong state).
- SQLAlchemy 2.0: wrap raw SQL in `text()`, no raw strings.
- `path_cache/*.json` must be committed (Railway containers start blank; `.gitignore` was too aggressive).
- `CORS_ORIGINS` must match frontend service URL **exactly** (wildcard + `allow_credentials=True` fails silently in browsers).
- Frontend nginx: hard-code port 80 (Railway's public domain routes to 80), don't try to envsubst PORT.
- Frontend nginx: do NOT include `location /api { proxy_pass ... }` block — it crashes when the upstream isn't resolvable, and Railway uses cross-service URLs not docker-compose service names.

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌────────────┐
│  React / TypeScript │◄───►│  FastAPI (Python)    │◄───►│ PostgreSQL │
│  Tailwind CSS       │     │  Pydantic v2         │     │ 14-alpine  │
│  Recharts + Leaflet │     │  SQLAlchemy 2.0      │     └────────────┘
│  sonner toasts      │     │  Alembic             │
└─────────────────────┘     │  slowapi (rate lim.) │     ┌────────────┐
                            │  JWT auth (jose)     │◄───►│   Redis    │
                            └────────┬─────────────┘     │  7-alpine  │
                                     │                    └────────────┘
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
        Google Maps Places   Agentic Scraper      Celery Worker + Beat
        (New API, Essential) MiniMax-M2.5 +       daily refresh 02:00 PT
        + GooglePlaceRaw     Playwright           daily alerts 08:00 PT
          dedup cache        + path cache         + content-hash short
                             + content_hash         circuit
```

---

## Regulatory Context (2026)

AptTrack is **not the target** of recent rental-pricing enforcement, but the landscape informs product decisions.

- **California AB 325** (2026-01-01) prohibits **competitors sharing a common pricing algorithm**. Targets hub-and-spoke SaaS coordination.
- **DOJ v. RealPage settlement** (2025-11-24) restricts RealPage's use of non-public competitor data.
- **SF (2024-08)** and **Berkeley (2024-09)** city-level bans on algorithmic rent-setting.

**Why AptTrack is not in scope**:
1. We collect **publicly accessible data** from individual listing pages.
2. We serve **tenants**, not landlords.
3. We are **not a hub**. No landlord supplies data to us; no landlord receives pricing advice from us.

**What changed**: daily price changes are now rare. Value shifted from "change velocity" to "current snapshot + future history".

**Hard rule — do NOT build**: any feature monetizing **landlords or property managers via pricing advice**. That could re-classify AptTrack as a "shared algorithm hub" under AB 325.

---

## Current Data Reality

Seeded with ~30 Bay Area apartments. Daily scrape at 02:00 PT. `PlanPriceHistory` target growth ≈ 90 rows/day.

| Time | Rows | What the data supports |
|------|------|------------------------|
| 2 weeks | ~1,300 | Current snapshot + deltas |
| 1 month | ~2,700 | 4-point trend lines |
| 3 months | ~8,000 | Meaningful history charts |
| 6 months | ~16,000 | Seasonal patterns |
| 12 months | ~33,000 | Basic forecasting possible |

**⚠ But real growth rate likely below target** until B1/B2 are fixed — `_match_plan` silently drops rows.

**Product rules**:
- **No price prediction / forecasting yet.** Revisit Q4 2026.
- **Don't feature price-history chart prominently** until ≥3 months data. Chart is kept in UI but subdued when points are few.
- **Do prefer snapshot-value features** — market comparisons, similar apartments, cheapest-in-city, etc.

---

## Completed Work

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

### Phase D partial
- AuthModal `onSuccess` callback.
- sonner toasts on all mutations.
- Leaflet map view with city-colored markers.
- Alerts count badge in nav.
- Mobile responsiveness.
- Mini map on ListingDetailPage.
- Multi-select city filter (client-side).

### Onboarding (Phase 3B.2)
- Demo subscription auto-created on register.
- Welcome email.
- Empty-state CTAs on AlertsPage.

### Scraper data expansion
- Per-plan `external_url` capture.
- Per-unit `floor_level` + compass `facing` capture.
- Amenities + move-in specials capture.
- Content-hash short-circuit: SHA256 of stripped HTML; unchanged → carry forward prices, $0.00 cost.

### Cost observability
- `ApiCostLog` Postgres table (replaced ephemeral JSONL, survives Railway redeploys).
- `dev/cost_summary.py` reader.
- `GooglePlaceRaw` dedup cache: re-importing a city costs $0.03 instead of $0.45.
- Google Maps keywords trimmed 15 → 3 synonyms (senior housing removed — noisy results).

### Dogfood instrumentation
- `docs/dogfood-papercuts.md` template + 4 entries in place.
- `seed_apartments.py --urls-file` CLI for adding new apartments.

### Testing
- 170 total tests: unit, API, scraper unit, live scraper integration.

---

## Post-Blockers Roadmap (after B1-B5 fixed, dogfood starts)

### Week 0 (smoke test + confirm data health)
- After B1-B5 merged + deployed, purge path cache and trigger full scrape.
- Run `dev/audit.py` (see below) — confirm sqft coverage ≥60%, clean plan names.
- Register real accounts, create 3-5 real subscriptions at realistic thresholds.

### Weeks 1-2 (strict dogfood, no new features)
- Use AptTrack daily as actual rental-hunting tool.
- Every friction → entry in `docs/dogfood-papercuts.md`.
- Add `task_daily_health_report` Celery task — 09:00 PT email summary of scrape outcomes, notification health, subscription triggers, data growth.
- Weekly `dev/audit.py` runs.

### Week 2 checkpoint
- Review paper-cut log with full numbers from daily reports.
- Pick top 3 S1/S2 items. That's Weeks 3-4 backlog, regardless of what Phase 4 docs say.

### Weeks 3-4 (polish top-3 based on dogfood)
- Ship top 3 as separate PRs.
- Update paper-cut log with `[FIXED]` tags.

### Weeks 5+
- Only if dogfood stable, revisit Phase 4 items (listed below).

---

## Phase 4 Deferred (DO NOT START — wait for dogfood evidence)

- **Google Places Photos** — Pro tier FieldMask + carousel UI.
- **Magic-link / passwordless auth** — infra partially built after B5 fix (token table).
- **Telegram bot bidirectional commands** (`/watch`, `/target`, `/pause`).
- **Saved Search model** — "listings matching my criteria" vs "watch this apartment".
- **Adaptive scrape cadence** — only relevant at 100+ apartments with varying change rates.
- **Price prediction** — revisit Q4 2026 with 6+ months data.
- **Celery task sharding** — irrelevant at 30-apartment scale.
- **Scraper code consolidation** (dup between service dir and tests dir).

---

## Key Directories

| Path | Purpose |
|------|---------|
| `backend/app/api/api_v1/endpoints/` | REST endpoints (apartments, auth, favorites, search, statistics, subscriptions, admin, webhooks) |
| `backend/app/models/apartment.py` | `Apartment`, `Plan` (with `current_price`, `external_url`, `floor_level`, `facing`), `PlanPriceHistory` |
| `backend/app/models/user.py` | `User` (with `unsubscribe_all_token`), `PriceSubscription` (with `baseline_price`, `trigger_count`, `is_demo`, `unsubscribe_token`) |
| `backend/app/models/notification_event.py` | Audit trail for every email/Telegram |
| `backend/app/models/favorite.py` | User shortlist |
| `backend/app/models/site_registry.py` | Compliance state per domain |
| `backend/app/models/google_place.py` | `GooglePlace` + `GooglePlaceRaw` dedup cache |
| `backend/app/models/scrape_run.py` | Per-scrape outcome, iterations, cost, elapsed |
| `backend/app/models/api_cost_log.py` | Every LLM/Google Maps cost event |
| `backend/app/services/scraper_agent/` | Agent + browser tools + path cache + compliance + content_hash |
| `backend/app/services/scraper_agent/content_hash.py` | SHA256 of stripped HTML for scrape short-circuit |
| `backend/app/services/google_maps.py` | Places API (New) with GooglePlaceRaw dedup |
| `backend/app/services/price_checker.py` | Price-drop detection (Phase A semantics) |
| `backend/app/services/notification.py` | SendGrid + Telegram, rich templates |
| `backend/app/worker.py` | Celery tasks, beat schedule, scrape pipeline, `_match_plan`, `_persist_scraped_prices` |
| `backend/alembic/versions/` | 23+ migrations |
| `app/src/pages/` | `ListingsPage`, `ListingDetailPage`, `AlertsPage`, `FavoritesPage`, `UnsubscribePage` |
| `app/src/components/` | `AlertModal`, `AuthModal`, `FilterPanel`, `ListingCard`, `MapView` |
| `dev/cost_summary.py` | CLI reader for `api_cost_log` |
| `dev/audit.py` | (to be added during B1-B5 fixes) SQL audit of plan sqft/name coverage |
| `docs/dogfood-papercuts.md` | 2-week dogfood UX tracking |

> **Note on scraper code duplication**: `backend/app/services/scraper_agent/` and `tests/integration/agentic_scraper/` hold parallel copies of `agent.py`, `browser_tools.py`, `models.py`, `path_cache.py`. Any change must be applied to both. Consolidation is deferred tech debt.

---

## Data Model

```
User (1) ──► (N) PriceSubscription
                     │ FK to apartment/plan (area-level disabled)
                     │ baseline_price, baseline_recorded_at, trigger_count
                     │ is_demo, unsubscribe_token

User (1) ──► (N) ApartmentFavorite

Apartment (1) ──► (N) Plan (1) ──► (N) PlanPriceHistory
    │                   │
    │                   ├──► external_url, floor_level, facing
    │                   └──► current_price (live value, kept in sync by worker)
    │
    │   last_content_hash, last_scraped_at (scrape short-circuit)
    │   current_special (move-in offer)

PriceSubscription (1) ──► (N) NotificationEvent (sent/delivered/opened/clicked/bounced)

ScrapeSiteRegistry (keyed by domain, 1:N Apartments)
GooglePlace + GooglePlaceRaw (dedup cache, keyed by place_id)
ScrapeRun (per-scrape outcome + cost + elapsed)
ApiCostLog (every LLM / Google Maps cost event)
```

**B5 will add**: `PasswordResetToken` (user_id FK, token unique, expires_at, used_at).

---

## Agentic Scraper

**Files**: `backend/app/services/scraper_agent/{agent.py, browser_tools.py, models.py, path_cache.py, compliance.py, content_hash.py}`.

**Loop**: LLM sees structured page state (BeautifulSoup — never screenshots) → decides tool call → `BrowserSession` executes via Playwright → observation → repeat until `submit_findings` or 22-iter no-data early stop.

**Tools**: `navigate_to`, `click_link`, `click_button`, `scroll_down`, `read_iframe`, `extract_all_units`, `submit_findings`.

**Model**: `MiniMax-M2.5` via OpenAI-compatible API. $0.30/M input, $1.10/M output.

**Scrape flow in worker.py per apartment**:

1. **Content-hash short-circuit** — HTTP GET + `compute_content_hash` → if `last_content_hash` unchanged: `_carry_forward_prices`, write `ScrapeRun outcome="content_unchanged"`, return. **0 LLM, 0 Playwright**.
2. **Path cache replay** (`load_path(url)`) — if cached, replay browser steps only, parse via `_parse_units_to_apartment_data`. **0 LLM calls**.
3. **Full ReAct loop** (cache miss or replay fail) — agent runs, max 35 iter, early stop at 22 no-data.
4. `_sanitize(result)` strips price-slider contamination.
5. **`_persist_scraped_prices`** — writes `PlanPriceHistory`, updates `Plan.current_price`, apartment `current_special`, `last_content_hash`. **⚠ Currently DOES NOT update area_sqft / bedrooms / bathrooms / name — see B1.**
6. **`_match_plan`** — exact name → fuzzy (beds+sqft ±10%). **⚠ Currently returns None on mismatch, dropping data — see B2.**

---

## Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `task_check_price_drops` | Daily 08:00 PT | Check subscriptions, send alerts, auto-pause on fire |
| `task_refresh_apartment_data` | Daily 02:00 PT | Re-scrape all `is_available` apartments |
| `task_daily_health_report` | Daily 09:00 PT | **(to add during Week 1 dogfood)** email admin summary |

---

## Auth & Security

- JWT (HS256), 24h expiry, bcrypt passwords.
- `require_admin` on write endpoints + Google Maps import.
- `get_current_user` on subscription endpoints, scoped to own `user_id`.
- GET endpoints public.
- Rate limits: write 10/min, auth 5/min, read 60/min, import 3/hr.
- `JWT_SECRET_KEY` validator refuses default in production.
- `unsubscribe_token` unguessable, per-subscription.
- **⚠ B5 outstanding**: current `/auth/reset-password` accepts unauthenticated password change by email. Fix before dogfood.

---

## Scraper Compliance (hard rules)

- NEVER scrape Craigslist or UGC aggregators (`Craigslist v. RadPad` $60.5M).
- NEVER scrape behind login walls.
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
python dev/audit.py                                            # (after B1-B5)
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

1. **B1-B5 outstanding** (see top section).
2. **Scraper code duplication** between `scraper_agent/` and `tests/integration/agentic_scraper/`.
3. **`Plan.price` deprecated** but still populated by seed script — remove after confirming no read paths use it.
4. **`ApartmentImage` table unused** — added for future image support; will repurpose or drop.
5. **Cost log JSONL fallback** (legacy path in `cost_log.py`) — remove after `api_cost_log` proven stable in production.
6. **`extract_all_units` capped at 15 floors** — insufficient for high-rise SF (NEMA 23 floors, Austin 42). Bump to 30.

---

## References

- `.claude/prompts.md` — copy-paste prompts for B1-B5 fixes + dogfood + post-dogfood work.
- `backend/app/services/scraper_agent/compliance.py` — legal context, C&D protocol, case citations.
- `docs/dogfood-papercuts.md` — active UX log during dogfood.
- `dev/cost_summary.py` — API spend observability.
- `dev/audit.py` (to be added) — plan data-quality SQL audit.