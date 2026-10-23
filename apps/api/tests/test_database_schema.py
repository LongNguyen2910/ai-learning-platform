import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


@pytest_asyncio.fixture
async def db_session():
    test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async_session = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_all_15_tables_exist(db_session):
    expected_tables = {
        "users",
        "subjects",
        "documents",
        "roadmaps",
        "roadmap_nodes",
        "study_sessions",
        "chat_sessions",
        "chat_messages",
        "flashcard_decks",
        "flashcards",
        "quizzes",
        "quiz_questions",
        "quiz_attempts",
        "quiz_attempt_answers",
        "token_usage_logs",
    }

    result = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
        )
    )
    existing_tables = {row[0] for row in result.fetchall()}

    missing_tables = expected_tables - existing_tables
    assert not missing_tables, f"Missing tables in PostgreSQL: {missing_tables}"


@pytest.mark.asyncio
async def test_indexes_exist(db_session):
    expected_indexes = {
        "idx_documents_user_id",
        "idx_documents_subject_id",
        "idx_roadmap_nodes_roadmap_id",
        "idx_study_sessions_user_date",
        "idx_chat_messages_session_id",
        "idx_flashcards_user_due",
        "idx_quiz_questions_quiz_id",
        "idx_token_usage_created_at",
    }

    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'public';"
        )
    )
    existing_indexes = {row[0] for row in result.fetchall()}

    missing_indexes = expected_indexes - existing_indexes
    assert not missing_indexes, f"Missing indexes in PostgreSQL: {missing_indexes}"


@pytest.mark.asyncio
async def test_session_lifecycle(db_session):
    result = await db_session.execute(text("SELECT 1;"))
    assert result.scalar() == 1
