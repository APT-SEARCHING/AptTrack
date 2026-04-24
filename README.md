# AptTrack - Apartment Rental Tracking System

AptTrack is a Bay Area apartment **rental price transparency** system. It collects publicly available listing prices from individual apartment complex websites, stores full price history in PostgreSQL, and serves a REST API consumed by a React frontend. Users can subscribe to price-drop alerts delivered via email or Telegram.

**Live**: https://apttrack-production-6c87.up.railway.app/

## Features

- **Apartment Listings**: Browse and search Bay Area apartments with detailed floor plan info
- **Multiple Floor Plans**: Each apartment has per-plan pricing (beds, baths, sqft, price)
- **Price History Tracking**: Full `PlanPriceHistory` table — every daily scrape is recorded
- **Price Drop Alerts**: Subscribe to a plan; get notified by email or Telegram when price drops
- **Advanced Filters**: Pets, parking, sqft range, available-before date, city multi-select
- **Market Context**: Median rent stats, similar apartments, cheapest-in-city
- **Favorites**: Shortlist apartments for comparison
- **Google Maps Integration**: Import apartment metadata (location, rating, phone) from Google Places

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.11) + Pydantic v2
- **Database**: PostgreSQL 14 + SQLAlchemy 2.0 + Alembic
- **Task Queue**: Celery + Redis (daily scrape at 02:00 PT, alerts at 08:00 PT)
- **Scraper**: MiniMax-M2.5 agentic loop + Playwright + platform adapters (see below)
- **Auth**: JWT (HS256), bcrypt, token-based password reset
- **Notifications**: SendGrid (email) + Telegram Bot API
- **Rate limiting**: slowapi
- **External APIs**: Google Maps Places API (New)

### Frontend
- **Framework**: React 18 + TypeScript
- **Styling**: Tailwind CSS
- **Charts**: Recharts (price history)
- **Maps**: Leaflet
- **Toasts**: sonner
- **Routing**: React Router

### Infrastructure
- **Hosting**: Railway (web + worker + beat + Postgres + Redis)
- **Containerization**: Docker & Docker Compose (local dev)
- **API Documentation**: Swagger UI (via FastAPI)

## Project Structure

```
AptTrack/
├── app/                  # Frontend React application
│   ├── src/
│   │   ├── components/   # Reusable UI components
│   │   ├── pages/        # Page components
│   │   ├── services/     # API service layer
│   │   └── utils/        # Utility functions
│   └── public/           # Static assets
│
├── backend/              # Backend FastAPI application
│   ├── alembic/          # Database migrations
│   ├── app/
│   │   ├── api/          # API endpoints
│   │   │   └── api_v1/
│   │   │       └── endpoints/
│   │   │           ├── apartments/    # Apartment-related endpoints
│   │   │           ├── neighborhoods/ # Neighborhood-related endpoints
│   │   │           ├── search/        # Search functionality
│   │   │           └── statistics/    # Statistical endpoints
│   │   ├── core/         # Core application settings
│   │   ├── db/           # Database configuration
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   └── services/     # Business logic and external services
│
├── tests/                # Comprehensive test suite
│   ├── unit/             # Unit tests for backend components
│   ├── integration/      # Integration tests for web scraping
│   └── llm/              # LLM-powered parsing tests
├── .env                  # Environment configuration (create from .env.example)
├── .env.example          # Example environment configuration
└── setup_env.py          # Environment setup helper script
│
└── docker-compose.yml    # Docker Compose configuration
```

## Data Models

### Apartment
The central entity representing a rental property with location details, amenities, and metadata.

### Plan
Each apartment can have multiple floor plans with different configurations (bedrooms, bathrooms, square footage, price).

### PlanPriceHistory
Tracks price changes for each plan over time, enabling price trend analysis.

### ApartmentImage
Stores images associated with apartments.

### Neighborhood
Contains information about neighborhoods including walkability scores and safety ratings.

## API Endpoints

### Apartments
- `GET /api/v1/apartments` - List all apartments with filtering options
- `POST /api/v1/apartments` - Create a new apartment
- `GET /api/v1/apartments/{id}` - Get a specific apartment
- `PUT /api/v1/apartments/{id}` - Update an apartment
- `DELETE /api/v1/apartments/{id}` - Delete an apartment
- `POST /api/v1/apartments/import/google-maps` - Import apartments from Google Maps

### Plans
- `GET /api/v1/apartments/{id}/plans` - List all plans for an apartment
- `POST /api/v1/apartments/{id}/plans` - Create a new plan for an apartment
- `GET /api/v1/apartments/{id}/plans/{plan_id}` - Get a specific plan
- `PUT /api/v1/apartments/{id}/plans/{plan_id}` - Update a plan
- `DELETE /api/v1/apartments/{id}/plans/{plan_id}` - Delete a plan
- `GET /api/v1/apartments/{id}/plans/{plan_id}/price-history` - Get price history for a plan

