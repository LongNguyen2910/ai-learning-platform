import json
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from llama_index.core.embeddings import MockEmbedding
from llama_index.core.schema import NodeWithScore, TextNode
from qdrant_client import QdrantClient

from app.core.config import settings
from app.main import app
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.chat.router import get_chat_rag_service
from app.modules.chat.schemas import RetrievedChunkDTO
from app.modules.chat.service import ChatRAGService
from app.modules.documents.schemas import DocumentMetadata, ParsedPageMetadata
from app.modules.documents.vector_service import DocumentVectorService

MOCK_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
ADMIN_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

MOCK_USER = User(
    id=MOCK_USER_ID,
    email="student@example.com",
    hashed_password="hashed_pwd",
    role="student",
    is_active=True,
)

OTHER_USER = User(
    id=OTHER_USER_ID,
    email="other@example.com",
    hashed_password="hashed_pwd",
    role="student",
    is_active=True,
)

ADMIN_USER = User(
    id=ADMIN_USER_ID,
    email="admin@example.com",
    hashed_password="hashed_pwd",
    role="admin",
    is_active=True,
)


@pytest.fixture
def mock_embed_model():
    return MockEmbedding(embed_dim=3072)


@pytest.fixture
def memory_qdrant_client():
    return QdrantClient(":memory:")


@pytest.fixture
def vector_service(memory_qdrant_client, mock_embed_model):
    vs = DocumentVectorService(
        qdrant_client=memory_qdrant_client,
        embed_model=mock_embed_model,
        collection_name="test_learning_chunks",
        chunk_size=128,
        chunk_overlap=20,
    )
    vs.ensure_collection_ready()
    return vs


@pytest.fixture
def chat_rag_service(vector_service):
    return ChatRAGService(vector_service=vector_service)


@pytest.fixture
def temp_dirs(monkeypatch):
    temp_upload = tempfile.mkdtemp()
    temp_parsed = tempfile.mkdtemp()
    monkeypatch.setattr(settings, "UPLOAD_DIR", temp_upload)
    monkeypatch.setattr(settings, "PARSED_DIR", temp_parsed)
    yield Path(temp_upload), Path(temp_parsed)
    shutil.rmtree(temp_upload, ignore_errors=True)
    shutil.rmtree(temp_parsed, ignore_errors=True)


@pytest.fixture
def client():
    app.dependency_overrides[get_current_active_user] = lambda: MOCK_USER
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_chat_rag_service, None)


# ============================================================================
# UNIT TESTS: ChatRAGService
# ============================================================================


@pytest.mark.asyncio
async def test_retrieve_chunks_by_doc_id(chat_rag_service, vector_service, tmp_path):
    doc_id = "doc_unit_1"

    p1 = tmp_path / "page_1.md"
    p1.write_text(
        "Định lý Pythagore: Bình phương cạnh huyền bằng tổng bình phương hai cạnh góc vuông: $$a^2 + b^2 = c^2$$.",
        encoding="utf-8",
    )
    p2 = tmp_path / "page_2.md"
    p2.write_text(
        "Định luật 2 Newton: Gia tốc tỉ lệ thuận với hợp lực: $$F = ma$$.",
        encoding="utf-8",
    )

    pages = [
        ParsedPageMetadata(
            page_number=1,
            has_formula=True,
            has_image=False,
            char_count=len(p1.read_text()),
            file_path=str(p1),
        ),
        ParsedPageMetadata(
            page_number=2,
            has_formula=True,
            has_image=False,
            char_count=len(p2.read_text()),
            file_path=str(p2),
        ),
    ]

    vector_service.index_document_pages(doc_id, pages)

    # Retrieval across all pages
    results = await chat_rag_service.retrieve_relevant_chunks(
        document_id=doc_id,
        query="Pythagore",
        similarity_top_k=5,
        score_threshold=0.5,
    )

    assert len(results) >= 1
    first = results[0]
    assert isinstance(first, RetrievedChunkDTO)
    assert first.citation_tag in ["[[Trang 1]]", "[[Trang 2]]"]
    assert first.score >= 0.5
    assert first.content != ""


@pytest.mark.asyncio
async def test_retrieve_chunks_with_page_number_filter(
    chat_rag_service, vector_service, tmp_path
):
    doc_id = "doc_unit_page_filter"

    p1 = tmp_path / "page_1.md"
    p1.write_text("Chương 1: Mở đầu về giải tích và đạo hàm.", encoding="utf-8")
    p2 = tmp_path / "page_2.md"
    p2.write_text(
        "Chương 2: Tích phân Riemann và ứng dụng tính diện tích.", encoding="utf-8"
    )

    pages = [
        ParsedPageMetadata(
            page_number=1,
            has_formula=False,
            has_image=False,
            char_count=len(p1.read_text()),
            file_path=str(p1),
        ),
        ParsedPageMetadata(
            page_number=2,
            has_formula=False,
            has_image=False,
            char_count=len(p2.read_text()),
            file_path=str(p2),
        ),
    ]

    vector_service.index_document_pages(doc_id, pages)

    # Filter explicitly for page 2
    results = await chat_rag_service.retrieve_relevant_chunks(
        document_id=doc_id,
        query="toán học",
        page_number=2,
        similarity_top_k=5,
    )

    assert len(results) > 0
    for chunk in results:
        assert chunk.page_number == 2
        assert chunk.citation_tag == "[[Trang 2]]"


