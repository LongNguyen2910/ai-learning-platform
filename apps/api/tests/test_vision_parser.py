from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from google.genai import errors

from app.modules.documents.vision_parser import (
    GeminiVisionParser,
    is_retryable_exception,
    normalize_katex_syntax,
)


def test_is_retryable_exception_fatal_client_errors():
    # 400 Invalid argument / invalid API key
    err_400 = errors.ClientError(
        400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}}
    )
    assert is_retryable_exception(err_400) is False

    # 401 Unauthorized
    err_401 = errors.ClientError(401, {"error": {"message": "Unauthenticated"}})
    assert is_retryable_exception(err_401) is False

    # 403 Forbidden
    err_403 = errors.ClientError(403, {"error": {"message": "Permission denied"}})
    assert is_retryable_exception(err_403) is False

    # 404 Not Found
    err_404 = errors.ClientError(404, {"error": {"message": "Model not found"}})
    assert is_retryable_exception(err_404) is False

    # 429 Hard Quota (Daily limit / Billing) should fail fast and NOT be retryable
    err_daily = errors.ClientError(
        429,
        {
            "error": {
                "message": "Quota exceeded for quota metric 'Queries' and limit 'Queries per day'"
            }
        },
    )
    assert is_retryable_exception(err_daily) is False

    err_billing = errors.ClientError(
        429, {"error": {"message": "Check your plan and billing details"}}
    )
    assert is_retryable_exception(err_billing) is False


def test_is_retryable_exception_transient_errors():
    # 429 Rate Limit / Quota
    err_429 = errors.ClientError(429, {"error": {"message": "Resource exhausted"}})
    assert is_retryable_exception(err_429) is True

    # 503 Server Error
    err_503 = errors.ServerError(503, {"error": {"message": "Service unavailable"}})
    assert is_retryable_exception(err_503) is True

    # Transport / Timeout errors
    assert is_retryable_exception(TimeoutError("Timed out")) is True
    assert is_retryable_exception(ConnectionError("Connection reset")) is True
    assert is_retryable_exception(httpx.TransportError("Socket closed")) is True
    assert is_retryable_exception(httpx.ReadTimeout("Read timeout")) is True


def test_is_retryable_exception_string_fallbacks():
    assert (
        is_retryable_exception(
            Exception("API_KEY_INVALID: Please pass a valid API key.")
        )
        is False
    )
    assert (
        is_retryable_exception(Exception("Quota exceeded: 429 too many requests"))
        is True
    )


@pytest.mark.asyncio
async def test_parse_page_image_fails_fast_on_invalid_api_key():
    parser = GeminiVisionParser(api_key="invalid_test_key")
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=errors.ClientError(
            400, {"error": {"message": "API key not valid."}}
        )
    )
    parser._client = mock_client

    with pytest.raises(RuntimeError) as exc_info:
        await parser.parse_page_image(
            b"fake_image_bytes", page_number=1, max_retries=3, initial_backoff=0.01
        )

    assert "Fatal error parsing page 1" in str(exc_info.value)
    # Crucial: verify generate_content was called ONLY once (no retry attempts)
    assert mock_client.aio.models.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_parse_page_image_retries_on_rate_limit():
    parser = GeminiVisionParser(api_key="valid_key")
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=errors.ClientError(
            429, {"error": {"message": "Resource exhausted"}}
        )
    )
    parser._client = mock_client

    with pytest.raises(RuntimeError) as exc_info:
        await parser.parse_page_image(
            b"fake_image_bytes", page_number=1, max_retries=3, initial_backoff=0.01
        )

    assert "Failed to parse page 1 after 3 attempts" in str(exc_info.value)
    # Verify it retried 3 times
    assert mock_client.aio.models.generate_content.call_count == 3


