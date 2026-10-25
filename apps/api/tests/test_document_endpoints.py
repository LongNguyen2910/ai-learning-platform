import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.modules.documents.schemas import DocumentMetadata


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_dirs(monkeypatch):
    temp_upload = tempfile.mkdtemp()
    temp_parsed = tempfile.mkdtemp()
    monkeypatch.setattr(settings, "UPLOAD_DIR", temp_upload)
    monkeypatch.setattr(settings, "PARSED_DIR", temp_parsed)
    yield Path(temp_upload), Path(temp_parsed)
    shutil.rmtree(temp_upload, ignore_errors=True)
    shutil.rmtree(temp_parsed, ignore_errors=True)


def test_delete_document_not_found(client, temp_dirs):
    response = client.delete("/api/v1/documents/non-existent-doc-id")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_delete_document_success(client, temp_dirs):
    temp_upload, temp_parsed = temp_dirs
    doc_id = "test-doc-123"

    # Create dummy pdf file in upload dir
    pdf_file = temp_upload / f"{doc_id}.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy content")

    # Create dummy parsed dir with metadata and page
    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    (doc_dir / "pages").mkdir(parents=True, exist_ok=True)
    (doc_dir / "pages" / "page_1.md").write_text("# Page 1")

    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Test Doc",
        file_path=str(pdf_file),
        file_size_kb=10,
        total_pages=1,
        status="failed",
        error_message="Something went wrong",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f)

    # Call DELETE endpoint
    response = client.delete(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == doc_id
    assert "deleted successfully" in data["message"]

    # Verify files and folders are gone
    assert not pdf_file.exists()
    assert not doc_dir.exists()


def test_retry_document_not_found(client, temp_dirs):
    response = client.post("/api/v1/documents/non-existent-doc-id/retry")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_retry_document_already_parsing(client, temp_dirs):
    temp_upload, temp_parsed = temp_dirs
    doc_id = "parsing-doc-456"

    pdf_file = temp_upload / f"{doc_id}.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Parsing Doc",
        file_path=str(pdf_file),
        file_size_kb=5,
        total_pages=1,
        status="parsing",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f)

    from app.modules.documents.service import ingestion_service

    ingestion_service.mark_task_active(doc_id)
    try:
        response = client.post(f"/api/v1/documents/{doc_id}/retry")
        assert response.status_code == 409
        assert "currently being processed" in response.json()["detail"]
    finally:
        ingestion_service.mark_task_inactive(doc_id)


def test_retry_document_already_indexing(client, temp_dirs):
    temp_upload, temp_parsed = temp_dirs
    doc_id = "indexing-doc-456"

    pdf_file = temp_upload / f"{doc_id}.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Indexing Doc",
        file_path=str(pdf_file),
        file_size_kb=5,
        total_pages=1,
        status="indexing",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f)

    from app.modules.documents.service import ingestion_service

    ingestion_service.mark_task_active(doc_id)
    try:
        response = client.post(f"/api/v1/documents/{doc_id}/retry")
        assert response.status_code == 409
        assert "currently being processed (indexing)" in response.json()["detail"]
    finally:
        ingestion_service.mark_task_inactive(doc_id)


@patch("app.modules.documents.service.IngestionService.run_ingestion_pipeline")
def test_retry_document_stale_parsing_allowed(
    mock_run_pipeline, client, temp_dirs
):
    temp_upload, temp_parsed = temp_dirs
    doc_id = "stale-parsing-doc-456"

    pdf_file = temp_upload / f"{doc_id}.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Stale Parsing Doc",
        file_path=str(pdf_file),
        file_size_kb=5,
        total_pages=1,
        status="parsing",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f)

    # Note: Not active in memory (simulating restart after crash)
    response = client.post(f"/api/v1/documents/{doc_id}/retry")
    assert response.status_code == 202
    assert response.json()["status"] == "parsing"


def test_retry_document_missing_pdf_file(client, temp_dirs):
    temp_upload, temp_parsed = temp_dirs
    doc_id = "missing-pdf-doc-789"

    # Metadata exists but PDF file is missing
    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Missing PDF Doc",
        file_path=str(temp_upload / "non-existent.pdf"),
        file_size_kb=5,
        total_pages=1,
        status="failed",
        error_message="Rate limit 429",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f)

    response = client.post(f"/api/v1/documents/{doc_id}/retry")
    assert response.status_code == 400
    assert "Original PDF file is missing" in response.json()["detail"]


