from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.core.models_registry
from app.core.config import settings
from app.modules.auth import auth_router
from app.modules.documents import documents_router

app = FastAPI(
    title="AI Learning Platform API",
    version="0.1.0",
    description="Backend Modular Monolith for AI Learning Platform",
    debug=settings.DEBUG,
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
app.include_router(auth_router, prefix="/api/v1")
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
