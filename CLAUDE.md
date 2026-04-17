# AptTrack

Bay Area apartment **rental price transparency and history** system. Collects publicly available listing prices from individual apartment complex websites; stores full price history in PostgreSQL; serves a REST API with JWT auth consumed by a React frontend. Users can subscribe to price-drop alerts delivered via email or Telegram. Celery handles scheduled scraping and alert checks.

> **Positioning note**: This is a *transparency + history* product, not a daily-arbitrage tool. See **Regulatory Context** below for why the cadence assumptions shifted in 2026.

---

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌────────────┐
│  React / TypeScript │◄───►│  FastAPI (Python)    │◄───►│ PostgreSQL │
│  Tailwind CSS       │     │  Pydantic v2         │     │ 14-alpine  │
│  Recharts           │     │  SQLAlchemy 2.0      │     └────────────┘
└─────────────────────┘     │  Alembic             │
                            │  slowapi (rate lim.) │     ┌────────────┐
                            │  JWT auth (jose)     │◄───►│   Redis    │
                            └────────┬─────────────┘     │  7-alpine  │
                                     │                    └────────────┘
                 ┌───────────────────┼───────────────────┐
                 ▼                   ▼                   ▼
        Google Maps Places   Agentic Scraper      Celery Worker + Beat
        (New API, Essent.)   MiniMax-M2.5 +       adaptive refresh
                             Playwright           daily alert check
                             + path cache (1.3)
                             + content hash