@pytest.mark.asyncio
async def test_parse_page_image_fails_fast_on_hard_quota():
    parser = GeminiVisionParser(api_key="valid_key")
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=errors.ClientError(
            429,
            {
                "error": {
                    "message": "Quota exceeded for quota metric 'Queries' and limit 'Queries per day'"
                }
            },
        )
    )
    parser._client = mock_client

    with pytest.raises(RuntimeError) as exc_info:
        await parser.parse_page_image(
            b"fake_image_bytes", page_number=1, max_retries=3, initial_backoff=0.01
        )

    assert "Fatal error parsing page 1" in str(exc_info.value)
    # Crucial: verify generate_content was called ONLY once (no retry attempts on hard daily quota)
    assert mock_client.aio.models.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_cancels_remaining_tasks_on_failure(tmp_path):
    from app.modules.documents.schemas import ParsedPageMetadata
    from app.modules.documents.service import IngestionService

    renderer_mock = MagicMock()
    renderer_mock.get_page_count.return_value = 5
    renderer_mock.is_page_empty.return_value = False
    renderer_mock.render_page_to_png_bytes.return_value = b"png"

    completed_pages = []

    async def mock_parse_page(image_bytes, page_number, **kwargs):
        if page_number == 1:
            raise RuntimeError("Quota exhausted 429")
        # Other pages wait; if not cancelled, they would complete and append to completed_pages
        await asyncio.sleep(0.5)
        completed_pages.append(page_number)
        return "content", ParsedPageMetadata(
            page_number=page_number,
            has_formula=False,
            has_image=False,
            char_count=7,
            file_path="",
        )

    parser_mock = MagicMock()
    parser_mock.parse_page_image = mock_parse_page

    vector_mock = MagicMock()

    service = IngestionService(
        renderer=renderer_mock,
        vision_parser=parser_mock,
        vector_service=vector_mock,
        parsed_base_dir=str(tmp_path / "parsed"),
    )

    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"%PDF dummy")

    with pytest.raises(RuntimeError) as exc_info:
        await service.run_ingestion_pipeline(
            document_id="doc-cancel-test",
            pdf_path=pdf_file,
            title="Cancel Test",
            force=True,
        )

    assert "Quota exhausted 429" in str(exc_info.value)

    # Crucial: Verify other pages were cancelled and NEVER completed
    assert completed_pages == []

    # Verify metadata was cleanly recorded as failed
    meta = service.load_metadata("doc-cancel-test")
    assert meta is not None
    assert meta.status == "failed"
    assert "Rate limit / Quota" in meta.error_message


@pytest.mark.asyncio
async def test_parse_page_images_batch_success():
    parser = GeminiVisionParser(api_key="valid_key")
    mock_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = """
<!-- PAGE_BREAK: 1 -->
# Trang 1
Công thức: $E = mc^2$

<!-- PAGE_BREAK: 2 -->
# Trang 2
[Hình vẽ trang 2: Sơ đồ kiến trúc RAG]
"""
    mock_client.aio.models.generate_content = AsyncMock(return_value=fake_response)
    parser._client = mock_client

    pages = [(1, b"page_1_png"), (2, b"page_2_png")]
    results = await parser.parse_page_images_batch(pages)

    assert len(results) == 2
    assert 1 in results and 2 in results

    p1_content, p1_meta = results[1]
    assert "Trang 1" in p1_content
    assert p1_meta.has_formula is True
    assert p1_meta.has_image is False

    p2_content, p2_meta = results[2]
    assert "Trang 2" in p2_content
    assert p2_meta.has_formula is False
    assert p2_meta.has_image is True

    # Crucial: Only 1 API call made for both pages!
    assert mock_client.aio.models.generate_content.call_count == 1


