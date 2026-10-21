from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from google.genai import errors

from app.modules.documents.vision_parser import (
    GeminiVisionParser,
    is_retryable_exception,
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
