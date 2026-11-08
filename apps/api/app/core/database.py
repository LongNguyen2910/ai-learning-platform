from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
async_session_maker = AsyncSessionLocal


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def ensure_roadmap_exam_schema() -> None:
    """Idempotently ensures Roadmap Final Assessment, Remediation, and User Avatar columns exist in PostgreSQL."""
    async with engine.connect() as conn:
        check_res = await conn.execute(
            text(
                "SELECT table_name, column_name "
                "FROM information_schema.columns "
                "WHERE table_name IN ('users', 'roadmaps', 'quizzes', 'quiz_questions')"
            )
        )
        existing = {(row[0], row[1]) for row in check_res.fetchall()}

    required = {
        ("users", "avatar_url"),
        ("roadmaps", "exam_status"),
        ("roadmaps", "latest_exam_score"),
        ("roadmaps", "iteration"),
        ("roadmaps", "parent_roadmap_id"),
        ("roadmaps", "weak_topics"),
        ("quizzes", "roadmap_id"),
        ("quiz_questions", "source_document_id"),
        ("quiz_questions", "source_document_title"),
    }
    if required.issubset(existing):
        return

    ddl_statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT NULL;",
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS exam_status VARCHAR(20) NOT NULL DEFAULT 'locked';",
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS latest_exam_score DOUBLE PRECISION NULL;",
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS iteration INTEGER NOT NULL DEFAULT 1;",
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS parent_roadmap_id UUID NULL REFERENCES roadmaps(id) ON DELETE SET NULL;",
        "ALTER TABLE roadmaps ADD COLUMN IF NOT EXISTS weak_topics JSONB NOT NULL DEFAULT '[]'::jsonb;",
        "ALTER TABLE quizzes ALTER COLUMN document_id DROP NOT NULL;",
        "ALTER TABLE quizzes ADD COLUMN IF NOT EXISTS roadmap_id UUID NULL REFERENCES roadmaps(id) ON DELETE CASCADE;",
        "CREATE INDEX IF NOT EXISTS ix_quizzes_roadmap_id ON quizzes (roadmap_id);",
        "ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS source_document_id UUID NULL;",
        "ALTER TABLE quiz_questions ADD COLUMN IF NOT EXISTS source_document_title VARCHAR(255) NULL;",
    ]
    async with engine.begin() as conn:
        for stmt in ddl_statements:
            await conn.execute(text(stmt))
