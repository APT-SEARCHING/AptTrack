# AptTrack

Bay Area apartment rental tracking system. Aggregates listings via Google Maps API and an LLM-powered agentic browser scraper; stores price history in PostgreSQL; serves a REST API consumed by a React frontend. Goal: price drop alerts + ML rent prediction for tenants.

## Architecture

```
┌─────────────────────┐     ┌──────────────────┐     ┌────────────┐
│  React / TypeScript  │◄───►│  FastAPI (Python) │◄───►│ PostgreSQL │
│  Tailwind CSS        │     │  Pydantic v1      │     │ 14-alpine  │
│  Recharts            │     │  SQLAlchemy <2.0   │     └────────────┘
└─────────────────────┘     │  Alembic           │
                             └────────┬───────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                   ▼
           Google Maps API    Agentic Scraper       Celery (planned)
           (Places New)       MiniMax-M2.5 +        price alerts
                              Playwright             scheduling
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
| `backend/app/api/api_v1/endpoints/` | REST endpoints grouped by domain |
| `backend/app/models/apartment.py` | SQLAlchemy models: Apartment, Plan, PlanPriceHistory, ApartmentImage, Neighborhood |
| `backend/app/schemas/apartment.py` | Pydantic request/response schemas |
| `backend/app/services/google_maps.py` | Google Maps Places API (New) integration, ~500 LOC |
| `backend/app/services/apartment_db_service.py` | DB helper for upsert operations |
| `backend/app/core/config.py` | Settings via Pydantic BaseSettings, reads `.env` |
| `backend/alembic/` | 5 migration versions |
| `app/src/` | React frontend (TypeScript) |
| `app/src/services/api.ts` | **Currently uses mock data, NOT real API** |
| `app/src/services/mockData.ts` | Hardcoded fake listings |
| `tests/integration/agentic_scraper/` | MiniMax + Playwright agent (best code in repo) |
| `tests/integration/modular_scraper/` | Legacy HTML-dump + LLM codegen (deprecated) |
| `tests/integration/legacy_scraper/` | Oldest scraper (deprecated) |

## Data Model

```
Apartment (1) ──► (N) Plan (1) ──► (N) PlanPriceHistory
    │
    └──► (N) ApartmentImage

Neighborhood (standalone, not FK-linked)
```

Key fields on Apartment: `external_id` (unique, from source), `city`, `zipcode`, `latitude/longitude`, `property_type`, amenity booleans, `source_url`, `rating`.

Key fields on Plan: `name`, `bedrooms`, `bathrooms`, `area_sqft`, `price`, `is_available`.

PlanPriceHistory: `plan_id`, `price`, `recorded_at` — the core time-series data for tracking.

## Known Bugs & Tech Debt

### Critical (app won't start)
- **`backend/app/main.py:7`** imports `from app.services.scraper import IrvineApartmentsScraper` — this file was deleted. Backend crashes on startup. Remove this import line and the unused import of `repeat_every`, `get_db`, `Session`.

### Severe (repo hygiene)
- **`app/node_modules/`** is committed to git (44,300 files, 388MB). Run: `git rm -r --cached app/node_modules && git commit`.
- **`__pycache__/`** dirs committed (11 .pyc files). Run: `git rm -r --cached '**/__pycache__' && git commit`.
- Add to `.gitignore`: `**/__pycache__/`, `*.pyc`, `app/node_modules/`.

### Security
- **Zero authentication** on all endpoints. Any caller can CREATE / DELETE data and trigger Google Maps API calls.
- **API key accepted via POST body** in `import_api.py` — should only come from server-side env var.
- **No rate limiting** — no `slowapi` or equivalent middleware.
- **CORS allows all methods/headers** — fine for dev, tighten for prod.

### Architecture
- **Frontend uses mock data** — `app/src/services/api.ts` never calls the real backend; all data comes from `mockData.ts`.
- **Duplicate import endpoints** — `import.py` and `import_api.py` do the same thing.
- **Task status stored in-memory dict** — lost on restart, broken with multiple workers.
- **No scheduled scraping** — `SCRAPE_INTERVAL_MINUTES` config exists but nothing reads it (no Celery/cron).
- **Agentic scraper lives in tests/** — should be promoted to `backend/app/services/`.

### Dependencies
- Pydantic v1 (1.10.13) — `BaseSettings` will break on upgrade; need `pydantic-settings`.
- SQLAlchemy <2.0 — pinned to 1.4.x; v2 has breaking changes.

## Environment Variables

Copy `.env.example` → `.env`. Required:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:password@db:5432/rental_tracker` |
| `GOOGLE_MAPS_API_KEY` | Google Places API (New) key | — |
| `MINIMAX_API_KEY` | MiniMax M2.5 API key (agentic scraper) | — |
| `BACKEND_PORT` | Backend port | `8000` |
| `FRONTEND_PORT` | Frontend port | `3000` |
| `CORS_ORIGINS` | Comma-separated allowed origins | `http://localhost:3000,http://localhost:8080` |
| `SCRAPE_INTERVAL_MINUTES` | (Not yet wired) | `60` |
| `LOG_LEVEL` | Python logging level | `INFO` |

