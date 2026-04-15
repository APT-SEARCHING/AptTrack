# AptTrack

Bay Area apartment rental tracking system. Aggregates listings via Google Maps API and an LLM-powered agentic browser scraper; stores price history in PostgreSQL; serves a REST API with JWT auth consumed by a React frontend. Users can subscribe to price-drop alerts delivered via email or Telegram. Celery handles scheduled scraping and alert checks.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐     ┌────────────┐
│  React / TypeScript  │◄───►│  FastAPI (Python)     │◄───►│ PostgreSQL │
│  Tailwind CSS        │     │  Pydantic v1          │     │ 14-alpine  │
│  Recharts            │     │  SQLAlchemy <2.0      │     └────────────┘
└─────────────────────┘     │  Alembic              │
                             │  slowapi (rate limit)  │     ┌────────────┐
                             │  JWT auth (jose)       │◄───►│   Redis    │
                             └────────┬───────────────┘     │  7-alpine  │
                                      │                      └────────────┘
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                   ▼
           Google Maps API   Scraper Agent          Celery Worker + Beat
           (Places New)      MiniMax-M2.5 +         daily price check
                             Playwright             daily data refresh
```
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
## Key Directories

| Path | Purpose |
|------|---------|
| `backend/app/api/api_v1/endpoints/` | REST endpoints: apartments, auth, neighborhoods, search, statistics, subscriptions |
| `backend/app/models/apartment.py` | Apartment, Plan, PlanPriceHistory, ApartmentImage, Neighborhood |
| `backend/app/models/user.py` | User, PriceSubscription |
| `backend/app/schemas/` | Pydantic request/response schemas (apartment.py, user.py) |
| `backend/app/core/security.py` | JWT + bcrypt + `get_current_user` / `require_admin` dependencies |
| `backend/app/core/limiter.py` | Shared slowapi Limiter singleton |
| `backend/app/core/config.py` | Settings via Pydantic BaseSettings, reads `.env` |
| `backend/app/services/scraper_agent/` | **Agentic scraper** — MiniMax M2.5 + Playwright |
| `backend/app/services/google_maps.py` | Google Maps Places API (New), ~500 LOC |
| `backend/app/services/price_checker.py` | Price-drop detection (plan/apartment/area level, 24h debounce) |
| `backend/app/services/notification.py` | SendGrid email + Telegram bot (fire-and-forget) |
| `backend/app/worker.py` | Celery app, beat schedule, tasks, graceful shutdown handler |
| `backend/alembic/` | 10 migration versions |
| `app/src/services/api.ts` | Real API client + adapter layer + mock fallback |
| `app/src/context/AuthContext.tsx` | JWT token in React Context + localStorage |
| `app/src/pages/` | ListingsPage (two-level), ListingDetailPage, AlertsPage |
| `tests/integration/agentic_scraper/` | 16 scraper tests (unit + integration) |
| `seed_apartments.py` | Scrapes 10 real Bay Area apartments, seeds database |

## Data Model

```
User (1) ──► (N) PriceSubscription
                      │ optional FK to apartment/plan
Apartment (1) ──► (N) Plan (1) ──► (N) PlanPriceHistory
    │
    └──► (N) ApartmentImage

Neighborhood (standalone, no FK)
```

## Auth & Security

- JWT (HS256) via `python-jose`, 24h expiry, bcrypt passwords.
- `require_admin` on all apartment/plan/image/neighborhood write endpoints + Google Maps import.
- `get_current_user` on subscription endpoints, scoped to own user_id.
- GET endpoints are public.
- Rate limiting: write 10/min, auth 5/min, read 60/min, import 3/hr.
- JWT_SECRET_KEY validator refuses to start in production with default value.

## API Endpoints (all under /api/v1)

**Public:** GET apartments, GET apartments/{id}, GET search, GET stats/*, GET neighborhoods, GET health, POST auth/register, POST auth/login.

**Authenticated:** GET auth/me, CRUD /subscriptions (own user only).

**Admin:** POST/PUT/DELETE apartments, plans, images, neighborhoods; POST apartments/import/google-maps.

## Agentic Scraper

Files: `backend/app/services/scraper_agent/` (agent.py, browser_tools.py, models.py).

ReAct loop: LLM sees structured page state (text/links/buttons/iframes from BeautifulSoup, NOT screenshots) → decides tool call → BrowserSession executes via Playwright → result appended to conversation → repeat until `submit_findings`.

Tools: `navigate_to`, `click_link`, `click_button`, `scroll_down`, `read_iframe`, `extract_all_units`, `submit_findings`.

`_sanitize()` removes price-slider contamination. `ScrapeMetrics` tracks tokens + cost per scrape.

MiniMax API: base URL `https://api.minimax.io/v1`, model `MiniMax-M2.5`, $0.30/M input, $1.10/M output.