```

---
## Compliance Principles

### 1. Public Data Only

We only collect **publicly accessible rental data**.

### 2. No Content Replication

We do NOT store or display: - Listing descriptions - Images - HTML
content

### 3. Data Transformation

We transform raw data into: - Aggregated statistics - Trends - Insights

We do NOT reproduce full listings.

### 4. Source Attribution

Every property page must include: → "View official listing"

## Regulatory Context (2026)

AptTrack is **not the target** of recent rental-pricing enforcement, but the regulatory landscape changed the underlying market dynamics that inform product decisions.

### What happened

- **California AB 325** (effective 2026-01-01) amended the Cartwright Act to prohibit **competitors sharing a common pricing algorithm**. Targets hub-and-spoke SaaS coordination (YieldStar, RENTmaximizer, RevenueIQ).
- **DOJ v. RealPage settlement** (2025-11-24) forces RealPage to stop using non-public competitor data.
- **San Francisco (2024-08)** and **Berkeley (2024-09)** banned algorithmic rent-setting at the city level.

### Why AptTrack is not in scope

1. We **collect publicly accessible data** from individual listing pages — not private landlord data.
2. We **serve tenants**, not landlords. AB 325 regulates supply-side coordination.
3. We are **not a hub**. No landlord provides us with data; no landlord receives pricing recommendations from us.

Legal precedents remain intact: **hiQ v. LinkedIn (9th Cir. 2022)** and **Meta v. Bright Data (N.D. Cal. 2024)** confirm scraping publicly accessible, logged-off data is lawful.

### What DID change (product implications)

- **Daily price changes are now rare**. Most Bay Area complexes moved from YieldStar dynamic pricing (daily) to static pricing (monthly). Daily refresh captures little signal on most sites.
- **Value moved from "change velocity" to "long-term history + cross-complex comparison"**.
- **A new product angle opened**: detecting regime changes in pricing cadence as a signal of AB 325 compliance status. Potentially valuable to Attorney General office, housing advocacy groups, researchers.

### Hard rule — do NOT build

Any feature that takes **money from landlords or property managers in exchange for pricing advice** could re-classify AptTrack as a "shared algorithm hub" under AB 325. Keep the monetization path strictly **tenant-facing (B2C)** or **data-feed to researchers/investors (B2B read-only)**.

---

## Current State (as of 2026-04)

### Done and working

- Agentic scraper with MiniMax-M2.5, 7 tools, ReAct loop, max 35 iterations, 22-iter no-data early stop.
- **Phase 1 token optimizations** (commit `993d61c6`):
  - `1.1` History trimming (`_trim_messages(keep_last=4)`)
  - `1.2` Reduced page state (`MAX_TEXT_CHARS=4000`, `MAX_LINKS=20`, `MAX_BUTTONS=15`) with pricing-keyword priority truncation
  - `1.3` Path caching (`path_cache.py`, 30-day TTL, per-domain JSON, 4 sites currently cached)
  - `1.4` Browser reuse across batch (`_NullContextManager`, shared `BrowserSession`)
- Price-slider contamination defense (`_sanitize()`).
- **Scraper compliance registry** (`ScrapeSiteRegistry` + `compliance.py`) with robots.txt checking, ToS review fields, C&D response protocol.
- Fuzzy plan matching in `_persist_scraped_prices` (bedrooms + sqft ±10%) to survive plan renames.
- JWT auth, price-drop subscriptions (apartment/plan level only; area-level disabled, see Phase A), 24h debounce, SendGrid + Telegram notifications.
- **Pydantic v2 + SQLAlchemy 2.0** migration complete.
- CI/CD with ruff, security hardening, API integration tests.
- RentCafe plan-card parser for `units_grid--item` sites (The Ryden, Atlas Oakland, Asher Fremont).
- **Phase A price-checker correctness fixes** (5 bugs):
  - Bug #1: `_is_triggered` now detects only the ≥→< crossing; subscriptions **auto-pause** (`is_active=False`) after firing; `trigger_count` column tracks fire history.
  - Bug #2: `price_drop_pct` anchored to `baseline_price` (subscription-time snapshot), not the previous scrape. `baseline_price` + `baseline_recorded_at` columns added; inferred from latest `PlanPriceHistory` → `Plan.price` → `None` at creation time.
  - Bug #3: Debounce timezone handling fixed (`astimezone()` not `.replace(tzinfo=)`).
  - Bug #4: `_get_latest_price` for plan-level subs returns `None` when no `PlanPriceHistory` exists (no stale `Plan.price` fallback).
  - Bug #5: Area-level subscriptions rejected at API layer with 422; existing rows deactivated via migration.

### Metrics (self-reported, commit `993d61c6`)

| Scenario | Before Phase 1 | After Phase 1 |
|---|---|---|
| Cache hit (SightMap/RentCafe) | — | $0.000 |
| Cache miss (trimmed) | $0.05–$0.12 | ~$0.02 |

---

## Phase 2: Bay-Area-Wide Expansion

**Goal**: scale from ~10 seeded apartments to ~3,000 Bay Area complexes (Yardi Matrix 50+ unit count) with adaptive refresh cadence, total monthly cost under $100.

### Hard blockers (must fix before scaling)

1. **`worker.py:task_refresh_apartment_data` is serial** (L108–142). A 3,000-apartment batch with 80s/apt would take ~40h. Must shard into Celery chunks (e.g., 50 apts per chunk, errors don't take down the batch).

2. **Celery beat has no jitter**. 02:00 PT hardcoded; 3,000 concurrent requests to 3,000 sites will trigger anti-bot + overload our own Playwright pool.

3. **`google_maps.py:fetch_apartments_by_location` runs 15 synonymous keywords** (L44–62). Cut to 2–3. Remove `X-Goog-FieldMask: "*"` (triggers $20/1K Enterprise tier); use Essentials (`id,displayName,location`) for discovery and request Pro fields (`websiteUri`, `rating`) only for places that pass the filter.

4. **`path_cache._domain_key` ignores URL path**. `/apartments/ca/palo-alto/...` and `/apartments/ca/mountain-view/...` collide on the same file. Use `domain + md5(path)[:8]`.

5. **No HTML content-hash short-circuit**. Between `load_path()` and running the agent, add an `aiohttp.get` + hash check against `apartment.last_content_hash`. 40–70% of daily scrapes will be "content unchanged, carry forward prices" — zero LLM, zero Playwright.

### Also worth doing

- **Adaptive refresh cadence**: new `Apartment.next_refresh_at` column; weekly default, escalate to daily for apartments with ≥2 price changes in trailing 14 days, back off to weekly after 30 days of no changes. Cuts daily scrape volume 60–85%.
- **`ScrapeRun` observability table** (persist `ScrapeMetrics.summary()` to DB, generate nightly Telegram digest: total cost, cache hit rate, failed sites).
- **Tiered model routing**: keep MiniMax-M2.5 default; consider DeepSeek V3.2 (automatic 90% prompt cache discount, ~2× cheaper) for long-tail sites where cache miss is common. Do NOT migrate blindly — validate tool-calling fidelity on 20 existing fixtures first.
- **Verify MiniMax prompt caching is active**: read `response.usage.cached_tokens` (or whatever the MiniMax equivalent is). If always 0, the SYSTEM_PROMPT prefix isn't being cached; either fix the call signature or switch to DeepSeek where caching is automatic.

### Infrastructure

- Phase 1 (500 apts): Hetzner CPX31 ($14/mo, 4 vCPU/8GB) sufficient.
- Phase 2 (3,000 apts): CPX41 ($26/mo, 8 vCPU/16GB) or 2× CPX31. Playwright browser-hours become the binding constraint once path cache hit rate ≥70%.

**Do not scale Postgres or Redis for Phase 2** — even at 3,000 apts × 3 plans × 365 days × 5 years the row count is ~16M, fits on any Hobby tier.

---

## Key Directories

| Path | Purpose |
|------|---------|
| `backend/app/api/api_v1/endpoints/` | REST endpoints (apartments, auth, neighborhoods, search, statistics, subscriptions) |
| `backend/app/models/apartment.py` | `Apartment`, `Plan`, `PlanPriceHistory`, `ApartmentImage`, `Neighborhood` |
| `backend/app/models/user.py` | `User`, `PriceSubscription` |
| `backend/app/models/site_registry.py` | `ScrapeSiteRegistry` (compliance per-domain state) |
| `backend/app/models/google_place.py` | Cached Google Places data (place_id permanent under ToS §3.2.3(b)) |
| `backend/app/schemas/` | Pydantic v2 request/response schemas |
| `backend/app/core/security.py` | JWT + bcrypt + `get_current_user` / `require_admin` |
| `backend/app/core/limiter.py` | Shared slowapi `Limiter` |
| `backend/app/core/config.py` | Settings via Pydantic BaseSettings, `.env` |
| `backend/app/services/scraper_agent/` | **Agentic scraper + compliance.py + path_cache** |
| `backend/app/services/google_maps.py` | Google Maps Places API (New) |
| `backend/app/services/price_checker.py` | Price-drop detection (24h debounce) |
| `backend/app/services/notification.py` | SendGrid + Telegram (fire-and-forget) |
| `backend/app/worker.py` | Celery app, beat schedule, tasks, SIGTERM handler |
| `backend/alembic/versions/` | 11 migrations |
| `app/src/pages/` | `ListingsPage` (two-level), `ListingDetailPage`, `AlertsPage` |
| `app/src/services/api.ts` | API client + mock fallback |
| `tests/integration/agentic_scraper/` | Scraper tests + batch_runner + legacy modular_scraper |
| `tests/integration/agentic_scraper/path_cache/` | Cached navigation paths (JSON per domain) |
| `seed_apartments.py` | Scrapes 10 real Bay Area apartments, seeds DB |

> **Note on duplication**: `backend/app/services/scraper_agent/` and `tests/integration/agentic_scraper/` currently hold parallel copies of `agent.py`. The worker imports from `backend/app/services/scraper_agent/`. Any agent change must be applied to both until consolidated (see **Tech Debt**).

---

## Data Model

```
User (1) ──► (N) PriceSubscription
                     │ optional FK to apartment/plan