## API Endpoints

All under `/api/v1`. No auth required (currently).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/apartments` | List/filter apartments |
| POST | `/apartments` | Create apartment |
| GET/PUT/DELETE | `/apartments/{id}` | CRUD single apartment |
| POST | `/apartments/import/google-maps` | Trigger Google Maps import (background task) |
| GET | `/apartments/import/status/{task_id}` | Poll import task status |
| GET/POST | `/apartments/{id}/plans` | List/create plans |
| GET/PUT/DELETE | `/apartments/{id}/plans/{plan_id}` | CRUD single plan |
| GET | `/apartments/{id}/plans/{plan_id}/price-history` | Price history for a plan |
| GET/POST/PUT/DELETE | `/apartments/{id}/images` | Image CRUD |
| GET/POST/PUT/DELETE | `/neighborhoods` | Neighborhood CRUD |
| GET | `/search?query=...` | Full-text search across title/desc/city/zip |
| GET | `/stats/price-trends` | Avg price over time (by day) |
| GET | `/stats/apartments-by-city` | Count per city |
| GET | `/stats/average-price-by-bedrooms` | Avg price grouped by BR count |
| GET | `/health` | Health check |

## Agentic Scraper

The best-engineered component. Located at `tests/integration/agentic_scraper/`.

**How it works:**
1. `ApartmentAgent.scrape(url)` sends URL + system prompt to MiniMax-M2.5 via OpenAI-compatible API.
2. Model calls browser tools in a loop: `navigate_to`, `click_link`, `click_button`, `scroll_down`, `read_iframe`, `extract_all_units`.
3. When data collected, calls `submit_findings` → returns `ApartmentData` Pydantic model.
4. `_sanitize()` post-processor detects/removes prices from slider filters (not real unit prices).
5. Auto-retries on 429/5xx with exponential backoff.

**Files:** `models.py` (Pydantic), `browser_tools.py` (Playwright wrapper), `agent.py` (agent + tools + sanitizer), `batch_runner.py`, `test_agentic_scraper.py` (16 tests).

**MiniMax API:** Base URL `https://api.minimax.io/v1`, model `MiniMax-M2.5`, OpenAI-compatible function calling.

## Development

```bash
# Full stack
docker compose up -d

# Backend only (hot reload) — requires DB running
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend only (hot reload)
cd app && npm install && npm start

# Database only
docker compose up -d db

# Run unit tests (no network/credentials)
pytest tests/unit/ -v
pytest tests/integration/agentic_scraper/ -m "not integration" -v

# Run integration tests (needs MINIMAX_API_KEY)
pytest tests/integration/agentic_scraper/ -m integration -v -s
```

## Coding Conventions

- **Backend:** Python 3.11, FastAPI, type hints everywhere, SQLAlchemy ORM (not raw SQL).
- **Endpoints:** grouped in domain folders under `api/api_v1/endpoints/`, each has `core.py` + `__init__.py` that assembles sub-routers.
- **Schemas:** Pydantic v1 style (`class Config: from_attributes = True`). Separate Create/Update/Response models.
- **Frontend:** React functional components with hooks, TypeScript strict, Tailwind for styling.
- **Tests:** pytest + pytest-asyncio. `@pytest.mark.integration` for tests needing network. Unit tests must pass offline.
- **Async:** Backend endpoints are sync (SQLAlchemy 1.4 sync session). Agentic scraper is fully async.
- **Config:** Single top-level `.env` file, loaded by Pydantic BaseSettings in `backend/app/core/config.py`.

## What's NOT Built Yet

These are the core product features that differentiate AptTrack from competitors:

1. **User system** — no auth, no accounts, no saved preferences
2. **Price drop alerts / subscriptions** — no notification system at all
3. **Scheduled scraping** — no Celery/cron, no periodic data refresh
4. **ML price prediction** — no Prophet/XGBoost/time-series models
5. **"Best time to rent" analysis** — no seasonal decomposition
6. **Frontend ↔ Backend integration** — frontend reads mock data, not real API
