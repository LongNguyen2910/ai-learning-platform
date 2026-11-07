import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.core.models_registry
from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.documents.models import Document
from app.modules.quizzes.exceptions import (
    DocumentNotFoundError,
    DocumentNotReadyError,
    GeminiGenerationError,
    InvalidPageRangeError,
    QuizNotFoundError,
)
from app.modules.quizzes.models import Quiz, QuizQuestion
from app.modules.quizzes.prompt import compute_bloom_distribution
from app.modules.quizzes.schemas import (
    BloomLevel,
    GeneratedQuestionItem,
    GeneratedQuizPayload,
    QuizGenerateRequest,
    QuizOptionItem,
)
from app.modules.quizzes.service import QuizService, quiz_service


@pytest.fixture
def mock_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student@example.com",
        hashed_password="hashed_pwd",
        full_name="Sinh Viên A",
        role="user",
        is_active=True,
    )


@pytest.fixture
def other_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="hashed_pwd",
        full_name="Người Dùng Khác",
        role="user",
        is_active=True,
    )


@pytest.fixture
def sample_payload() -> GeneratedQuizPayload:
    return GeneratedQuizPayload(
        title="Trắc nghiệm Tổng quan AI",
        questions=[
            GeneratedQuestionItem(
                question_text="Mạng nơ-ron tích chập (CNN) thường được sử dụng cho bài toán nào?",
                bloom_level=BloomLevel.REMEMBER,
                options=[
                    QuizOptionItem(key="A", text="Xử lý hình ảnh"),
                    QuizOptionItem(key="B", text="Dự báo thời tiết bảng số"),
                    QuizOptionItem(key="C", text="Phân tích âm thanh đơn"),
                    QuizOptionItem(key="D", text="Quản lý bộ nhớ RAM"),
                ],
                correct_option="A",
                explanation="CNN được thiết kế chuyên biệt cho xử lý dữ liệu dạng lưới 2D/3D như hình ảnh.",
                target_page=1,
                topic_tag="CNN",
            ),
            GeneratedQuestionItem(
                question_text="Tại sao hàm kích hoạt ReLU lại giải quyết được vấn đề triệt tiêu đạo hàm?",
                bloom_level=BloomLevel.UNDERSTAND,
                options=[
                    QuizOptionItem(
                        key="A", text="Vì đạo hàm của nó luôn bằng 1 khi x > 0"
                    ),
                    QuizOptionItem(key="B", text="Vì nó nén giá trị vào khoảng [0, 1]"),
                    QuizOptionItem(key="C", text="Vì nó không có điểm gãy tại 0"),
                    QuizOptionItem(key="D", text="Vì nó làm mạng học chậm hơn"),
                ],
                correct_option="A",
                explanation="Khi x > 0, gradient của ReLU là hằng số 1, không bị co lại như sigmoid.",
                target_page=2,
                topic_tag="Activation Functions",
            ),
            GeneratedQuestionItem(
                question_text="Cho một ảnh kích thước 28x28 qua filter 3x3 (stride=1, no padding). Kích thước output là?",
                bloom_level=BloomLevel.APPLY,
                options=[
                    QuizOptionItem(key="A", text="26x26"),
                    QuizOptionItem(key="B", text="28x28"),
                    QuizOptionItem(key="C", text="25x25"),
                    QuizOptionItem(key="D", text="30x30"),
                ],
                correct_option="A",
                explanation="Công thức (W - K + 2P)/S + 1 = (28 - 3 + 0)/1 + 1 = 26.",
                target_page=3,
                topic_tag="CNN Calculation",
            ),
        ],
    )


# -----------------------------------------------------------------------------
# Unit Tests: Bloom Formula & Prompts
# -----------------------------------------------------------------------------


def test_compute_bloom_distribution_n5():
    dist = compute_bloom_distribution(5)
    assert dist["remember"] == 2
    assert dist["understand"] == 2
    assert dist["apply"] == 1
    assert sum(dist.values()) == 5


def test_compute_bloom_distribution_n10():
    dist = compute_bloom_distribution(10)
    assert dist["remember"] == 4
    assert dist["understand"] == 4
    assert dist["apply"] == 2
    assert sum(dist.values()) == 10


def test_compute_bloom_distribution_n7():
    dist = compute_bloom_distribution(7)
    assert dist["remember"] == 3
    assert dist["understand"] == 3
    assert dist["apply"] == 1
    assert sum(dist.values()) == 7


