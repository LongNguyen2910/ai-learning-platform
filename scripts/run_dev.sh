#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "AI Learning Platform - Environment Verification & Dev Start"
echo "=========================================================="

# 1. Check Docker daemon & containers
echo "[1/4] Checking Docker containers..."
docker compose -f docker/docker-compose.yml up -d

# 2. Check health of services
echo "[2/4] Verifying services health..."
docker compose -f docker/docker-compose.yml ps

echo "Testing Postgres..."
docker exec ai_lms_postgres pg_isready -U postgres -d ai_lms_db

echo "Testing Redis..."
docker exec ai_lms_redis redis-cli ping

echo "Testing Qdrant..."
curl -s -f http://localhost:6333/healthz > /dev/null && echo "Qdrant is healthy!"

# 3. Backend Environment
echo "[3/4] Verifying Python backend virtualenv..."
cd apps/api
uv run python -c "from app.core.config import settings; print('Config loaded successfully for env:', settings.APP_ENV)"

# 4. Start Dev Server
echo "[4/4] Starting FastAPI development server on port 8000..."
echo "API Docs will be available at: http://localhost:8000/docs"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
