import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from llama_index.core.embeddings import MockEmbedding
from qdrant_client import QdrantClient

from app.modules.documents.renderer import PDFPageRenderer
from app.modules.documents.schemas import ParsedPageMetadata
from app.modules.documents.service import IngestionService
from app.modules.documents.vector_service import DocumentVectorService
from app.modules.documents.vision_parser import GeminiVisionParser


@pytest.fixture
def mock_embed_model():
    return MockEmbedding(embed_dim=3072)


@pytest.fixture
def memory_qdrant_client():
    return QdrantClient(":memory:")


@pytest.fixture
def vector_service(memory_qdrant_client, mock_embed_model):
    return DocumentVectorService(
        qdrant_client=memory_qdrant_client,
        embed_model=mock_embed_model,
        collection_name="test_learning_chunks",
        chunk_size=100,
        chunk_overlap=20,
    )


def test_ensure_collection_ready(vector_service, memory_qdrant_client):
    assert not memory_qdrant_client.collection_exists("test_learning_chunks")

    vector_service.ensure_collection_ready()

    assert memory_qdrant_client.collection_exists("test_learning_chunks")


def test_ensure_collection_ready_dimension_mismatch_raises_error(
    vector_service, memory_qdrant_client
):
    vector_service.ensure_collection_ready()
    # Attempting to re-ensure with a different vector size must raise ValueError without deleting collection
    vector_service.vector_size = 1536
    with pytest.raises(ValueError, match="dimension mismatch"):
        vector_service.ensure_collection_ready()
    # Collection still exists
    assert memory_qdrant_client.collection_exists("test_learning_chunks")


def test_index_and_retrieve_document_pages(vector_service, tmp_path):
    # Setup temporary page markdown files
    page1_file = tmp_path / "page_1.md"
    page1_file.write_text(
        "Định lý Pythagore: Trong tam giác vuông, bình phương cạnh huyền bằng tổng bình phương hai cạnh góc vuông: $$a^2 + b^2 = c^2$$.",
        encoding="utf-8",
    )

    page2_file = tmp_path / "page_2.md"
    page2_file.write_text(
        "Định luật Newton 2: Gia tốc của một vật tỉ lệ thuận với lực tác dụng lên nó: $$F = ma$$.",
        encoding="utf-8",
    )

    # Empty page placeholder
    page3_file = tmp_path / "page_3.md"
    page3_file.write_text("<!-- Trang 3 để trống -->", encoding="utf-8")

    pages_meta = [
        ParsedPageMetadata(
            page_number=1,
            has_formula=True,
            has_image=False,
            char_count=120,
            file_path=str(page1_file),
        ),
        ParsedPageMetadata(
            page_number=2,
            has_formula=True,
            has_image=False,
            char_count=90,
            file_path=str(page2_file),
        ),
        ParsedPageMetadata(
            page_number=3,
            has_formula=False,
            has_image=False,
            char_count=0,
            file_path=str(page3_file),
        ),
    ]

    doc_id = "doc_test_123"
    total_indexed = vector_service.index_document_pages(doc_id, pages_meta)

    # Should have indexed chunks for pages 1 and 2, but skipped page 3
    assert total_indexed >= 2

    # Verify retrieval with doc_id filter
    retriever = vector_service.get_retriever(document_id=doc_id, similarity_top_k=5)
    results = retriever.retrieve("Pythagore")
    assert len(results) > 0
    assert results[0].metadata["doc_id"] == doc_id
    assert results[0].metadata["page_number"] in [1, 2]

    # Verify retrieval with both doc_id and page_number filter
    page1_retriever = vector_service.get_retriever(
        document_id=doc_id, page_number=1, similarity_top_k=2
    )
    p1_results = page1_retriever.retrieve("công thức")
    assert len(p1_results) > 0
    for node in p1_results:
        assert node.metadata["doc_id"] == doc_id
        assert node.metadata["page_number"] == 1


def test_delete_document_vectors(vector_service, tmp_path):
    page_file = tmp_path / "page_1.md"
    page_file.write_text("Nội dung thử nghiệm cho việc xóa.", encoding="utf-8")

    pages_meta = [
        ParsedPageMetadata(
            page_number=1,
            has_formula=False,
            has_image=False,
            char_count=50,
            file_path=str(page_file),
        )
    ]

    doc_id = "doc_to_delete"
    vector_service.index_document_pages(doc_id, pages_meta)

    # Verify indexed
    retriever = vector_service.get_retriever(document_id=doc_id)
    assert len(retriever.retrieve("thử nghiệm")) > 0

    # Delete vectors
    vector_service.delete_document_vectors(doc_id)

    # Verify gone
    retriever_after = vector_service.get_retriever(document_id=doc_id)
    assert len(retriever_after.retrieve("thử nghiệm")) == 0