# -----------------------------------------------------------------------------
# Service Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quiz_service_generate_success(
    mock_user: User, sample_payload: GeneratedQuizPayload, tmp_path
):
    doc_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    fake_doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        title="Giáo trình AI",
        file_path="mock.pdf",
        file_type="pdf",
        file_size_kb=100,
        total_pages=3,
        status="ready",
    )

    # Set up mock execute results:
    # 1st call: select(Document) -> fake_doc
    # 2nd call: select(Quiz) with loaded questions -> quiz
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = fake_doc

    fake_quiz = Quiz(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        document_id=doc_id,
        title="Trắc nghiệm Tổng quan AI",
        total_questions=3,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    fake_quiz.questions = [
        QuizQuestion(
            id=uuid.uuid4(),
            quiz_id=fake_quiz.id,
            question_text=q.question_text,
            bloom_level=q.bloom_level.value,
            options=[opt.model_dump() for opt in q.options],
            correct_option=q.correct_option,
            explanation=q.explanation,
            target_page=q.target_page,
            topic_tag=q.topic_tag,
        )
        for q in sample_payload.questions
    ]

    quiz_result = MagicMock()
    quiz_result.scalar_one.return_value = fake_quiz
    mock_db.execute.side_effect = [doc_result, quiz_result]

    # Mock storage
    mock_storage = MagicMock()
    doc_dir = tmp_path / str(doc_id)
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "page_1.md").write_text("Nội dung trang 1", encoding="utf-8")
    (pages_dir / "page_2.md").write_text("Nội dung trang 2", encoding="utf-8")
    (pages_dir / "page_3.md").write_text("Nội dung trang 3", encoding="utf-8")
    mock_storage.get_document_dir.return_value = doc_dir

    # Mock Gemini Client
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = sample_payload
    mock_genai_client.aio.models.generate_content = AsyncMock(
        return_value=mock_response
    )

    service = QuizService(client=mock_genai_client, storage=mock_storage)

    req = QuizGenerateRequest(
        document_id=doc_id,
        num_questions=5,
        page_start=1,
        page_end=3,
        title="Trắc nghiệm Tổng quan AI",
    )

    created_quiz = await service.generate_quiz(mock_db, mock_user.id, req)

    assert created_quiz.title == "Trắc nghiệm Tổng quan AI"
    assert len(created_quiz.questions) == 3
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_quiz_service_document_not_found(mock_user: User):
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = doc_result

    service = QuizService()
    req = QuizGenerateRequest(document_id=uuid.uuid4(), num_questions=5)

    with pytest.raises(DocumentNotFoundError):
        await service.generate_quiz(mock_db, mock_user.id, req)


@pytest.mark.asyncio
async def test_quiz_service_idor_check(mock_user: User, other_user: User):
    doc_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    # Document belongs to other_user
    fake_doc = Document(
        id=doc_id,
        user_id=other_user.id,
        title="Private Doc",
        file_path="mock.pdf",
        file_type="pdf",
        file_size_kb=100,
        total_pages=5,
        status="ready",
    )
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = fake_doc
    mock_db.execute.return_value = doc_result

    service = QuizService()
    req = QuizGenerateRequest(document_id=doc_id, num_questions=5)

    with pytest.raises(DocumentNotFoundError):
        await service.generate_quiz(mock_db, mock_user.id, req)


@pytest.mark.asyncio
async def test_quiz_service_document_not_ready(mock_user: User):
    doc_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    fake_doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        title="Doc processing",
        file_path="mock.pdf",
        file_type="pdf",
        file_size_kb=100,
        total_pages=5,
        status="parsing",
    )
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = fake_doc
    mock_db.execute.return_value = doc_result

    service = QuizService()
    req = QuizGenerateRequest(document_id=doc_id, num_questions=5)

    with pytest.raises(DocumentNotReadyError):
        await service.generate_quiz(mock_db, mock_user.id, req)


@pytest.mark.asyncio
async def test_quiz_service_invalid_page_range(mock_user: User):
    doc_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    fake_doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        title="Doc ready",
        file_path="mock.pdf",
        file_type="pdf",
        file_size_kb=100,
        total_pages=5,
        status="ready",
    )
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = fake_doc
    mock_db.execute.return_value = doc_result

    service = QuizService()
    req = QuizGenerateRequest(
        document_id=doc_id, num_questions=5, page_start=4, page_end=2
    )

    with pytest.raises(InvalidPageRangeError):
        await service.generate_quiz(mock_db, mock_user.id, req)


