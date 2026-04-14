# AptTrack

Apartment rental tracking system. Aggregates listings from Google Maps, web scraping, and an agentic browser-based scraper; tracks price history; serves a REST API consumed by a React frontend.

## Architecture

```
React (TypeScript + Tailwind)  ←→  FastAPI (Python)  ←→  PostgreSQL
                                          ↑
                              Agentic Scraper (Minimax + Playwright)
```

## Key Directories

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI app, SQLAlchemy models, Alembic migrations |
| `app/` | React + TypeScript frontend |
| `tests/unit/` | Unit tests (no network) |
| `tests/integration/agentic_scraper/` | **New agentic scraper** — Minimax + Playwright |
| `tests/integration/modular_scraper/` | Legacy HTML-dump + LLM-codegen scraper |
| `tests/integration/legacy_scraper/` | Oldest scraper, kept for reference |

## Agentic Scraper

Located at `tests/integration/agentic_scraper/`. Replaces the fragile HTML-dump → LLM-code-gen pipeline with an agent that directly controls a browser.

### How it works

1. `ApartmentAgent.scrape(url)` sends the URL to **MiniMax-M2.5** via the OpenAI-compatible API.
2. The model calls browser tools (`navigate_to`, `click_link`, `click_button`, `scroll_down`) in a loop until it has found floor plan and pricing data.
3. When done, it calls `submit_findings` with structured JSON, which terminates the loop and returns an `ApartmentData` Pydantic model.

### Files

```
tests/integration/agentic_scraper/
├── models.py        # ApartmentData, FloorPlan Pydantic models
├── browser_tools.py # BrowserSession wrapping Playwright async API
├── agent.py         # ApartmentAgent class + TOOLS definitions
└── test_agentic_scraper.py  # Unit + integration tests
```

### Running

```bash
# Install test deps
pip install -r tests/requirements-test.txt
playwright install chromium

# Unit tests only (no network, no API key needed)
pytest tests/integration/agentic_scraper/test_agentic_scraper.py -m "not integration"

# Integration tests (real browser + real Minimax API)
MINIMAX_API_KEY=your_key pytest tests/integration/agentic_scraper/test_agentic_scraper.py -m integration -v -s
```

## Environment Variables

Copy `.env.example` to `.env` and fill in:

| Variable | Description |
|----------|-------------|
| `MINIMAX_API_KEY` | Minimax API key (required for agentic scraper) |
| `GOOGLE_MAPS_API_KEY` | Google Maps Places API key |
| `DATABASE_URL` | PostgreSQL connection string |

## Minimax API

- **Base URL:** `https://api.minimax.io/v1`
- **Model:** `MiniMax-M2.5`
- **Client:** `openai.AsyncOpenAI(base_url=..., api_key=MINIMAX_API_KEY)`
- Uses OpenAI-compatible chat completions with function/tool calling.

## Development

```bash
# Backend (hot reload)
cd backend && uvicorn app.main:app --reload

# Frontend (hot reload)
cd app && npm start

# Database only
docker compose up -d db
```

## Test Conventions

- Tests are plain `pytest` files; async tests use `pytest-asyncio`.
- Integration tests are marked `@pytest.mark.integration` and skipped in CI unless explicitly enabled.
- Unit tests mock all network and browser I/O — they must pass with no credentials or internet.
