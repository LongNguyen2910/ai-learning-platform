import json
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from llama_index.core.embeddings import MockEmbedding
from qdrant_client import QdrantClient

from app.core.config import settings
from app.main import app
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.documents.schemas import DocumentMetadata, ParsedPageMetadata
from app.modules.documents.vector_service import DocumentVectorService

USER_ALICE_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_BOB_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

USER_ALICE = User(
    id=USER_ALICE_ID,
    email="alice@example.com",
    hashed_password="hashed_pwd_alice",
    role="student",
    is_active=True,
)

USER_BOB = User(
    id=USER_BOB_ID,
    email="bob@example.com",
    hashed_password="hashed_pwd_bob",
    role="student",
    is_active=True,
)


@pytest.fixture
def temp_dirs(monkeypatch):
    temp_upload = tempfile.mkdtemp()
    temp_parsed = tempfile.mkdtemp()
    monkeypatch.setattr(settings, "UPLOAD_DIR", temp_upload)
    monkeypatch.setattr(settings, "PARSED_DIR", temp_parsed)
    yield Path(temp_upload), Path(temp_parsed)
    shutil.rmtree(temp_upload, ignore_errors=True)
    shutil.rmtree(temp_parsed, ignore_errors=True)


def test_idor_user_bob_cannot_access_user_alice_document(temp_dirs):
    temp_upload, temp_parsed = temp_dirs
    alice_doc_id = str(uuid.uuid4())

    # Create Alice's document in Alice's user storage
    alice_upload_dir = temp_upload / str(USER_ALICE_ID)
    alice_upload_dir.mkdir(parents=True, exist_ok=True)
    pdf_file = alice_upload_dir / f"{alice_doc_id}.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy alice document")

    doc_dir = temp_parsed / alice_doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    (pages_dir / "page_1.md").write_text("# Alice Private Research")

    meta = DocumentMetadata(
        document_id=alice_doc_id,
        user_id=str(USER_ALICE_ID),
        title="Alice Secret Document",
        file_path=str(pdf_file),
        file_size_kb=20,
        total_pages=1,
        status="ready",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta.model_dump(), f)

    # Bob logs in and tries to access Alice's document
    app.dependency_overrides[get_current_active_user] = lambda: USER_BOB
    with TestClient(app) as client:
        # 1. Content access -> must return 404
        res_content = client.get(f"/api/v1/documents/{alice_doc_id}/content")
        assert res_content.status_code == 404
        assert "not found" in res_content.json()["detail"].lower()

        # 2. File download -> must return 404
        res_file = client.get(f"/api/v1/documents/{alice_doc_id}/file")
        assert res_file.status_code == 404

        # 3. Status check -> must return 404
        res_status = client.get(f"/api/v1/documents/{alice_doc_id}/status")
        assert res_status.status_code == 404

        # 4. Retry parsing -> must return 404
        res_retry = client.post(f"/api/v1/documents/{alice_doc_id}/retry")
        assert res_retry.status_code == 404

        # 5. Delete document -> must return 404
        res_delete = client.delete(f"/api/v1/documents/{alice_doc_id}")
        assert res_delete.status_code == 404

        # File and metadata must still exist untouched
        assert pdf_file.exists()
        assert doc_dir.exists()

    app.dependency_overrides.pop(get_current_active_user, None)


def test_document_list_isolated_between_users(temp_dirs):
    _, temp_parsed = temp_dirs

    # Create Alice document
    alice_doc_id = str(uuid.uuid4())
    alice_dir = temp_parsed / alice_doc_id
    alice_dir.mkdir(parents=True, exist_ok=True)
    alice_meta = DocumentMetadata(
        document_id=alice_doc_id,
        user_id=str(USER_ALICE_ID),
        title="Alice Doc",
        file_path="dummy.pdf",
        file_size_kb=10,
        total_pages=1,
        status="ready",
    )
    with open(alice_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(alice_meta.model_dump(), f)

    # Create Bob document
    bob_doc_id = str(uuid.uuid4())
    bob_dir = temp_parsed / bob_doc_id
    bob_dir.mkdir(parents=True, exist_ok=True)
    bob_meta = DocumentMetadata(
        document_id=bob_doc_id,
        user_id=str(USER_BOB_ID),
        title="Bob Doc",
        file_path="dummy.pdf",
        file_size_kb=10,
        total_pages=1,
        status="ready",
    )
    with open(bob_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(bob_meta.model_dump(), f)

    # Alice queries list -> sees only Alice's doc
    app.dependency_overrides[get_current_active_user] = lambda: USER_ALICE
    with TestClient(app) as client:
        res = client.get("/api/v1/documents")
        assert res.status_code == 200
        items = res.json()
        doc_ids = [item["document_id"] for item in items]
        assert alice_doc_id in doc_ids
        assert bob_doc_id not in doc_ids

    # Bob queries list -> sees only Bob's doc
    app.dependency_overrides[get_current_active_user] = lambda: USER_BOB
    with TestClient(app) as client:
        res = client.get("/api/v1/documents")
        assert res.status_code == 200
        items = res.json()
        doc_ids = [item["document_id"] for item in items]
        assert bob_doc_id in doc_ids
        assert alice_doc_id not in doc_ids

    app.dependency_overrides.pop(get_current_active_user, None)


def test_qdrant_vector_retriever_multi_tenant_isolation(tmp_path):
    """Verifies that RAG retrieval filtered by user_id completely prevents cross-tenant data leakage."""
    memory_client = QdrantClient(":memory:")
    mock_embed = MockEmbedding(embed_dim=3072)
    vector_svc = DocumentVectorService(
        qdrant_client=memory_client,
        embed_model=mock_embed,
        collection_name="tenant_rag_test",
    )
    vector_svc.ensure_collection_ready()

    alice_doc_id = "alice-rag-doc"
    page1 = tmp_path / "alice_p1.md"
    page1.write_text("Công thức toán giải tích bí mật của Alice: integral(x^2 dx)")
    page_meta = ParsedPageMetadata(
        page_number=1,
        has_formula=True,
        has_image=False,
        char_count=len(page1.read_text()),
        file_path=str(page1),
    )

    # Index document with Alice's user_id
    indexed_chunks = vector_svc.index_document_pages(
        document_id=alice_doc_id,
        pages_meta=[page_meta],
        user_id=str(USER_ALICE_ID),
    )
    assert indexed_chunks > 0

    # 1. Bob attempts retrieval with Bob's user_id -> must retrieve NOTHING
    bob_retriever = vector_svc.get_retriever(
        user_id=str(USER_BOB_ID),
        similarity_top_k=5,
    )
    bob_results = bob_retriever.retrieve("công thức toán giải tích")
    assert len(bob_results) == 0

    # 2. Alice retrieves with Alice's user_id -> must retrieve Alice's chunk
    alice_retriever = vector_svc.get_retriever(
        user_id=str(USER_ALICE_ID),
        similarity_top_k=5,
    )
    alice_results = alice_retriever.retrieve("công thức toán giải tích")
    assert len(alice_results) > 0
    assert "Alice" in alice_results[0].node.get_text()
    assert alice_results[0].node.metadata["user_id"] == str(USER_ALICE_ID)
