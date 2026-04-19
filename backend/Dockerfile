# Web service only (FastAPI + Alembic). Does NOT install Playwright or Chromium.
# Celery worker and beat use Dockerfile.worker (mcr.microsoft.com/playwright/python base).
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run the application with environment variables
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

EXPOSE 8000