import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.modules.documents import documents_router, ingestion_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: recover any interrupted document ingestion tasks
    try:
        recovered = await ingestion_service.recover_interrupted_documents()
        if recovered:
            logger.info(
                "Successfully triggered recovery for %d interrupted document(s): %s",
                len(recovered),
                recovered,
            )
    except Exception:
        logger.exception("Failed to recover interrupted documents on startup")
    yield
    # Shutdown


app = FastAPI(
    title="AI Learning Platform API",
    version="0.1.0",
    description="Backend Modular Monolith for AI Learning Platform",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(documents_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "ok",
        "env": settings.APP_ENV,
        "database_configured": bool(settings.DATABASE_URL),
        "qdrant_url": settings.QDRANT_URL,
        "redis_url": settings.REDIS_URL,
    }


@app.get("/", tags=["Root"])
async def root():
    return {"message": "Welcome to AI Learning Platform API"}
