from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Finds the workspace root directory (containing 'storage' and 'apps')."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "storage").is_dir() and (parent / "apps").is_dir():
            return parent
    return current.parents[4] if len(current.parents) > 4 else current.parent


PROJECT_ROOT = _find_project_root()


class Settings(BaseSettings):
    # Base paths
    PROJECT_ROOT: Path = PROJECT_ROOT

    # App
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-secret-key-change-in-production-min-32-chars"

    # Postgres
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "ai_lms_db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_lms_db"
    )

    # Qdrant
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_COLLECTION_NAME: str = "learning_chunks"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Gemini
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 3072

    # Storage (Anchored to the root storage directory outside apps/api)
    UPLOAD_DIR: str = str(PROJECT_ROOT / "storage" / "uploads")
    PARSED_DIR: str = str(PROJECT_ROOT / "storage" / "parsed")
    MAX_FILE_SIZE_MB: int = 50
    INGESTION_CONCURRENCY: int = 3
    AUTO_RESUME_INGESTION_ON_STARTUP: bool = True

    @field_validator("UPLOAD_DIR", "PARSED_DIR", mode="after")
    @classmethod
    def resolve_storage_path(cls, v: str) -> str:
        path = Path(v)
        if not path.is_absolute():
            return str((PROJECT_ROOT / path).resolve())
        return str(path.resolve())

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
