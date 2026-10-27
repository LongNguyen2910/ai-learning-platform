from pathlib import Path
import pytest

from app.modules.documents.schemas import DocumentMetadata, ParsedPageMetadata
from app.modules.documents.storage import DocumentStorage


def test_document_storage_save_and_load_metadata(tmp_path):
    storage = DocumentStorage(
        parsed_base_dir=tmp_path / "parsed",
        upload_base_dir=tmp_path / "uploads",
    )

    doc_id = "doc_storage_test_1"
    metadata = DocumentMetadata(
        document_id=doc_id,
        user_id="user_123",
        title="Test Document",
        file_path=str(tmp_path / "uploads" / "doc_storage_test_1.pdf"),
        file_size_kb=1024,
        total_pages=5,
        status="parsing",
    )

    storage.save_metadata(metadata)

    loaded = storage.load_metadata(doc_id)
    assert loaded is not None
    assert loaded.document_id == doc_id
    assert loaded.title == "Test Document"
    assert loaded.status == "parsing"


def test_document_storage_count_parsed_pages(tmp_path):
    storage = DocumentStorage(
        parsed_base_dir=tmp_path / "parsed",
        upload_base_dir=tmp_path / "uploads",
    )

    doc_id = "doc_storage_test_2"
    doc_dir = storage.get_document_dir(doc_id, create=True)
    pages_dir = doc_dir / "pages"

    assert storage.count_parsed_pages(doc_id) == 0

    (pages_dir / "page_1.md").write_text("# Page 1", encoding="utf-8")
    (pages_dir / "page_2.md").write_text("# Page 2", encoding="utf-8")
    (pages_dir / "page_3.md").write_text("", encoding="utf-8")  # empty not counted

    assert storage.count_parsed_pages(doc_id) == 2


def test_document_storage_get_content(tmp_path):
    storage = DocumentStorage(
        parsed_base_dir=tmp_path / "parsed",
        upload_base_dir=tmp_path / "uploads",
    )

    doc_id = "doc_storage_test_3"
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Content Test",
        file_path="dummy.pdf",
        file_size_kb=100,
        total_pages=1,
        status="ready",
    )
    storage.save_metadata(metadata)

    # Save full document
    full_path = storage.get_full_doc_path(doc_id)
    full_path.write_text("# Full Content Here", encoding="utf-8")

    content_resp = storage.get_document_content(doc_id)
    assert content_resp is not None
    assert content_resp.full_content == "# Full Content Here"


def test_document_storage_delete_files(tmp_path):
    storage = DocumentStorage(
        parsed_base_dir=tmp_path / "parsed",
        upload_base_dir=tmp_path / "uploads",
    )

    doc_id = "doc_storage_delete"
    doc_dir = storage.get_document_dir(doc_id, create=True)
    metadata = DocumentMetadata(
        document_id=doc_id,
        title="Delete Test",
        file_path="dummy.pdf",
        file_size_kb=50,
        total_pages=1,
    )
    storage.save_metadata(metadata)

    pdf_file = storage.upload_base_dir / f"{doc_id}.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    assert pdf_file.exists()
    assert doc_dir.exists()

    deleted = storage.delete_document_files(doc_id)
    assert deleted is True

    assert not pdf_file.exists()
    assert not doc_dir.exists()