@pytest.mark.asyncio
async def test_ingestion_service_vector_integration():
    with tempfile.TemporaryDirectory() as temp_dir:
        mock_renderer = MagicMock(spec=PDFPageRenderer)
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.is_page_empty.return_value = False
        mock_renderer.render_page_to_png_bytes.return_value = b"fake-png"

        mock_parser = MagicMock(spec=GeminiVisionParser)

        async def fake_parse(*args, **kwargs):
            return "Nội dung trang 1 về Toán.", ParsedPageMetadata(
                page_number=1,
                has_formula=False,
                has_image=False,
                char_count=25,
                file_path="",
            )

        mock_parser.parse_page_image.side_effect = fake_parse

        mock_vector_service = MagicMock(spec=DocumentVectorService)
        mock_vector_service.index_document_pages.return_value = 1

        service = IngestionService(
            renderer=mock_renderer,
            vision_parser=mock_parser,
            vector_service=mock_vector_service,
            parsed_base_dir=temp_dir,
        )

        doc_id = "doc_ingest_test"
        dummy_pdf = Path(temp_dir) / f"{doc_id}.pdf"
        dummy_pdf.write_bytes(b"%PDF-1.4 dummy")

        metadata = await service.run_ingestion_pipeline(
            document_id=doc_id,
            pdf_path=dummy_pdf,
            title="Tài liệu Test",
        )

        # Status must finish at 'ready'
        assert metadata.status == "ready"
        mock_vector_service.index_document_pages.assert_called_once()

        # Delete document calls delete_document_vectors
        assert service.delete_document(doc_id) is True
        mock_vector_service.delete_document_vectors.assert_called_once_with(doc_id)


@pytest.mark.asyncio
async def test_ingestion_service_smart_resume_skips_gemini_vision():
    with tempfile.TemporaryDirectory() as temp_dir:
        mock_renderer = MagicMock(spec=PDFPageRenderer)
        mock_renderer.get_page_count.return_value = 1
        mock_renderer.is_page_empty.return_value = False

        mock_parser = MagicMock(spec=GeminiVisionParser)
        mock_vector_service = MagicMock(spec=DocumentVectorService)
        mock_vector_service.index_document_pages.return_value = 1

        service = IngestionService(
            renderer=mock_renderer,
            vision_parser=mock_parser,
            vector_service=mock_vector_service,
            parsed_base_dir=temp_dir,
        )

        doc_id = "doc_resume_test"
        dummy_pdf = Path(temp_dir) / f"{doc_id}.pdf"
        dummy_pdf.write_bytes(b"%PDF-1.4 dummy")

        # Pre-create the parsed page file as if previously parsed before vector failure
        pages_dir = service.get_document_dir(doc_id, create=True) / "pages"
        cached_page = pages_dir / "page_1.md"
        cached_page.write_text("Nội dung đã parse từ trước.", encoding="utf-8")

        metadata = await service.run_ingestion_pipeline(
            document_id=doc_id,
            pdf_path=dummy_pdf,
            title="Resume Test",
            force=False,
        )

        assert metadata.status == "ready"
        # Gemini vision parser should NOT be called because page was cached!
        mock_parser.parse_page_image.assert_not_called()
        # Vector service should still be called to index the document
        mock_vector_service.index_document_pages.assert_called_once()


def test_index_document_pages_batching(vector_service, tmp_path, monkeypatch):
    """Verifies that large number of nodes are processed in batches rather than all-at-once."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 2)
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 0.0)

    # Create 5 page files
    pages_meta = []
    for i in range(1, 6):
        page_file = tmp_path / f"batch_page_{i}.md"
        page_file.write_text(f"Nội dung trang số {i} với các thông tin chi tiết.", encoding="utf-8")
        pages_meta.append(
            ParsedPageMetadata(
                page_number=i,
                has_formula=False,
                has_image=False,
                char_count=50,
                file_path=str(page_file),
            )
        )

    insert_calls = []
    from llama_index.core.indices.vector_store import VectorStoreIndex

    original_insert = VectorStoreIndex.insert_nodes

    def tracking_insert(self, nodes, **kwargs):
        insert_calls.append(len(nodes))
        return original_insert(self, nodes, **kwargs)

    monkeypatch.setattr(VectorStoreIndex, "insert_nodes", tracking_insert)

    total = vector_service.index_document_pages("doc_batch_test", pages_meta)
    assert total == 5
    # 5 nodes with batch_size=2 should be 2 + 2 + 1 = 3 batches
    assert insert_calls == [2, 2, 1]


def test_index_document_pages_retry_on_429(vector_service, tmp_path, monkeypatch):
    """Verifies that 429 rate limit errors trigger backoff and retry successfully."""
    from app.core.config import settings
    import app.modules.documents.vector_service as vs_mod

    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 5)
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_RETRIES", 3)

    page_file = tmp_path / "page_retry.md"
    page_file.write_text("Nội dung cần test retry khi gặp lỗi hạn ngạch 429.", encoding="utf-8")
    pages_meta = [
        ParsedPageMetadata(
            page_number=1,
            has_formula=False,
            has_image=False,
            char_count=50,
            file_path=str(page_file),
        )
    ]

    attempts = {"count": 0}
    from llama_index.core.indices.vector_store import VectorStoreIndex

    original_insert = VectorStoreIndex.insert_nodes

    def flaky_insert(self, nodes, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("429 Resource Exhausted: Rate limit exceeded")
        return original_insert(self, nodes, **kwargs)

    sleep_calls = []
    monkeypatch.setattr(vs_mod.time, "sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(VectorStoreIndex, "insert_nodes", flaky_insert)

    total = vector_service.index_document_pages("doc_retry_test", pages_meta)
    assert total == 1
    assert attempts["count"] == 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] > 0