@pytest.mark.asyncio
async def test_retrieve_chunks_score_threshold_filters_out_low_scores(vector_service):
    # Test score filtering logic with mocked retriever returning low score
    mock_retriever = AsyncMock()
    low_score_node = NodeWithScore(
        node=TextNode(
            text="Nội dung không liên quan",
            metadata={"page_number": 1, "chunk_index": 0},
        ),
        score=0.35,
    )
    mock_retriever.aretrieve.return_value = [low_score_node]

    custom_vs = DocumentVectorService(
        qdrant_client=QdrantClient(":memory:"),
        embed_model=MockEmbedding(embed_dim=3072),
    )
    custom_vs.get_retriever = lambda *args, **kwargs: mock_retriever

    service = ChatRAGService(vector_service=custom_vs)

    # Query with default threshold = 0.5; node with 0.35 must be filtered out
    results = await service.retrieve_relevant_chunks(
        document_id="doc_irrelevant",
        query="vật lý lượng tử",
        score_threshold=0.5,
    )
    assert results == []

    # If threshold is lowered to 0.3, node passes
    results_passed = await service.retrieve_relevant_chunks(
        document_id="doc_irrelevant",
        query="vật lý lượng tử",
        score_threshold=0.3,
    )
    assert len(results_passed) == 1
    assert results_passed[0].score == 0.35
    assert results_passed[0].citation_tag == "[[Trang 1]]"


# ============================================================================
# INTEGRATION TESTS: REST Endpoint POST /api/v1/chat/documents/{id}/retrieval
# ============================================================================


def _create_mock_document_storage(
    temp_parsed: Path,
    doc_id: str,
    status: str = "ready",
    user_id: str | None = str(MOCK_USER_ID),
):
    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    meta = DocumentMetadata(
        document_id=doc_id,
        user_id=user_id,
        title="Giáo trình Toán cao cấp",
        file_path=str(doc_dir / "doc.pdf"),
        file_size_kb=100,
        total_pages=5,
        status=status,
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta.model_dump(), f)
    return meta


def test_endpoint_retrieval_success(client, temp_dirs, chat_rag_service):
    _, temp_parsed = temp_dirs
    doc_id = "doc_test_success_123"
    _create_mock_document_storage(temp_parsed, doc_id, status="ready")

    # Inject mock retrieval chunks via dependency override
    mock_service = AsyncMock()
    mock_service.retrieve_relevant_chunks.return_value = [
        RetrievedChunkDTO(
            chunk_id="chunk_001",
            page_number=3,
            chunk_index=0,
            score=0.8875,
            content="Nội dung trang 3 về chuỗi Fourier",
            has_formula=True,
            has_image=False,
            citation_tag="[[Trang 3]]",
        )
    ]
    app.dependency_overrides[get_chat_rag_service] = lambda: mock_service

    payload = {
        "query": "Chuỗi Fourier là gì?",
        "page_number": 3,
        "similarity_top_k": 3,
        "score_threshold": 0.6,
    }

    response = client.post(f"/api/v1/chat/documents/{doc_id}/retrieval", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["document_id"] == doc_id
    assert data["query"] == payload["query"]
    assert data["total_retrieved"] == 1
    assert len(data["chunks"]) == 1

    chunk = data["chunks"][0]
    assert chunk["chunk_id"] == "chunk_001"
    assert chunk["page_number"] == 3
    assert chunk["citation_tag"] == "[[Trang 3]]"
    assert chunk["score"] == 0.8875
    assert chunk["has_formula"] is True
    assert chunk["has_image"] is False


def test_endpoint_document_not_ready(client, temp_dirs):
    _, temp_parsed = temp_dirs
    doc_id = "doc_indexing_456"
    _create_mock_document_storage(temp_parsed, doc_id, status="indexing")

    payload = {"query": "Câu hỏi tra cứu"}
    response = client.post(f"/api/v1/chat/documents/{doc_id}/retrieval", json=payload)

    assert response.status_code == 400
    assert "not ready" in response.json()["detail"]


def test_endpoint_document_not_found(client, temp_dirs):
    payload = {"query": "Câu hỏi bất kỳ"}
    response = client.post(
        "/api/v1/chat/documents/non_existent_doc_id/retrieval", json=payload
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_retrieval_endpoint_auth_and_ownership(client, temp_dirs):
    _, temp_parsed = temp_dirs
    # Document owned by OTHER_USER
    doc_id = "doc_owned_by_bob"
    _create_mock_document_storage(
        temp_parsed, doc_id, status="ready", user_id=str(OTHER_USER_ID)
    )

    # Current user is MOCK_USER (student, not admin, not owner)
    payload = {"query": "Nội dung bí mật"}
    response = client.post(f"/api/v1/chat/documents/{doc_id}/retrieval", json=payload)

    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()


def test_retrieval_endpoint_admin_cannot_access_other_user_private_document(temp_dirs):
    """Admin role must respect privacy principles and cannot access other users' private documents."""
    _, temp_parsed = temp_dirs
    doc_id = "doc_for_admin_check"
    _create_mock_document_storage(
        temp_parsed, doc_id, status="ready", user_id=str(OTHER_USER_ID)
    )

    app.dependency_overrides[get_current_active_user] = lambda: ADMIN_USER
    mock_service = AsyncMock()
    mock_service.retrieve_relevant_chunks.return_value = []
    app.dependency_overrides[get_chat_rag_service] = lambda: mock_service

    with TestClient(app) as test_client:
        response = test_client.post(
            f"/api/v1/chat/documents/{doc_id}/retrieval",
            json={"query": "Admin audit"},
        )
        assert response.status_code == 403
        assert "permission" in response.json()["detail"].lower()

    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_chat_rag_service, None)


def test_retrieval_endpoint_admin_can_access_own_document(temp_dirs):
    """Admin can retrieve chunks for documents they personally own."""
    _, temp_parsed = temp_dirs
    doc_id = "doc_admin_own"
    _create_mock_document_storage(
        temp_parsed, doc_id, status="ready", user_id=str(ADMIN_USER_ID)
    )

    app.dependency_overrides[get_current_active_user] = lambda: ADMIN_USER
    mock_service = AsyncMock()
    mock_service.retrieve_relevant_chunks.return_value = []
    app.dependency_overrides[get_chat_rag_service] = lambda: mock_service

    with TestClient(app) as test_client:
        response = test_client.post(
            f"/api/v1/chat/documents/{doc_id}/retrieval",
            json={"query": "Admin search own file"},
        )
        assert response.status_code == 200
        assert response.json()["total_retrieved"] == 0

    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_chat_rag_service, None)


