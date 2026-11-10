import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.core.models_registry
from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.flashcards.models import FlashcardDeck
from app.modules.flashcards.schemas import (
    ExtractedFlashcardItem,
    ExtractionSourceType,
    FlashcardExtractRequest,
    GeneratedFlashcardsPayload,
)
from app.modules.flashcards.service import FlashcardService
from app.modules.quizzes.models import QuizAttempt, QuizAttemptAnswer, QuizQuestion


@pytest.fixture
def mock_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student@example.com",
        hashed_password="hashed_password",
        full_name="Nguyễn Văn Học",
        role="user",
        is_active=True,
    )


@pytest.fixture
def other_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="hashed_password",
        full_name="Học Viên Khác",
        role="user",
        is_active=True,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add_all = MagicMock()
    return db


# -----------------------------------------------------------------------------
# Unit & Service Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quiz_extraction_no_wrong_answers_fast_path(
    mock_db: AsyncMock, mock_user: User
):
    """Khi bài quiz đúng 100%, trả về rỗng ngay lập tức mà không gọi Gemini API."""
    attempt_id = uuid.uuid4()
    mock_attempt = QuizAttempt(
        id=attempt_id,
        quiz_id=uuid.uuid4(),
        user_id=mock_user.id,
        score=10.0,
        total_correct=5,
        total_incorrect=0,
        completed_at=datetime.now(UTC),
    )
    mock_attempt.answers = [
        QuizAttemptAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt_id,
            question_id=uuid.uuid4(),
            selected_option="A",
            is_correct=True,
        )
    ]

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_attempt
    mock_db.execute.return_value = mock_result

    mock_gemini_client = MagicMock()
    service = FlashcardService(client=mock_gemini_client)

    request = FlashcardExtractRequest(
        source_type=ExtractionSourceType.QUIZ_ATTEMPT,
        source_id=attempt_id,
    )
    response = await service.extract_flashcards(
        db=mock_db, user_id=mock_user.id, request=request
    )

    assert response.total_extracted == 0
    assert response.cards == []
    assert "Chúc mừng" in (response.message or "")
    # Đảm bảo tuyệt đối không gọi Gemini
    mock_gemini_client.models.generate_content.assert_not_called()


@pytest.mark.asyncio
async def test_quiz_extraction_with_wrong_answers_calls_gemini(
    mock_db: AsyncMock, mock_user: User
):
    """Khi có câu sai, gọi Gemini Structured Output và trả về danh sách thẻ chuẩn."""
    attempt_id = uuid.uuid4()
    q_id = uuid.uuid4()

    mock_question = QuizQuestion(
        id=q_id,
        quiz_id=uuid.uuid4(),
        question_text="Định luật II Newton được phát biểu như thế nào?",
        bloom_level="remember",
        options=[
            {"key": "A", "text": "F = m * a"},
            {"key": "B", "text": "F = m * v"},
            {"key": "C", "text": "F = m / a"},
            {"key": "D", "text": "F = 0"},
        ],
        correct_option="A",
        explanation="Định luật II Newton nêu F = ma.",
        target_page=5,
    )

    mock_attempt = QuizAttempt(
        id=attempt_id,
        quiz_id=uuid.uuid4(),
        user_id=mock_user.id,
        score=0.0,
        total_correct=0,
        total_incorrect=1,
        completed_at=datetime.now(UTC),
    )
    mock_attempt.answers = [
        QuizAttemptAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt_id,
            question_id=q_id,
            selected_option="B",  # Học viên chọn sai
            is_correct=False,
        )
    ]
    mock_attempt.answers[0].question = mock_question

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_attempt
    mock_db.execute.return_value = mock_result

    # Mock response từ Gemini
    expected_payload = GeneratedFlashcardsPayload(
        cards=[
            ExtractedFlashcardItem(
                front_text="Định luật II Newton",
                back_text=r"$\vec{F} = m\vec{a}$",
                category="formula",
                context_snippet="Định luật II Newton",
                trigger_reason="Học viên nhầm lẫn giữa gia tốc và vận tốc.",
                target_page=5,
            )
        ]
    )
    mock_gen_response = MagicMock()
    mock_gen_response.parsed = expected_payload

    mock_gemini_client = MagicMock()
    mock_gemini_client.models.generate_content.return_value = mock_gen_response

    service = FlashcardService(client=mock_gemini_client)
    request = FlashcardExtractRequest(
        source_type=ExtractionSourceType.QUIZ_ATTEMPT,
        source_id=attempt_id,
    )

    response = await service.extract_flashcards(
        db=mock_db, user_id=mock_user.id, request=request
    )

    assert response.total_extracted == 1
    assert len(response.cards) == 1
    assert response.cards[0].front_text == "Định luật II Newton"
    assert response.cards[0].category == "formula"
    mock_gemini_client.models.generate_content.assert_called_once()


