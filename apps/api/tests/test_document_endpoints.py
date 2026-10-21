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

    response = client.post(f"/api/v1/documents/{doc_id}/retry")
    assert response.status_code == 409
    assert "currently being processed" in response.json()["detail"]


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

    response = client.post(f"/api/v1/documents/{doc_id}/retry")
    assert response.status_code == 409
    assert "currently being processed (indexing)" in response.json()["detail"]


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