@pytest.mark.asyncio
async def test_quiz_service_model_fallback_on_503(
    mock_user: User, sample_payload: GeneratedQuizPayload, tmp_path
):
    doc_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    fake_doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        title="Doc fallback",
        file_path="mock.pdf",
        file_type="pdf",
        file_size_kb=100,
        total_pages=2,
        status="ready",
    )
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = fake_doc

    fake_quiz = Quiz(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        document_id=doc_id,
        title="Quiz Fallback",
        total_questions=3,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    fake_quiz.questions = []
    quiz_result = MagicMock()
    quiz_result.scalar_one.return_value = fake_quiz
    mock_db.execute.side_effect = [doc_result, quiz_result]

    mock_storage = MagicMock()
    doc_dir = tmp_path / str(doc_id)
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "page_1.md").write_text("Trang 1", encoding="utf-8")
    mock_storage.get_document_dir.return_value = doc_dir

    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.parsed = sample_payload

    # First model call raises 503 UNAVAILABLE, second model call succeeds
    mock_genai_client.aio.models.generate_content = AsyncMock(
        side_effect=[RuntimeError("503 UNAVAILABLE: high demand"), mock_response]
    )

    service = QuizService(client=mock_genai_client, storage=mock_storage)
    req = QuizGenerateRequest(
        document_id=doc_id, num_questions=5, page_start=1, page_end=1
    )

    created_quiz = await service.generate_quiz(mock_db, mock_user.id, req)
    assert created_quiz is not None
    assert mock_genai_client.aio.models.generate_content.await_count == 2


@pytest.mark.asyncio
async def test_quiz_service_gemini_failure(mock_user: User, tmp_path):
    doc_id = uuid.uuid4()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    fake_doc = Document(
        id=doc_id,
        user_id=mock_user.id,
        title="Doc ready",
        file_path="mock.pdf",
        file_type="pdf",
        file_size_kb=100,
        total_pages=2,
        status="ready",
    )
    doc_result = MagicMock()
    doc_result.scalar_one_or_none.return_value = fake_doc
    mock_db.execute.return_value = doc_result

    mock_storage = MagicMock()
    doc_dir = tmp_path / str(doc_id)
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "page_1.md").write_text("Trang 1", encoding="utf-8")
    mock_storage.get_document_dir.return_value = doc_dir

    mock_genai_client = MagicMock()
    mock_genai_client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError("API quota exceeded")
    )

    service = QuizService(client=mock_genai_client, storage=mock_storage)
    req = QuizGenerateRequest(
        document_id=doc_id, num_questions=5, page_start=1, page_end=1
    )

    with pytest.raises(GeminiGenerationError):
        await service.generate_quiz(mock_db, mock_user.id, req)


# -----------------------------------------------------------------------------
# Endpoint Tests: HTTP API
# -----------------------------------------------------------------------------


@pytest.fixture
def client_with_user(mock_user: User):
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as test_client:
        yield test_client, mock_db
    app.dependency_overrides.clear()


