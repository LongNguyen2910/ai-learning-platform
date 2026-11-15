import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.quizzes.models import Quiz, QuizQuestion


@pytest.fixture
def current_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student@example.com",
        hashed_password="hashed_pwd",
        full_name="Quiz Student",
        role="user",
        is_active=True,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def auth_client(current_user: User, mock_db: AsyncMock):
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client():
    with TestClient(app) as test_client:
        yield test_client


def test_create_quiz_unauthorized(unauth_client: TestClient):
    payload = {
        "document_id": str(uuid.uuid4()),
        "title": "Unauthorized Quiz",
        "total_questions": 5,
        "new_questions": [],
    }
    resp = unauth_client.post("/api/v1/quizzes", json=payload)
    assert resp.status_code == 401


def test_create_quiz_validation_error(auth_client: TestClient):
    # Empty new_questions
    payload = {
        "document_id": str(uuid.uuid4()),
        "title": "Invalid Quiz",
        "total_questions": 5,
        "new_questions": [],
    }
    resp = auth_client.post("/api/v1/quizzes", json=payload)
    assert resp.status_code == 422


def test_create_quiz_insufficient_questions(auth_client: TestClient, mock_db: AsyncMock):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []  # No historical review questions
    mock_db.execute.return_value = mock_result

    # Wants 10 questions, but only 2 new questions provided and 0 review available
    payload = {
        "document_id": str(uuid.uuid4()),
        "title": "Short Quiz",
        "total_questions": 10,
        "new_questions": [
            {
                "question_text": "Q1",
                "bloom_level": "remember_understand",
                "options": [{"key": "A", "text": "Opt A"}, {"key": "B", "text": "Opt B"}],
                "correct_option": "A",
            },
            {
                "question_text": "Q2",
                "bloom_level": "remember_understand",
                "options": [{"key": "A", "text": "Opt A"}, {"key": "B", "text": "Opt B"}],
                "correct_option": "B",
            },
        ],
    }
    resp = auth_client.post("/api/v1/quizzes", json=payload)
    assert resp.status_code == 422
    assert "Insufficient questions in pool" in resp.json()["detail"]


def test_create_quiz_first_lesson_all_new(
    auth_client: TestClient,
    current_user: User,
    mock_db: AsyncMock,
):
    doc_id = uuid.uuid4()
    quiz_id = uuid.uuid4()

    # Mock historical review questions query -> empty
    mock_review_res = MagicMock()
    mock_review_res.scalars.return_value.all.return_value = []

    # Mock reloaded quiz
    created_quiz = Quiz(
        id=quiz_id,
        user_id=current_user.id,
        document_id=doc_id,
        title="Lesson 1 Quiz",
        is_interleaved=False,
        total_questions=3,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    created_quiz.questions = [
        QuizQuestion(
            id=uuid.uuid4(),
            quiz_id=quiz_id,
            question_text=f"Q{i}",
            bloom_level="remember_understand",
            options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            correct_option="A",
        )
        for i in range(1, 4)
    ]

    mock_reload_res = MagicMock()
    mock_reload_res.scalar_one.return_value = created_quiz

    mock_db.execute.side_effect = [mock_review_res, mock_reload_res]

    payload = {
        "document_id": str(doc_id),
        "title": "Lesson 1 Quiz",
        "total_questions": 3,
        "new_questions": [
            {
                "question_text": f"Q{i}",
                "bloom_level": "remember_understand",
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                "correct_option": "A",
            }
            for i in range(1, 4)
        ],
    }

    resp = auth_client.post("/api/v1/quizzes", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == str(quiz_id)
    assert data["is_interleaved"] is False
    assert data["total_questions"] == 3
    assert len(data["questions"]) == 3
    mock_db.commit.assert_awaited_once()


def test_create_interleaved_quiz_with_review_pool(
    auth_client: TestClient,
    current_user: User,
    mock_db: AsyncMock,
):
    doc_id = uuid.uuid4()
    quiz_id = uuid.uuid4()

    # Mock historical review questions
    historical_questions = [
        QuizQuestion(
            id=uuid.uuid4(),
            quiz_id=uuid.uuid4(),
            question_text=f"Hist Q{i}",
            bloom_level="apply",
            options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            correct_option="B",
        )
        for i in range(1, 6)
    ]
    mock_review_res = MagicMock()
    mock_review_res.scalars.return_value.all.return_value = historical_questions

    # Mock reloaded interleaved quiz
    created_quiz = Quiz(
        id=quiz_id,
        user_id=current_user.id,
        document_id=doc_id,
        title="Interleaved Quiz Week 2",
        is_interleaved=True,
        total_questions=10,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    created_quiz.questions = [
        QuizQuestion(
            id=uuid.uuid4(),
            quiz_id=quiz_id,
            question_text=f"Q{i}",
            bloom_level="remember_understand",
            options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            correct_option="A",
        )
        for i in range(1, 11)
    ]

    mock_reload_res = MagicMock()
    mock_reload_res.scalar_one.return_value = created_quiz

    mock_db.execute.side_effect = [mock_review_res, mock_reload_res]

    payload = {
        "document_id": str(doc_id),
        "title": "Interleaved Quiz Week 2",
        "total_questions": 10,
        "new_questions": [
            {
                "question_text": f"New Q{i}",
                "bloom_level": "remember_understand",
                "options": [{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
                "correct_option": "A",
            }
            for i in range(1, 11)
        ],
        "seed": 42,
    }

    resp = auth_client.post("/api/v1/quizzes", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["is_interleaved"] is True
    assert data["total_questions"] == 10
    assert len(data["questions"]) == 10


def test_get_quiz_not_found(auth_client: TestClient, mock_db: AsyncMock):
    quiz_id = uuid.uuid4()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    resp = auth_client.get(f"/api/v1/quizzes/{quiz_id}")
    assert resp.status_code == 404
    assert f"Quiz with id {quiz_id} not found" in resp.json()["detail"]