# -----------------------------------------------------------------------------
# API & Integration Tests
# -----------------------------------------------------------------------------


def test_api_extract_flashcards_idor_defense(mock_user: User, other_user: User):
    """Học viên A không thể trích xuất quiz của học viên B (IDOR 404)."""
    attempt_id = uuid.uuid4()
    mock_attempt = QuizAttempt(
        id=attempt_id,
        quiz_id=uuid.uuid4(),
        user_id=other_user.id,  # Thuộc về người khác
        score=5.0,
        total_correct=1,
        total_incorrect=1,
        completed_at=datetime.now(UTC),
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_attempt
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        client = TestClient(app)
        res = client.post(
            "/api/v1/flashcards/extract",
            json={
                "source_type": "quiz_attempt",
                "source_id": str(attempt_id),
            },
        )
        assert res.status_code == 404
        assert "không tồn tại hoặc bạn không có quyền truy cập" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_api_extract_flashcards_incomplete_quiz(mock_user: User):
    """Trích xuất từ quiz chưa hoàn tất (completed_at is None) trả về 400."""
    attempt_id = uuid.uuid4()
    mock_attempt = QuizAttempt(
        id=attempt_id,
        quiz_id=uuid.uuid4(),
        user_id=mock_user.id,
        score=0.0,
        total_correct=0,
        total_incorrect=0,
        completed_at=None,  # Chưa hoàn thành
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_attempt
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        client = TestClient(app)
        res = client.post(
            "/api/v1/flashcards/extract",
            json={
                "source_type": "quiz_attempt",
                "source_id": str(attempt_id),
            },
        )
        assert res.status_code == 400
        assert "Vui lòng hoàn thành bài kiểm tra" in res.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_api_bulk_create_flashcards(mock_user: User):
    """Lưu danh sách thẻ đã duyệt vào deck của học viên với các thông số SM-2 mặc định."""
    deck_id = uuid.uuid4()
    mock_deck = FlashcardDeck(
        id=deck_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Vật Lý Đại Cương",
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_deck
    mock_db.execute.return_value = mock_result
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()
    mock_db.add_all = MagicMock()

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        client = TestClient(app)
        payload = {
            "deck_id": str(deck_id),
            "cards": [
                {
                    "front_text": "Định luật I Newton",
                    "back_text": "Quán tính của vật khi không có ngoại lực tác dụng.",
                    "page_number": 3,
                },
                {
                    "front_text": "Định luật II Newton",
                    "back_text": r"$\vec{F} = m\vec{a}$",
                    "page_number": 5,
                },
            ],
        }
        res = client.post("/api/v1/flashcards/bulk", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["created_count"] == 2
        assert len(data["cards"]) == 2
        # Kiểm tra SM-2 defaults
        assert data["cards"][0]["easiness_factor"] == 2.5
        assert data["cards"][0]["repetition_number"] == 0
        assert data["cards"][0]["interval_days"] == 1
    finally:
        app.dependency_overrides.clear()