Apartment (1) ──► (N) Plan (1) ──► (N) PlanPriceHistory
    │
    └──► (N) ApartmentImage

ScrapeSiteRegistry (keyed by domain, 1:N Apartments)
GooglePlace (cached, keyed by place_id)
Neighborhood (standalone)
```

---

## Agentic Scraper

**Files**: `backend/app/services/scraper_agent/{agent.py, browser_tools.py, models.py, path_cache.py, compliance.py}`.

**Loop**: LLM sees structured page state (text/links/buttons/iframes from BeautifulSoup — **never screenshots**) → decides a tool call → `BrowserSession` executes via Playwright → observation appended → repeat until `submit_findings` or hard stop.

**Tools**: `navigate_to`, `click_link`, `click_button`, `scroll_down`, `read_iframe`, `extract_all_units`, `submit_findings`.

**Model**: `MiniMax-M2.5` via OpenAI-compatible API at `https://api.minimax.io/v1`. Pricing: $0.30/M input, $1.10/M output.

**Scrape flow** (current):
1. `load_path(url)` → if cached, replay tool calls via browser only (0 LLM calls), parse via `_parse_units_to_apartment_data`.
2. If cache miss or replay fails, invalidate cache and run full ReAct loop.
3. On success, `save_path(url, ...)` stores the trace for next time. Only paths ending in `extract_all_units` are cached (only deterministic-replay action).
4. `_sanitize(result)` runs on all output to strip price-slider contamination.

**Scrape flow** (after Phase 2 blockers fixed):
1. HTTP GET + content hash → if unchanged since yesterday, carry forward prices (0 LLM, 0 Playwright).
2. `load_path(url)` → replay if cached.
3. Full ReAct loop only if both above miss.

---

## Celery Tasks

| Task | Current Schedule | Purpose |
|------|------------------|---------|
| `task_check_price_drops` | Daily 08:00 PT | Check subscriptions, send alerts |
| `task_refresh_apartment_data` | Daily 02:00 PT | Re-scrape all `is_available` apartments |