@patch("app.modules.documents.service.IngestionService.run_ingestion_pipeline")
def test_retry_document_success(mock_run_pipeline, client, temp_dirs):
    temp_upload, temp_parsed = temp_dirs
    doc_id = "failed-doc-999"

    pdf_file = temp_upload / f"{doc_id}.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Failed Doc",
        file_path=str(pdf_file),
        file_size_kb=10,
        total_pages=3,
        status="failed",
        error_message="Quota exhausted: 429",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f)

    response = client.post(f"/api/v1/documents/{doc_id}/retry")
    assert response.status_code == 202
    data = response.json()
    assert data["document_id"] == doc_id
    assert data["status"] == "parsing"
    assert data["total_pages"] == 3
    assert "Retry scheduled" in data["message"]

    # Verify metadata was reset
    with open(doc_dir / "metadata.json", "r", encoding="utf-8") as f:
        saved_meta = json.load(f)
    assert saved_meta["status"] == "parsing"
    assert saved_meta["error_message"] is None


@pytest.mark.asyncio
async def test_recover_interrupted_documents_with_pdf(temp_dirs):
    temp_upload, temp_parsed = temp_dirs
    from app.modules.documents.service import IngestionService

    doc_id = "interrupted-doc-111"
    pdf_file = temp_upload / f"{doc_id}.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Interrupted Doc",
        file_path=str(pdf_file),
        file_size_kb=5,
        total_pages=1,
        status="parsing",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f)

    service = IngestionService(parsed_base_dir=str(temp_parsed))
    with patch.object(service, "run_ingestion_pipeline"):
        recovered = await service.recover_interrupted_documents()
        assert doc_id in recovered
        assert service.is_task_active(doc_id)
        # Clean up active state
        service.mark_task_inactive(doc_id)


@pytest.mark.asyncio
async def test_recover_interrupted_documents_missing_pdf(temp_dirs):
    temp_upload, temp_parsed = temp_dirs
    from app.modules.documents.service import IngestionService

    doc_id = "interrupted-missing-pdf-222"
    doc_dir = temp_parsed / doc_id
    doc_dir.mkdir(parents=True, exist_ok=True)
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Missing PDF Interrupted",
        file_path=str(temp_upload / "non-existent.pdf"),
        file_size_kb=5,
        total_pages=1,
        status="indexing",
    )
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata.model_dump(), f)

    service = IngestionService(parsed_base_dir=str(temp_parsed))
    recovered = await service.recover_interrupted_documents()
    assert doc_id not in recovered
    reloaded = service.load_metadata(doc_id)
    assert reloaded.status == "failed"
    assert "không tìm thấy file PDF gốc" in reloaded.error_message


def test_format_user_friendly_error_messages():
    from app.modules.documents.service import format_user_friendly_error

    # Rate limit error
    msg = format_user_friendly_error("Bóc tách nội dung AI", Exception("Resource has been exhausted (e.g. check quota). [429]"))
    assert "Lỗi ở bước [Bóc tách nội dung AI]" in msg
    assert "Vượt quá giới hạn lượt gọi API" in msg

    # API key error
    msg = format_user_friendly_error("Bóc tách nội dung AI", Exception("API_KEY_INVALID: API key not valid."))
    assert "Lỗi ở bước [Bóc tách nội dung AI]" in msg
    assert "Khóa API không hợp lệ" in msg

    # Qdrant error
    msg = format_user_friendly_error("Đánh chỉ mục vector", Exception("Qdrant connection refused on localhost:6333"))
    assert "Lỗi ở bước [Đánh chỉ mục vector]" in msg
    assert "Qdrant" in msg

    # File permission / Security violation error
    msg = format_user_friendly_error("Phân đoạn văn bản", PermissionError("Security Violation [pathsec.open]: refusing multiply-linked file"))
    assert "Lỗi ở bước [Phân đoạn văn bản]" in msg
    assert "quyền truy cập tập tin" in msg

    # Corrupted PDF
    msg = format_user_friendly_error("Đọc file PDF", Exception("FileDataError: cannot open corrupted stream"))
    assert "Lỗi ở bước [Đọc file PDF]" in msg
    assert "File PDF bị hỏng" in msg
