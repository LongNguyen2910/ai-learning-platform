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


def test_token_aware_batching_splits_by_token_budget(vector_service, tmp_path, monkeypatch):
    """Verifies batches are also bounded by EMBEDDING_MAX_TOKENS_PER_BATCH."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 50)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_TOKENS_PER_BATCH", 120)
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(settings, "EMBEDDING_TPM_LIMIT", 0)

    pages_meta = []
    for i in range(1, 5):
        page_file = tmp_path / f"tok_page_{i}.md"
        # ~350 chars -> ~100 estimated tokens each -> 120 token budget allows 1 per batch
        page_file.write_text(f"Trang {i}: " + ("kiến thức học máy " * 18), encoding="utf-8")
        pages_meta.append(
            ParsedPageMetadata(
                page_number=i,
                has_formula=False,
                has_image=False,
                char_count=350,
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

    total = vector_service.index_document_pages("doc_tok_budget", pages_meta)
    assert total == 4
    assert len(insert_calls) == 4
    assert all(c == 1 for c in insert_calls)


def test_sliding_window_rate_limiter_throttles_when_tpm_exceeded(monkeypatch):
    """Verifies _SlidingWindowRateLimiter sleeps when adding tokens would exceed TPM limit."""
    import app.modules.documents.vector_service as vs_mod

    limiter = vs_mod._SlidingWindowRateLimiter(window_seconds=60.0)
    clock = {"now": 100.0}
    sleeps = []

    def fake_monotonic():
        return clock["now"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(vs_mod.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(vs_mod.time, "sleep", fake_sleep)

    # First batch of 15k tokens under 20k TPM -> immediate
    waited1 = limiter.acquire(tokens=15000, tpm_limit=20000, rpm_limit=80)
    assert waited1 == 0.0

    # Second batch of 10k tokens at t=101s would reach 25k > 20k -> must wait ~59.5s
    clock["now"] = 101.0
    waited2 = limiter.acquire(tokens=10000, tpm_limit=20000, rpm_limit=80)
    assert waited2 >= 59.0
    assert len(sleeps) == 1


def test_index_document_pages_resumes_skipping_existing_chunks(vector_service, tmp_path, monkeypatch):
    """Verifies partial progress is preserved on 429 failure and resumed without re-embedding done chunks."""
    from app.core.config import settings
    from llama_index.core.indices.vector_store import VectorStoreIndex

    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 2)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_TOKENS_PER_BATCH", 8000)
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_RETRIES", 1)
    monkeypatch.setattr(settings, "EMBEDDING_TPM_LIMIT", 0)

    pages_meta = []
    for i in range(1, 5):
        page_file = tmp_path / f"resume_page_{i}.md"
        page_file.write_text(f"Nội dung trang {i} cho kiểm thử resume.", encoding="utf-8")
        pages_meta.append(
            ParsedPageMetadata(
                page_number=i,
                has_formula=False,
                has_image=False,
                char_count=40,
                file_path=str(page_file),
            )
        )

    original_insert = VectorStoreIndex.insert_nodes
    state = {"calls": [], "fail_second": True}

    def flaky_insert(self, nodes, **kwargs):
        state["calls"].append(len(nodes))
        if state["fail_second"] and len(state["calls"]) == 2:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return original_insert(self, nodes, **kwargs)

    monkeypatch.setattr(VectorStoreIndex, "insert_nodes", flaky_insert)

    # First run: batch 1 (2 nodes) succeeds, batch 2 (2 nodes) fails
    with pytest.raises(RuntimeError, match="429"):
        vector_service.index_document_pages("doc_resume_idx", pages_meta)

    assert state["calls"] == [2, 2]

    # Second run: batch 1 is already in Qdrant, only remaining 2 nodes are indexed
    state["calls"].clear()
    state["fail_second"] = False
    total = vector_service.index_document_pages("doc_resume_idx", pages_meta)
    assert total == 4
    assert state["calls"] == [2]


def test_index_document_pages_fails_fast_on_hard_daily_quota(vector_service, tmp_path, monkeypatch):
    """Verifies daily/billing quota exhaustion does not sleep or retry."""
    from app.core.config import settings
    import app.modules.documents.vector_service as vs_mod
    from llama_index.core.indices.vector_store import VectorStoreIndex

    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 5)
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_RETRIES", 5)
    monkeypatch.setattr(settings, "EMBEDDING_TPM_LIMIT", 0)

    page_file = tmp_path / "daily_quota.md"
    page_file.write_text("Nội dung test hard daily quota.", encoding="utf-8")
    pages_meta = [
        ParsedPageMetadata(
            page_number=1,
            has_formula=False,
            has_image=False,
            char_count=30,
            file_path=str(page_file),
        )
    ]

    attempts = {"count": 0}
    sleep_calls = []

    def daily_fail_insert(self, nodes, **kwargs):
        attempts["count"] += 1
        raise RuntimeError("429 Quota exceeded for metric embed_content per day. Check your plan and billing.")

    monkeypatch.setattr(vs_mod.time, "sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(VectorStoreIndex, "insert_nodes", daily_fail_insert)

    with pytest.raises(RuntimeError, match="per day"):
        vector_service.index_document_pages("doc_daily_fail", pages_meta)

    assert attempts["count"] == 1
    assert sleep_calls == []


def test_index_document_pages_respects_retry_after_delay(vector_service, tmp_path, monkeypatch):
    """Verifies retry delay parsed from Google API error message is respected."""
    from app.core.config import settings
    import app.modules.documents.vector_service as vs_mod
    from llama_index.core.indices.vector_store import VectorStoreIndex

    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 5)
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_RETRIES", 3)
    monkeypatch.setattr(settings, "EMBEDDING_TPM_LIMIT", 0)

    page_file = tmp_path / "retry_after.md"
    page_file.write_text("Nội dung test retryDelay parsing.", encoding="utf-8")
    pages_meta = [
        ParsedPageMetadata(
            page_number=1,
            has_formula=False,
            has_image=False,
            char_count=30,
            file_path=str(page_file),
        )
    ]

    original_insert = VectorStoreIndex.insert_nodes
    attempts = {"count": 0}
    sleep_calls = []

    def flaky_insert(self, nodes, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 42.5s.")
        return original_insert(self, nodes, **kwargs)

    monkeypatch.setattr(vs_mod.time, "sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(VectorStoreIndex, "insert_nodes", flaky_insert)

    total = vector_service.index_document_pages("doc_retry_after", pages_meta)
    assert total == 1
    assert attempts["count"] == 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 43.5


def test_index_document_pages_retries_google_tpm_error_with_billing_boilerplate(
    vector_service, tmp_path, monkeypatch
):
    """Verifies Google's per-minute 429 message containing 'plan and billing details' is retried, not treated as hard daily quota."""
    from app.core.config import settings
    import app.modules.documents.vector_service as vs_mod
    from llama_index.core.indices.vector_store import VectorStoreIndex

    monkeypatch.setattr(settings, "EMBEDDING_BATCH_SIZE", 5)
    monkeypatch.setattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(settings, "EMBEDDING_MAX_RETRIES", 3)
    monkeypatch.setattr(settings, "EMBEDDING_TPM_LIMIT", 0)

    page_file = tmp_path / "tpm_boilerplate.md"
    page_file.write_text("Nội dung test lỗi TPM của Google.", encoding="utf-8")
    pages_meta = [
        ParsedPageMetadata(
            page_number=1,
            has_formula=False,
            has_image=False,
            char_count=35,
            file_path=str(page_file),
        )
    ]

    original_insert = VectorStoreIndex.insert_nodes
    attempts = {"count": 0}
    sleep_calls = []

    google_tpm_msg = (
        "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
        "'You exceeded your current quota, please check your plan and billing details. "
        "Embed content tokens per minute limit exceeded on Free Tier. "
        "Please retry in 33.714717229s.'}}"
    )

    def flaky_insert(self, nodes, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError(google_tpm_msg)
        return original_insert(self, nodes, **kwargs)

    monkeypatch.setattr(vs_mod.time, "sleep", lambda s: sleep_calls.append(s))
    monkeypatch.setattr(VectorStoreIndex, "insert_nodes", flaky_insert)

    total = vector_service.index_document_pages("doc_tpm_boilerplate", pages_meta)
    assert total == 1
    assert attempts["count"] == 2
    assert len(sleep_calls) == 1
    assert sleep_calls[0] >= 34.7