**Token cost concern:** Full conversation history resent each iteration. 6-10 iterations per apartment = 80K-250K tokens. Daily scraping of 10 sites = $3-9/month. Navigation path caching (not yet built) would reduce to near-zero for repeat visits.

## Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `task_check_price_drops` | Daily 08:00 PT | Check subscriptions, send alerts |
| `task_refresh_apartment_data` | Daily 02:00 PT | Re-scrape apartments, update PlanPriceHistory |

## Docker Services

backend, frontend, db (postgres), redis, celery-worker, celery-beat — 6 services total.

## Environment Variables

See `.env.example`. Critical: `DATABASE_URL`, `JWT_SECRET_KEY` (must change for prod), `MINIMAX_API_KEY` (for scraper), `REDIS_URL`.

## Development

```bash
./start.sh          # Docker full stack
./start.sh local    # Local dev
python seed_apartments.py  # Seed with real data
pytest tests/unit/ -v
pytest tests/integration/agentic_scraper/ -m "not integration" -v
```

## Coding Conventions

- Python 3.11, type hints, SQLAlchemy ORM. Pydantic v1 style.
- Endpoints in domain folders, each with core.py + __init__.py router assembly.
- Every write endpoint needs `@limiter.limit()` + auth dependency.
- Frontend: React functional + hooks, TypeScript strict, Tailwind.
- Tests: pytest, `@pytest.mark.integration` for network tests.
- Lint: ruff (backend/ruff.toml), 120 char lines.

## Known Tech Debt

- Pydantic v1 + SQLAlchemy 1.4 — should migrate to v2 of both.
- `_persist_scraped_prices` matches by `Plan.name` — fragile if sites rename plans.
- Agent opens new browser per apartment — could reuse browser context in batch.
- No API endpoint integration tests (TestClient + test DB).
- High token consumption for daily re-scraping — needs path caching.

## Scraper Compliance

AptTrack scrapes individual apartment complex websites (NOT aggregator platforms). This is relatively low-risk: public data, no login required, factual pricing only. Key legal protections: hiQ v. LinkedIn (9th Cir. 2022) and Meta v. Bright Data (N.D. Cal. 2024) confirm logged-off scraping of public data is lawful.

**Current gaps (to be built):**
- No robots.txt checking — scraper should verify before each target
- User-Agent spoofs Chrome — should identify as `AptTrack/1.0 (rental research bot)`
- No site registry — should track each domain's robots.txt status, ToS review, and platform type
- No inter-scrape delay — should add 5s pause between apartments in batch runs
- No C&D response protocol documented in code

**Hard rules:**
- NEVER scrape Craigslist (Craigslist v. RadPad: $60.5M judgment)
- NEVER scrape behind login walls
- NEVER collect personal information (user emails, personal phone numbers)
- IMMEDIATELY comply with any cease & desist letter
- Only store factual data: prices, sqft, bedrooms, availability

## What's NOT Built Yet

1. ML price prediction (Prophet time-series, XGBoost cross-sectional)
2. "Best time to rent" seasonal analysis
3. Navigation path caching for scraper (token optimization)
4. Scraper compliance registry (site-level robots.txt / ToS tracking)
5. Public data integration (ZORI, Apartment List, HUD FMR)
6. Crowdsourced actual lease prices
7. Geographic expansion beyond Bay Area