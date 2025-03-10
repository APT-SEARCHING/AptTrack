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
│   └── tests/            # Unit and integration tests
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

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/AptTrack.git
   cd AptTrack
   ```

2. Set up environment variables:
   ```bash
   # Create a .env file in the backend directory
   echo "GOOGLE_MAPS_API_KEY=your_api_key_here" > backend/.env
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

### Web Scraping

AptTrack includes a scraper service that can collect apartment data from various sources. Currently, it supports:

- Irvine Company Apartments

To run the scraper manually:

```bash
docker compose exec backend python -m app.services.scraper
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details. 