### Images
- `GET /api/v1/apartments/{id}/images` - Get all images for an apartment
- `POST /api/v1/apartments/{id}/images` - Add an image to an apartment
- `PUT /api/v1/apartments/{id}/images/{image_id}` - Update an image
- `DELETE /api/v1/apartments/{id}/images/{image_id}` - Delete an image

### Neighborhoods
- `GET /api/v1/neighborhoods` - List all neighborhoods
- `POST /api/v1/neighborhoods` - Create a new neighborhood
- `GET /api/v1/neighborhoods/{id}` - Get a specific neighborhood
- `PUT /api/v1/neighborhoods/{id}` - Update a neighborhood
- `DELETE /api/v1/neighborhoods/{id}` - Delete a neighborhood

### Statistics
- `GET /api/v1/stats/price-trends` - Get price trends over time
- `GET /api/v1/stats/apartments-by-city` - Get apartment count by city
- `GET /api/v1/stats/apartments-by-property-type` - Get apartment count by property type
- `GET /api/v1/stats/average-price-by-bedrooms` - Get average price by number of bedrooms
- `GET /api/v1/stats/plans-by-bedrooms` - Get plan count by number of bedrooms
- `GET /api/v1/stats/average-area-by-bedrooms` - Get average area by number of bedrooms

### Search
- `GET /api/v1/search` - Search for apartments by various criteria

## Getting Started

### Prerequisites
- Docker and Docker Compose
- Git
- Google Maps API key (for importing apartment data)

### Environment Configuration

AptTrack uses a single top-level `.env` file for all configuration. This includes:
- Database connection settings
- Backend and frontend ports
- API endpoints
- External service API keys
- CORS configuration
- Logging levels

**Quick Setup:**
```bash
# Use the automated setup script (recommended)
python3 setup_env.py

# Or manually copy and edit
cp .env.example .env
# Edit .env with your actual values
```

**Required Environment Variables:**
- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `JWT_SECRET_KEY`: Secret for JWT signing (refused at startup if left as default)
- `MINIMAX_API_KEY`: MiniMax-M2.5 API key (for agentic scraper)
- `GOOGLE_MAPS_API_KEY`: Google Maps Places API key (New)
- `SENDGRID_API_KEY` + `SENDGRID_FROM_EMAIL`: For email alerts
- `APP_BASE_URL`: Public URL of the frontend (used in alert email links)
- `CORS_ORIGINS`: Comma-separated list of allowed frontend origins (must match exactly)
- `TELEGRAM_BOT_TOKEN` *(optional)*: For Telegram alerts

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/AptTrack.git
   cd AptTrack
   ```

2. Set up environment variables:
   ```bash
   # Option 1: Use the setup script (recommended)
   python setup_env.py
   
   # Option 2: Manual setup
   cp .env.example .env
   
   # Edit the .env file with your actual values
   # At minimum, set your Google Maps API key:
   # GOOGLE_MAPS_API_KEY=your_api_key_here
   ```

3. Start the application using Docker Compose:
   ```bash
   docker compose up -d
   ```

4. Access the application:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

### Development

To run the application in development mode:

```bash
# Start just the database
docker compose up -d db

# Run the backend with hot reloading
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# Run the frontend with hot reloading
cd app
npm install
npm start
```

## Data Import

AptTrack provides multiple ways to import apartment data:

### Google Maps Import

You can import apartment data from Google Maps by providing a location (city or zipcode):

```bash
# Using the API
curl -X POST "http://localhost:8000/api/v1/apartments/import/google-maps" \
  -H "Content-Type: application/json" \
  -d '{"location": "Santa Clara, CA", "api_key": "your_api_key_here"}'
```

Or use the Swagger UI at http://localhost:8000/docs to trigger the import.

### Agentic Scraper

The scraper extracts floor plan names, bed/bath counts, sqft, and prices from apartment websites. It uses a three-stage pipeline designed to minimise LLM cost — most daily scrapes cost $0.00.

#### Cost tiers (fastest / cheapest first)

| Stage | Trigger | LLM tokens | Approx cost |
|-------|---------|-----------|-------------|
| **Content-hash short-circuit** | Page HTML unchanged since last scrape | 0 | $0.00 |
| **Platform adapter** | Known REIT/CMS detected in static HTML | 0 | $0.00 |
| **Path-cache replay** | Navigation path cached from prior agent run | 0 | $0.00 |
| **Full ReAct agent loop** | Cache miss on unknown site | ~100k tok | ~$0.04 |

#### Platform adapters

Static-HTML adapters fire before the browser or LLM are involved. Each adapter detects its platform by a unique HTML fingerprint and extracts floor plan data directly:

| Adapter | Detects | Properties covered |
|---------|---------|-------------------|
| `avalonbay.py` | `Fusion.globalContent` JSON blob | AvalonBay, eaves communities |
| `essex.py` (via Windsor adapter) | Essex domain + `/floor-plans` path | Essex Apartment Homes, Windsor Ridge |
| `greystar.py` | `LodgingBusiness` JSON-LD with `containsPlace` | Greystar-managed properties |
| `rentcafe.py` | `cdngeneralmvc.rentcafe.com` script tag | RentCafe / Yardi sites |
| `leasingstar.py` | LeaseStar property ID in HTML | LeaseStar-managed properties |
| `sightmap.py` | Engrain SightMap iframe embed | SightMap interactive floor maps |
| `fatwin.py` | FatWin widget script | FatWin-powered sites |
| `jonah_digital.py` | Jonah Digital JSON feed | Jonah Digital CMS |
| `windsor.py` | `windsorcommunities.com` domain | Windsor Communities |
| `generic_detail.py` | Schema.org `FloorPlan` structured data | Any site with schema.org markup |

#### Full ReAct agent loop

When no adapter matches and no path cache exists, the agent uses **MiniMax-M2.5** (OpenAI-compatible API, $0.30/M input / $1.10/M output) with a real Playwright browser:

1. Agent receives a structured BeautifulSoup page state (never screenshots).
2. LLM decides which browser tool to call: `navigate_to`, `click_link`, `click_button`, `scroll_down`, `read_iframe`, `extract_all_units`, or `submit_findings`.
3. `BrowserSession` executes the tool and returns an observation.
4. Loop continues until `submit_findings` is called or a 22-iteration no-data early stop.
5. On success, the navigation path is saved to `path_cache/` — future scrapes of the same URL replay the steps at $0 cost.
6. `_sanitize()` strips prices leaked from the site's price-range filter slider.

#### Seeding new apartments

```bash
# Seed from a JSON list of {name, url, city, state, zip} objects
python seed_apartments.py --urls-file dev/my_apartments.json

