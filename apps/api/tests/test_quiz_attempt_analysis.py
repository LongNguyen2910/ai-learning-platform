import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.quizzes.models import (
    Quiz,
    QuizAttempt,
    QuizAttemptAnswer,
    QuizQuestion,
)


@pytest.fixture
def current_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="test_student@example.com",
        hashed_password="hashed_pwd",
        full_name="Analysis Student",
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


def test_post_attempt_returns_analysis(
    auth_client: TestClient, current_user: User, mock_db: AsyncMock
):
    quiz_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    q1_id = uuid.uuid4()
    q2_id = uuid.uuid4()

    q1 = QuizQuestion(
        id=q1_id,
        quiz_id=quiz_id,
        question_text="Q1: Định nghĩa Bayes",
        bloom_level="remember",
        options=[{"key": "A", "text": "Đúng"}, {"key": "B", "text": "Sai"}],
        correct_option="A",
        topic_tag="Xác suất Bayes",
        target_page=12,
        source_document_id=doc_id,
        source_document_title="Giáo trình Xác suất",
    )
    q2 = QuizQuestion(
        id=q2_id,
        quiz_id=quiz_id,
        question_text="Q2: Vận dụng Bayes",
        bloom_level="apply",
        options=[{"key": "A", "text": "Đúng"}, {"key": "B", "text": "Sai"}],
        correct_option="B",
        topic_tag="Xác suất Bayes",
        target_page=14,
        source_document_id=doc_id,
        source_document_title="Giáo trình Xác suất",
    )

    quiz = Quiz(
        id=quiz_id,
        user_id=current_user.id,
        document_id=doc_id,
        title="Quiz Xác suất",
        total_questions=2,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    quiz.questions = [q1, q2]

    mock_quiz_res = MagicMock()
    mock_quiz_res.scalar_one_or_none.return_value = quiz
    mock_db.execute.return_value = mock_quiz_res

    payload = {
        "answers": [
            {"question_id": str(q1_id), "selected_option": "STRING"},  # Previously failed with VARCHAR(5) truncation
            {"question_id": str(q2_id), "selected_option": "B"},  # CORRECT
        ]
    }

    resp = auth_client.post(f"/api/v1/quizzes/{quiz_id}/attempts", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["quiz_id"] == str(quiz_id)
    assert data["score"] == 50.0
    assert data["total_correct"] == 1
    assert data["total_incorrect"] == 1

    # Analysis check
    assert "analysis" in data
    analysis = data["analysis"]
    assert len(analysis["weak_topics"]) == 1
    weak = analysis["weak_topics"][0]
    assert weak["topic_tag"] == "Xác suất Bayes"
    assert weak["severity"] == "critical_foundation"
    assert weak["incorrect_question_ids"] == [str(q1_id)]

    # Page review recommendations
    assert len(analysis["review_recommendations"]) == 1
    rec = analysis["review_recommendations"][0]
    assert rec["pages"] == [12]
    assert "Xác suất Bayes" in rec["topics"]


def test_get_attempt_analysis_success(
    auth_client: TestClient, current_user: User, mock_db: AsyncMock
):
    attempt_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    q1_id = uuid.uuid4()

    q1 = QuizQuestion(
        id=q1_id,
        quiz_id=quiz_id,
        question_text="Q1",
        bloom_level="apply",
        options=[{"key": "A", "text": "A"}],
        correct_option="A",
        topic_tag="Machine Learning",
        target_page=45,
        source_document_id=doc_id,
        source_document_title="ML Basics",
    )

    attempt = QuizAttempt(
        id=attempt_id,
        quiz_id=quiz_id,
        user_id=current_user.id,
        score=0.0,
        total_correct=0,
        total_incorrect=1,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    ans = QuizAttemptAnswer(
        id=uuid.uuid4(),
        attempt_id=attempt_id,
        question_id=q1_id,
        selected_option="B",
        is_correct=False,
    )
    ans.question = q1
    attempt.answers = [ans]
    attempt.quiz = Quiz(
        id=quiz_id,
        user_id=current_user.id,
        document_id=doc_id,
        title="ML Quiz",
        total_questions=1,
    )

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = attempt
    mock_db.execute.return_value = mock_res

    resp = auth_client.get(f"/api/v1/quizzes/attempts/{attempt_id}/analysis")
    assert resp.status_code == 200
    data = resp.json()
    assert data["attempt_id"] == str(attempt_id)
    assert data["score"] == 0.0

    analysis = data["analysis"]
    assert len(analysis["weak_topics"]) == 1
    assert analysis["weak_topics"][0]["severity"] == "application_practice"
    assert analysis["review_recommendations"][0]["pages"] == [45]


def test_get_attempt_analysis_not_found(auth_client: TestClient, mock_db: AsyncMock):
    attempt_id = uuid.uuid4()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res

    resp = auth_client.get(f"/api/v1/quizzes/attempts/{attempt_id}/analysis")
    assert resp.status_code == 404
    assert f"Quiz attempt with id {attempt_id} not found" in resp.json()["detail"]


def test_quiz_scoring_perfect_100_percent(
    auth_client: TestClient, current_user: User, mock_db: AsyncMock
):
    """Quiz Scoring: All questions answered correctly yield 100.0% score."""
    quiz_id = uuid.uuid4()
    q1_id = uuid.uuid4()
    q2_id = uuid.uuid4()

    q1 = QuizQuestion(
        id=q1_id,
        quiz_id=quiz_id,
        question_text="Q1",
        bloom_level="remember",
        options=[{"key": "A", "text": "A"}],
        correct_option="A",
        topic_tag="Topic 1",
        target_page=1,
    )
    q2 = QuizQuestion(
        id=q2_id,
        quiz_id=quiz_id,
        question_text="Q2",
        bloom_level="understand",
        options=[{"key": "B", "text": "B"}],
        correct_option="B",
        topic_tag="Topic 2",
        target_page=2,
    )

    quiz = Quiz(
        id=quiz_id,
        user_id=current_user.id,
        title="Perfect Quiz",
        total_questions=2,
        time_limit_minutes=10,
        created_at=datetime.now(UTC),
    )
    quiz.questions = [q1, q2]

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = quiz
    mock_db.execute.return_value = mock_res

    payload = {
        "answers": [
            {"question_id": str(q1_id), "selected_option": "A"},
            {"question_id": str(q2_id), "selected_option": "B"},
        ]
    }
    resp = auth_client.post(f"/api/v1/quizzes/{quiz_id}/attempts", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["score"] == 100.0
    assert data["total_correct"] == 2
    assert data["total_incorrect"] == 0


def test_quiz_scoring_rounding_percentages_and_unanswered(
    auth_client: TestClient, current_user: User, mock_db: AsyncMock
):
    """Quiz Scoring: 1 out of 3 correct yields 33.33% with unanswered questions handled."""
    quiz_id = uuid.uuid4()
    q1_id = uuid.uuid4()
    q2_id = uuid.uuid4()
    q3_id = uuid.uuid4()

    q1 = QuizQuestion(
        id=q1_id,
        quiz_id=quiz_id,
        question_text="Q1",
        bloom_level="remember",
        options=[{"key": "A", "text": "A"}],
        correct_option="A",
        topic_tag="Topic 1",
        target_page=1,
    )
    q2 = QuizQuestion(
        id=q2_id,
        quiz_id=quiz_id,
        question_text="Q2",
        bloom_level="remember",
        options=[{"key": "B", "text": "B"}],
        correct_option="B",
        topic_tag="Topic 2",
        target_page=2,
    )
    q3 = QuizQuestion(
        id=q3_id,
        quiz_id=quiz_id,
        question_text="Q3",
        bloom_level="remember",
        options=[{"key": "C", "text": "C"}],
        correct_option="C",
        topic_tag="Topic 3",
        target_page=3,
    )

    quiz = Quiz(
        id=quiz_id,
        user_id=current_user.id,
        title="Rounding Quiz",
        total_questions=3,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    quiz.questions = [q1, q2, q3]

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = quiz
    mock_db.execute.return_value = mock_res

    # Answer only Q1 correctly, Q2 wrong, Q3 left unanswered
    payload = {
        "answers": [
            {"question_id": str(q1_id), "selected_option": "A"},
            {"question_id": str(q2_id), "selected_option": "D"},
            # Q3 omitted
        ]
    }
    resp = auth_client.post(f"/api/v1/quizzes/{quiz_id}/attempts", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["score"] == 33.33
    assert data["total_correct"] == 1
    assert data["total_incorrect"] == 2
