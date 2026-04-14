# AptTrack - Apartment Rental Tracking System

AptTrack is a comprehensive apartment rental tracking system that helps users find, compare, and track apartment listings over time. The application monitors rental prices, provides detailed apartment information, and offers analytics on rental market trends.

## Features

- **Apartment Listings**: Browse and search for apartments with detailed information
- **Multiple Floor Plans**: Each apartment can have multiple floor plans with different configurations
- **Price History Tracking**: Monitor how rental prices change over time
- **Advanced Search**: Filter apartments by location, price range, bedrooms, and more
- **Neighborhood Information**: Get details about neighborhoods including walkability scores
- **Statistics & Analytics**: View market trends and price comparisons
- **Image Management**: Store and manage apartment images
- **Google Maps Integration**: Import apartment data from Google Maps based on location

## Tech Stack

### Backend
- **Framework**: FastAPI (Python)
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy
- **Migrations**: Alembic
- **Data Scraping**: BeautifulSoup, aiohttp
- **External APIs**: Google Maps Places API

### Frontend
- **Framework**: React
- **Styling**: Tailwind CSS
- **State Management**: React Hooks
- **Routing**: React Router

### Infrastructure
- **Containerization**: Docker & Docker Compose
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
- `GOOGLE_MAPS_API_KEY`: Your Google Maps API key
- `DATABASE_URL`: Database connection string
- `BACKEND_PORT`: Backend service port (default: 8000)
- `FRONTEND_PORT`: Frontend service port (default: 3000)

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

### Agentic Scraper (Recommended)

The agentic scraper uses **MiniMax-M2.5** (via the OpenAI-compatible API) and a real Playwright browser to extract floor plan and pricing data from any apartment website — including sites with dynamic UIs, iframes, and tab-based layouts that break traditional HTML-parsing approaches.

The agent navigates the site autonomously, clicks through floor plan tabs, scrolls to load lazy content, and submits structured JSON once it has collected pricing data.

**Setup:**

```bash
pip install -r tests/requirements-test.txt
playwright install chromium
```

Add `MINIMAX_API_KEY=your_key` to your `.env` file.

**Scrape a single apartment:**

```python
import asyncio
from tests.integration.agentic_scraper.agent import ApartmentAgent

async def main():
    agent = ApartmentAgent()   # reads MINIMAX_API_KEY from .env
    result = await agent.scrape("https://www.rentmiro.com/floorplans")
    for plan in result.floor_plans:
        print(plan.name, plan.min_price, plan.size_sqft)

asyncio.run(main())
```

**Batch-scrape 10 Bay Area apartments:**

```bash
python tests/integration/agentic_scraper/batch_runner.py
```

Results are printed as a table and saved to `tests/integration/agentic_scraper/batch_results.json`.

**How it works:**

1. The agent calls `navigate_to`, `click_link`, `click_button`, and `scroll_down` tools in a loop driven by the LLM.
2. When it has collected enough data it calls `submit_findings`, which terminates the loop and returns an `ApartmentData` Pydantic model.
3. A post-scrape validator (`_sanitize`) detects and removes prices that were mistakenly copied from a site's price-range filter slider rather than from individual plan cards.
4. The LLM call layer retries automatically on 429 / 5xx / overload errors with exponential back-off.

**Agentic scraper files:**

```
tests/integration/agentic_scraper/
├── models.py          # ApartmentData, FloorPlan Pydantic models
├── browser_tools.py   # BrowserSession wrapping Playwright async API
├── agent.py           # ApartmentAgent + tool definitions + sanitizer
├── batch_runner.py    # Scrape 10 apartments concurrently and print a table
└── test_agentic_scraper.py  # 13 unit tests + 3 live integration tests
```

**Run tests:**

```bash
# Unit tests — no API key or internet required
pytest tests/integration/agentic_scraper/ -m "not integration" -v

# Live integration tests — requires MINIMAX_API_KEY
pytest tests/integration/agentic_scraper/ -m integration -v -s
```

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