# Dry-run to preview scraped data without writing to DB
python seed_apartments.py --urls-file dev/my_apartments.json --dry-run
```

The seed script runs up to 2 apartments concurrently. Each URL gets a stable `external_id` derived from `SHA256(hostname + path)` so re-seeding the same URL is idempotent and REIT properties on the same domain (e.g. multiple Avalon communities) each get their own DB record.

#### Daily scraping (Celery)

The Celery worker scrapes all active apartments daily at **02:00 PT** via `task_refresh_apartment_data`. Price-drop alerts are checked at **08:00 PT** via `task_check_price_drops`.

```bash
# Local full stack (includes Celery worker + beat)
./start.sh
```

#### Scraper files

```
backend/app/services/scraper_agent/    # Production scraper (used by Celery worker)
├── agent.py           # ApartmentAgent, ReAct loop, path-cache logic
├── browser_tools.py   # BrowserSession (Playwright), extract_all_units (SightMap)
├── models.py          # ApartmentData, FloorPlan Pydantic models
├── path_cache.py      # Save/load browser navigation sequences
├── content_hash.py    # SHA256 of stripped HTML for short-circuit
├── compliance.py      # robots.txt check, C&D protocol, blocked domains
└── platforms/         # Static-HTML adapters (see table above)

tests/integration/agentic_scraper/     # Mirror used for integration tests
```

> **Note**: the two directories above are kept in sync manually. Consolidation is tracked as tech debt.

**Run scraper tests:**

```bash
# Unit tests — no API key or browser required
pytest tests/integration/agentic_scraper/ -m "not integration" -v

# Live integration tests — requires MINIMAX_API_KEY + Playwright
pytest tests/integration/agentic_scraper/ -m integration -v -s
```

#### Compliance

- Only publicly accessible pages — never behind login walls.
- `robots.txt` is checked for every new domain via `ScrapeSiteRegistry`.
- 5-second minimum delay between requests to the same domain.
- Only factual data collected: prices, sqft, bed/bath counts, availability, public amenity flags.
- Never: Craigslist/UGC aggregators, original images, listing descriptions, or PII.

### Legacy Scraper

The older pipeline (`tests/integration/modular_scraper/`) crawls raw HTML then asks an LLM to generate extraction code. It is kept for reference but is fragile on JS-heavy or iframe-based sites.

## Testing

AptTrack includes a comprehensive test suite organized into three main categories:

### Test Structure
- **Unit Tests** (`tests/unit/`): Test individual components and functions
- **Integration Tests** (`tests/integration/`): Test web scraping and data processing workflows
- **LLM Tests** (`tests/llm/`): Test AI-powered parsing and code generation

### Running Tests

1. **Setup test environment:**
   ```bash
   python tests/setup_tests.py
   ```

2. **Run all tests:**
   ```bash
   python tests/run_tests.py
   ```

3. **Run specific test categories:**
   ```bash
   # Unit tests only (no credentials needed)
   pytest tests/unit/ -v

   # Agentic scraper unit tests
   pytest tests/integration/agentic_scraper/ -m "not integration" -v

   # LLM tests only
   pytest tests/llm/ -v
   ```

4. **Run individual test files:**
   ```bash
   pytest tests/unit/test_google_maps.py -v
   ```

5. **Run standalone scripts:**
   ```bash
   # Run Google Maps service directly
   python3 tests/unit/run_google_maps.py

   # Check database schema
   python3 tests/integration/check_db_schema.py

   # Run database migration
   python3 tests/integration/run_migration.py
   ```

For detailed testing information, see [tests/README.md](tests/README.md).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 