#!/usr/bin/env bash
# start.sh — start AptTrack backend + frontend
# Usage:
#   ./start.sh          # Docker (full stack: DB, Redis, Celery, backend, frontend)
#   ./start.sh local    # Local processes (requires Postgres running separately)

set -e

MODE="${1:-docker}"

# ── helpers ──────────────────────────────────────────────────────────────────

check_env() {
    if [ ! -f .env ]; then
        echo "ERROR: .env file not found. Copy .env.example → .env and fill in your values."
        exit 1
    fi
}

# ── Docker mode (default) ─────────────────────────────────────────────────────

run_docker() {
    check_env
    echo "Starting full stack with Docker Compose..."
    docker compose up --build -d

    echo ""
    echo "Services starting — waiting for health checks..."
    sleep 5

    echo ""
    echo "  Frontend : http://localhost:$(grep FRONTEND_PORT .env | cut -d= -f2 | tr -d ' ' || echo 3000)"
    echo "  Backend  : http://localhost:$(grep BACKEND_PORT  .env | cut -d= -f2 | tr -d ' ' || echo 8000)/docs"
    echo "  Redis    : localhost:6379"
    echo ""
    echo "Logs: docker compose logs -f"
    echo "Stop: docker compose down"
}

# ── Local mode ────────────────────────────────────────────────────────────────

run_local() {
    check_env

    # Load .env and rewrite DB host from Docker service name → localhost
    set -o allexport
    source .env
    set +o allexport
    export DATABASE_URL="${DATABASE_URL//@db:/@localhost:}"

    # Install backend deps if needed
    if ! python -c "import fastapi" 2>/dev/null; then
        echo "Installing backend dependencies..."
        pip install -r backend/requirements.txt
    fi

    # Install frontend deps if needed
    if [ ! -d app/node_modules ]; then
        echo "Installing frontend dependencies..."
        (cd app && npm install)
    fi

    # Run Alembic migrations
    echo "Running database migrations..."
    (cd backend && PYTHONPATH=. python -m alembic upgrade heads)

    # Start backend in background
    echo "Starting backend on :8000..."
    (cd backend && PYTHONPATH=. python -m uvicorn app.main:app --reload --port 8000) &
    BACKEND_PID=$!

    # Start frontend in background
    echo "Starting frontend on :3000..."
    (cd app && npm start) &
    FRONTEND_PID=$!

    echo ""
    echo "  Frontend : http://localhost:3000"
    echo "  Backend  : http://localhost:8000/docs"
    echo ""
    echo "Press Ctrl+C to stop both servers."

    # Shut down both processes on exit
    trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
    wait
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "$MODE" in
    docker) run_docker ;;
    local)  run_local  ;;
    *)
        echo "Usage: $0 [docker|local]"
        echo "  docker (default) — run via Docker Compose (includes DB, Redis, Celery)"
        echo "  local            — run backend + frontend as local processes"
        exit 1
        ;;
esac