def test_api_generate_quiz_success(
    client_with_user, mock_user: User, sample_payload: GeneratedQuizPayload
):
    client, _ = client_with_user
    doc_id = uuid.uuid4()
    quiz_id = uuid.uuid4()

    fake_quiz = Quiz(
        id=quiz_id,
        user_id=mock_user.id,
        document_id=doc_id,
        title=sample_payload.title,
        total_questions=len(sample_payload.questions),
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    fake_quiz.questions = [
        QuizQuestion(
            id=uuid.uuid4(),
            quiz_id=fake_quiz.id,
            question_text=q.question_text,
            bloom_level=q.bloom_level.value,
            options=[opt.model_dump() for opt in q.options],
            correct_option=q.correct_option,
            explanation=q.explanation,
            target_page=q.target_page,
            topic_tag=q.topic_tag,
        )
        for q in sample_payload.questions
    ]

    with patch.object(
        quiz_service, "generate_quiz", new_callable=AsyncMock
    ) as mock_gen:
        mock_gen.return_value = fake_quiz

        body = {
            "document_id": str(doc_id),
            "num_questions": 5,
            "page_start": 1,
            "page_end": 3,
        }
        response = client.post("/api/v1/quizzes/generate", json=body)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(quiz_id)
        assert data["title"] == sample_payload.title
        assert len(data["questions"]) == 3
        assert data["questions"][0]["options"][0]["key"] == "A"
        assert data["questions"][0]["target_page"] == 1


def test_api_generate_quiz_document_not_found(client_with_user):
    client, _ = client_with_user
    doc_id = uuid.uuid4()

    with patch.object(
        quiz_service, "generate_quiz", side_effect=DocumentNotFoundError(doc_id)
    ):
        response = client.post(
            "/api/v1/quizzes/generate",
            json={"document_id": str(doc_id), "num_questions": 5},
        )
        assert response.status_code == 404
        assert str(doc_id) in response.json()["detail"]


def test_api_generate_quiz_document_not_ready(client_with_user):
    client, _ = client_with_user
    doc_id = uuid.uuid4()

    with patch.object(
        quiz_service, "generate_quiz", side_effect=DocumentNotReadyError(doc_id)
    ):
        response = client.post(
            "/api/v1/quizzes/generate",
            json={"document_id": str(doc_id), "num_questions": 5},
        )
        assert response.status_code == 400


def test_api_generate_quiz_invalid_page_range(client_with_user):
    client, _ = client_with_user
    doc_id = uuid.uuid4()

    with patch.object(
        quiz_service,
        "generate_quiz",
        side_effect=InvalidPageRangeError("Khoảng trang không hợp lệ"),
    ):
        response = client.post(
            "/api/v1/quizzes/generate",
            json={"document_id": str(doc_id), "num_questions": 5},
        )
        assert response.status_code == 422


def test_api_get_quiz_success(
    client_with_user, mock_user: User, sample_payload: GeneratedQuizPayload
):
    client, _ = client_with_user
    doc_id = uuid.uuid4()
    quiz_id = uuid.uuid4()

    fake_quiz = Quiz(
        id=quiz_id,
        user_id=mock_user.id,
        document_id=doc_id,
        title="Trắc nghiệm AI",
        total_questions=3,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    fake_quiz.questions = [
        QuizQuestion(
            id=uuid.uuid4(),
            quiz_id=fake_quiz.id,
            question_text=q.question_text,
            bloom_level=q.bloom_level.value,
            options=[opt.model_dump() for opt in q.options],
            correct_option=q.correct_option,
            explanation=q.explanation,
            target_page=q.target_page,
            topic_tag=q.topic_tag,
        )
        for q in sample_payload.questions
    ]

    with patch.object(
        quiz_service, "get_quiz_by_id", new_callable=AsyncMock
    ) as mock_get:
        mock_get.return_value = fake_quiz

        response = client.get(f"/api/v1/quizzes/{quiz_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(quiz_id)
        assert len(data["questions"]) == 3


def test_api_get_quiz_not_found(client_with_user):
    client, _ = client_with_user
    quiz_id = uuid.uuid4()

    with patch.object(
        quiz_service, "get_quiz_by_id", side_effect=QuizNotFoundError(quiz_id)
    ):
        response = client.get(f"/api/v1/quizzes/{quiz_id}")
        assert response.status_code == 404
        assert str(quiz_id) in response.json()["detail"]


def test_api_unauthorized():
    # Make request without dependency overrides or token
    with TestClient(app) as anonymous_client:
        response = anonymous_client.post(
            "/api/v1/quizzes/generate",
            json={"document_id": str(uuid.uuid4()), "num_questions": 5},
        )
        assert response.status_code == 401


def test_api_list_quizzes_success(
    client_with_user, mock_user: User, sample_payload: GeneratedQuizPayload
):
    client, _ = client_with_user
    doc_id = uuid.uuid4()
    quiz_id = uuid.uuid4()

    fake_quiz = Quiz(
        id=quiz_id,
        user_id=mock_user.id,
        document_id=doc_id,
        title="Trắc nghiệm Danh sách AI",
        total_questions=3,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    fake_quiz.questions = [
        QuizQuestion(
            id=uuid.uuid4(),
            quiz_id=fake_quiz.id,
            question_text=q.question_text,
            bloom_level=q.bloom_level.value,
            options=[opt.model_dump() for opt in q.options],
            correct_option=q.correct_option,
            explanation=q.explanation,
            target_page=q.target_page,
            topic_tag=q.topic_tag,
        )
        for q in sample_payload.questions
    ]

    with patch.object(
        quiz_service, "list_user_quizzes", new_callable=AsyncMock
    ) as mock_list:
        mock_list.return_value = [fake_quiz]

        response = client.get("/api/v1/quizzes")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(quiz_id)
        assert data[0]["title"] == "Trắc nghiệm Danh sách AI"


def test_api_delete_quiz_success(client_with_user):
    client, _ = client_with_user
    quiz_id = uuid.uuid4()

    with patch.object(
        quiz_service, "delete_quiz", new_callable=AsyncMock
    ) as mock_del:
        mock_del.return_value = None

        response = client.delete(f"/api/v1/quizzes/{quiz_id}")
        assert response.status_code == 204


def test_api_delete_quiz_not_found(client_with_user):
    client, _ = client_with_user
    quiz_id = uuid.uuid4()

    with patch.object(
        quiz_service, "delete_quiz", side_effect=QuizNotFoundError(quiz_id)
    ):
        response = client.delete(f"/api/v1/quizzes/{quiz_id}")
        assert response.status_code == 404
        assert str(quiz_id) in response.json()["detail"]