**Phase 2 changes**: `task_refresh_apartment_data` becomes a dispatcher; actual work moves to `task_refresh_apartment_chunk` (50 apts/chunk, countdown-staggered). Only apartments with `next_refresh_at <= now()` get dispatched.

---

## Auth & Security

- JWT (HS256) via `python-jose`, 24h expiry, bcrypt passwords.
- `require_admin` on all write endpoints + Google Maps import.
- `get_current_user` on subscription endpoints, scoped to own `user_id`.
- GET endpoints are public.
- Rate limits: write 10/min, auth 5/min, read 60/min, import 3/hr.
- `JWT_SECRET_KEY` validator refuses to start in production with default value.
- **Never commit `.env`**; `.env.example` is the template.

---

## Scraper Compliance (hard rules)

- **NEVER scrape Craigslist or other UGC/marketplace aggregators.** `Craigslist v. RadPad` (N.D. Cal. 2017) = $60.5M judgment.
- **NEVER scrape behind login walls.**
- **NEVER collect PII** (user emails, personal phone numbers, names).
- **Only store factual data**: prices, sqft, bedrooms, availability, business phone, official listing URL.
- **robots.txt must be checked before adding any new domain** (`ScrapeSiteRegistry.robots_txt_allows`).
- **C&D protocol**: On any cease & desist, `is_active=False` on the registry row → delete all `Apartment` rows from that domain → respond within 48h → log in `ceased_reason`. See top-of-file docstring in `compliance.py`.
- **User-Agent**: identify honestly. Do not impersonate Chrome to bypass bot detection.
- **Rate limit**: 5s minimum between scrapes of the same domain.

---

## Environment Variables

See `.env.example`. Critical: `DATABASE_URL`, `JWT_SECRET_KEY` (must change for prod), `MINIMAX_API_KEY`, `GOOGLE_MAPS_API_KEY`, `REDIS_URL`, `SENDGRID_API_KEY`, `TELEGRAM_BOT_TOKEN`.

---

## Development

```bash
./start.sh                    # Docker full stack
./start.sh local              # Local dev
python seed_apartments.py     # Seed with 10 real apartments
pytest tests/unit/ -v         # Unit tests (no network)
pytest tests/integration/agentic_scraper/ -m "not integration" -v   # Scraper unit tests
pytest tests/integration/agentic_scraper/ -m integration -v         # Live scraper (needs MINIMAX_API_KEY)
alembic revision --autogenerate -m "description"                     # New migration
alembic upgrade head                                                 # Apply
ruff check backend/                                                  # Lint
```

---

## Coding Conventions

- Python 3.11, type hints required on all public functions, SQLAlchemy 2.0 ORM syntax (`select(...)`).
- Pydantic v2 (`model_dump`, `model_validate`, not `dict()`/`parse_obj`).
- Endpoints organized by domain in folders, each with `core.py` + `__init__.py` router assembly.
- Every write endpoint: `@limiter.limit(...)` + auth dependency.
- Frontend: React functional + hooks, TypeScript strict, Tailwind.
- Tests: pytest, `@pytest.mark.integration` for network tests.
- Lint: ruff (`backend/ruff.toml`), 120-char lines.

---

## Tech Debt (active)

1. **Scraper code duplication** between `backend/app/services/scraper_agent/` and `tests/integration/agentic_scraper/`. Consolidate to one location; tests should import from the service module.
2. **Serial Celery refresh** (Phase 2 blocker #1 above).
3. **Domain-only path cache key** (Phase 2 blocker #4 above).
4. **15-keyword Google Maps discovery** (Phase 2 blocker #3 above).
5. **No `ScrapeRun` table** — every scrape's metrics live in memory only; can't retrospectively analyze cost/quality drift.
6. **No frontend map view** — listings are list-only; map view on the roadmap.
7. **Mock adapter fallback in `api.ts`** should be deleted once Phase 2 backend is stable.

---

## What's NOT Built

1. ML price prediction (Prophet, XGBoost).
2. "Best time to rent" seasonal analysis.
3. Public data integration (ZORI, Apartment List, HUD FMR) for cross-validation.
4. Crowdsourced actual lease prices.
5. Geographic expansion beyond Bay Area.
6. Adaptive refresh cadence (Phase 2).
7. Content-hash short-circuit (Phase 2).
8. Nightly cost/quality digest (Phase 2).
9. Transparency dashboard for AB 325 regime-change detection (product positioning opportunity).

---

## References

- `.claude/instructions.md` — working rules for Claude Code on this repo.
- `backend/app/services/scraper_agent/compliance.py` — legal context, C&D protocol, case citations.
- `CLAUDE.md` (this file) — living project doc; update it when architecture changes.