#!/usr/bin/env bash
set -e

TARGET="${1:-all}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=========================================================="
echo "AI Learning Platform - Development Environment Bootstrapper"
echo "Target mode: [${TARGET}] (options: all | api | web)"
echo "=========================================================="

# Cleanup handler for graceful shutdown
cleanup() {
  echo ""
  echo "Shutting down development servers..."
  jobs -p | xargs -r kill 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# -----------------------------------------------------------------------------
# 1. Prerequisites Check
# -----------------------------------------------------------------------------
echo "[1/4] Checking prerequisites..."

command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed."; exit 1; }

if [ "$TARGET" = "all" ] || [ "$TARGET" = "api" ]; then
  command -v uv >/dev/null 2>&1 || { echo "'uv' package manager is required for backend. Install via: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "web" ]; then
  command -v node >/dev/null 2>&1 || { echo "Node.js is required for frontend."; exit 1; }
  command -v pnpm >/dev/null 2>&1 || { echo "'pnpm' is required for frontend. Install via: npm install -g pnpm"; exit 1; }
fi

# Check environment variable templates
if [ ! -f "$ROOT_DIR/.env" ]; then
  if [ -f "$ROOT_DIR/.env.example" ]; then
    echo "Root .env not found. Auto-generating from .env.example..."
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
  fi
fi

if [ ! -f "$ROOT_DIR/apps/web/.env.local" ]; then
  if [ -f "$ROOT_DIR/apps/web/.env.example" ]; then
    echo "apps/web/.env.local not found. Auto-generating from .env.example..."
    cp "$ROOT_DIR/apps/web/.env.example" "$ROOT_DIR/apps/web/.env.local"
  fi
fi

# -----------------------------------------------------------------------------
# 2. Infrastructure Services (Docker)
# -----------------------------------------------------------------------------
echo "[2/4] Starting infrastructure containers (PostgreSQL, Qdrant, Redis)..."
docker compose -f "$ROOT_DIR/docker/docker-compose.yml" up -d

echo "Verifying service readiness..."
docker exec ai_lms_postgres pg_isready -U postgres -d ai_lms_db >/dev/null 2>&1 && echo "PostgreSQL: ready"
docker exec ai_lms_redis redis-cli ping >/dev/null 2>&1 && echo "Redis: ready"
curl -s -f http://localhost:6333/healthz >/dev/null && echo "Qdrant: ready"

# -----------------------------------------------------------------------------
# 3. Environment Preparation
# -----------------------------------------------------------------------------
echo "[3/4] Preparing application environments..."

if [ "$TARGET" = "all" ] || [ "$TARGET" = "api" ]; then
  echo "Checking backend virtualenv & dependencies..."
  (cd "$ROOT_DIR/apps/api" && uv run python -c "from app.core.config import settings; print('FastAPI Config:', settings.APP_ENV)")
fi

if [ "$TARGET" = "all" ] || [ "$TARGET" = "web" ]; then
  echo "Checking frontend dependencies..."
  if [ ! -d "$ROOT_DIR/apps/web/node_modules" ]; then
    echo "node_modules missing in apps/web. Installing with pnpm..."
    (cd "$ROOT_DIR/apps/web" && pnpm install)
  else
    echo "Frontend node_modules present"
  fi
fi

# -----------------------------------------------------------------------------
# 4. Service Launch
# -----------------------------------------------------------------------------
echo "[4/4] Starting development servers..."

start_api() {
  echo "Launching FastAPI on http://localhost:8000 (Docs: http://localhost:8000/docs)..."
  (cd "$ROOT_DIR/apps/api" && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload)
}

start_web() {
  echo "Launching Next.js on http://localhost:3000..."
  (cd "$ROOT_DIR/apps/web" && pnpm dev)
}

if [ "$TARGET" = "api" ]; then
  start_api
elif [ "$TARGET" = "web" ]; then
  start_web
elif [ "$TARGET" = "all" ]; then
  start_api &
  API_PID=$!
  start_web &
  WEB_PID=$!

  echo "----------------------------------------------------------"
  echo "All services running! Press Ctrl+C to stop both servers."
  echo "- Backend API: http://localhost:8000/docs"
  echo "- Frontend Web: http://localhost:3000"
  echo "----------------------------------------------------------"

  # Wait for both background processes
  wait $API_PID $WEB_PID
else
  echo "Unknown target: $TARGET. Supported targets: all | api | web"
  exit 1
fi