def test_retrieval_endpoint_qdrant_error_returns_503(client, temp_dirs):
    _, temp_parsed = temp_dirs
    doc_id = "doc_qdrant_down"
    _create_mock_document_storage(temp_parsed, doc_id, status="ready")

    mock_service = AsyncMock()
    mock_service.retrieve_relevant_chunks.side_effect = RuntimeError(
        "Qdrant connection timed out"
    )
    app.dependency_overrides[get_chat_rag_service] = lambda: mock_service

    payload = {"query": "Tra cứu khi Qdrant sập"}
    response = client.post(f"/api/v1/chat/documents/{doc_id}/retrieval", json=payload)

    assert response.status_code == 503
    assert "tạm thời gián đoạn" in response.json()["detail"]


def test_retrieval_endpoint_request_validation(client, temp_dirs):
    _, temp_parsed = temp_dirs
    doc_id = "doc_validation_check"
    _create_mock_document_storage(temp_parsed, doc_id, status="ready")

    # query too short (min_length=2)
    response = client.post(
        f"/api/v1/chat/documents/{doc_id}/retrieval", json={"query": "a"}
    )
    assert response.status_code == 422

    # score_threshold > 1.0 (le=1.0)
    response2 = client.post(
        f"/api/v1/chat/documents/{doc_id}/retrieval",
        json={"query": "Hợp lệ", "score_threshold": 1.5},
    )
    assert response2.status_code == 422

    # similarity_top_k > 20 (le=20)
    response3 = client.post(
        f"/api/v1/chat/documents/{doc_id}/retrieval",
        json={"query": "Hợp lệ", "similarity_top_k": 50},
    )
    assert response3.status_code == 422


def test_retrieval_endpoint_public_doc_allowed(temp_dirs):
    _, temp_parsed = temp_dirs
    doc_uuid = uuid.uuid4()
    doc_id = str(doc_uuid)
    _create_mock_document_storage(
        temp_parsed, doc_id, status="ready", user_id=str(OTHER_USER_ID)
    )

    from app.core.database import get_db
    from app.modules.documents.models import Document

    mock_db = AsyncMock()
    mock_db.scalar.return_value = Document(
        id=doc_uuid,
        user_id=OTHER_USER_ID,
        title="Tài liệu công khai",
        file_path="dummy.pdf",
        file_type="pdf",
        file_size_kb=50,
        total_pages=1,
        is_public=True,
        status="ready",
    )
    mock_service = AsyncMock()
    mock_service.retrieve_relevant_chunks.return_value = []

    app.dependency_overrides[get_current_active_user] = lambda: MOCK_USER
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_chat_rag_service] = lambda: mock_service

    with TestClient(app) as test_client:
        response = test_client.post(
            f"/api/v1/chat/documents/{doc_id}/retrieval",
            json={"query": "Tài liệu công khai"},
        )
        assert response.status_code == 200
        assert response.json()["total_retrieved"] == 0

    app.dependency_overrides.pop(get_current_active_user, None)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_chat_rag_service, None)