@pytest.mark.asyncio
async def test_parse_page_images_batch_fallback_on_missing_page():
    parser = GeminiVisionParser(api_key="valid_key")
    mock_client = MagicMock()

    # Batch response only returns page 1, misses page 2
    batch_response = MagicMock()
    batch_response.text = """
<!-- PAGE_BREAK: 1 -->
# Trang 1
Nội dung trang 1
"""
    # Single-page fallback response for page 2
    single_response = MagicMock()
    single_response.text = "# Trang 2 fallback"

    async def fake_generate_content(*args, **kwargs):
        # If user contents asks for both pages, it's the batch call
        contents = kwargs.get("contents", [])
        if any("trang tài liệu" in str(c) for c in contents):
            return batch_response
        return single_response

    mock_client.aio.models.generate_content = AsyncMock(side_effect=fake_generate_content)
    parser._client = mock_client

    pages = [(1, b"page_1_png"), (2, b"page_2_png")]
    results = await parser.parse_page_images_batch(pages)

    assert len(results) == 2
    assert 1 in results and 2 in results
    assert "Trang 1" in results[1][0]
    assert "Trang 2 fallback" in results[2][0]

    # Batch call (1) + Single-page fallback for page 2 (1) = 2 calls
    assert mock_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_run_ingestion_pipeline_batching_groups_pages(tmp_path, monkeypatch):
    from app.core.config import settings
    from app.modules.documents.schemas import ParsedPageMetadata
    from app.modules.documents.service import IngestionService

    monkeypatch.setattr(settings, "INGESTION_BATCH_SIZE", 3)

    renderer_mock = MagicMock()
    renderer_mock.get_page_count.return_value = 5  # 5 pages with batch size 3 -> 2 batches ([1,2,3], [4,5])
    renderer_mock.is_page_empty.return_value = False
    renderer_mock.render_page_to_png_bytes.return_value = b"dummy_png"

    batch_calls = []

    async def mock_batch(pages, **kwargs):
        batch_nums = [p[0] for p in pages]
        batch_calls.append(batch_nums)
        return {
            p[0]: (
                f"# Markdown for page {p[0]}",
                ParsedPageMetadata(
                    page_number=p[0],
                    has_formula=False,
                    has_image=False,
                    char_count=20,
                    file_path="",
                ),
            )
            for p in pages
        }

    parser_mock = MagicMock()
    parser_mock.parse_page_images_batch = mock_batch

    vector_mock = MagicMock()
    vector_mock.index_document_pages.return_value = 5

    parsed_dir = tmp_path / "parsed"
    service = IngestionService(
        renderer=renderer_mock,
        vision_parser=parser_mock,
        vector_service=vector_mock,
        parsed_base_dir=str(parsed_dir),
    )

    pdf_file = tmp_path / "document.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    meta = await service.run_ingestion_pipeline(
        document_id="batch-pipeline-doc",
        pdf_path=pdf_file,
        title="Batch Pipeline Test",
        force=True,
    )

    assert meta.status == "ready"
    assert meta.total_pages == 5

    # Verify batch calls: 5 pages split into [1, 2, 3] and [4, 5]
    assert len(batch_calls) == 2
    assert batch_calls[0] == [1, 2, 3]
    assert batch_calls[1] == [4, 5]

    # Verify all 5 individual markdown files were saved
    pages_dir = parsed_dir / "batch-pipeline-doc" / "pages"
    for i in range(1, 6):
        page_file = pages_dir / f"page_{i}.md"
        assert page_file.is_file()
        assert f"# Markdown for page {i}" in page_file.read_text(encoding="utf-8")


def test_normalize_katex_syntax():
    # Basic \eqno(4)
    raw = r"$$ Q = N \times D + D \times log_2(V). \eqno(4) $$"
    expected = r"$$ Q = N \times D + D \times log_2(V). \tag{4} $$"
    assert normalize_katex_syntax(raw) == expected

    # With space \eqno (5)
    raw_space = r"$$ Q = C \times (D + D \times log_2(V)), \eqno (5) $$"
    expected_space = r"$$ Q = C \times (D + D \times log_2(V)), \tag{5} $$"
    assert normalize_katex_syntax(raw_space) == expected_space

    # Decimal equation numbers \eqno (12.3)
    raw_dec = r"E = mc^2 \eqno (12.3)"
    assert normalize_katex_syntax(raw_dec) == r"E = mc^2 \tag{12.3}"

    # Braced variations \eqno{(6)} and \eqno{7}
    assert normalize_katex_syntax(r"a + b = c \eqno{(6)}") == r"a + b = c \tag{6}"
    assert normalize_katex_syntax(r"a + b = c \eqno{7}") == r"a + b = c \tag{7}"

    # Bare number \eqno 8
    assert normalize_katex_syntax(r"a + b = c \eqno 8") == r"a + b = c \tag{8}"

    # Left equation numbering \leqno(9)
    assert normalize_katex_syntax(r"x + y = z \leqno(9)") == r"x + y = z \tag{9}"

    # Non-math text or normal formulas without eqno remain unchanged
    normal = r"Công thức $E = mc^2$ và khối $$f(x) = \sin(x)$$"
    assert normalize_katex_syntax(normal) == normal

    # Empty string or None
    assert normalize_katex_syntax("") == ""
    assert normalize_katex_syntax(None) is None




