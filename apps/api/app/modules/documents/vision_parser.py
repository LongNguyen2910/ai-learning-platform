import asyncio
import logging
import re

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import settings
from app.modules.documents.schemas import ParsedPageMetadata

logger = logging.getLogger(__name__)

GEMINI_OCR_SYSTEM_PROMPT = """Bạn là chuyên gia OCR và số hóa tài liệu học thuật kỹ thuật cao. Nhiệm vụ của bạn là bóc tách toàn bộ nội dung từ hình ảnh trang tài liệu được cung cấp sang định dạng Markdown chuẩn với độ chính xác nguyên văn 100% (High Fidelity).

YÊU CẦU BẮT BUỘC:
1. CÔNG THỨC TOÁN HỌC:
   - Toàn bộ công thức nội dòng (inline) PHẢI được bọc trong cặp dấu `$`: ví dụ `$E = mc^2$`, `$f(x) = \\int_0^1 x dx$`.
   - Toàn bộ công thức dạng khối (block/display) PHẢI được đặt trên dòng riêng và bọc trong cặp dấu `$$`:
     $$
     \\lim_{x \\to 0} \\frac{\\sin x}{x} = 1
     $$
   - Chuẩn hóa toàn bộ ký hiệu toán về mã LaTeX chuẩn (dùng \\frac, \\sum, \\int, \\alpha, \\beta...). Tuyệt đối không dùng ký tự Unicode rời rạc thay cho công thức toán.

2. HÌNH ẢNH, SƠ ĐỒ & ĐỒ THỊ:
   - Với mỗi sơ đồ, hình vẽ, đồ thị xuất hiện trên trang, hãy tạo một khối mô tả riêng theo đúng định dạng:
     [Hình vẽ trang {page_number}: <Mô tả chi tiết nội dung, các trục tọa độ, xu hướng dữ liệu hoặc ý nghĩa kỹ thuật của sơ đồ>]

3. ĐỘ NGUYÊN VĂN (FIDELITY):
   - Giữ nguyên toàn bộ cấu trúc tiêu đề (#, ##, ###), danh sách gạch đầu dòng, bảng biểu (Markdown Table).
   - Tuyệt đối KHÔNG tự ý tóm tắt, KHÔNG diễn giải lại, KHÔNG thêm lời chào hay ghi chú ngoài lề. Chỉ trả về nội dung Markdown thuần túy.
"""


def clean_markdown_fences(text: str) -> str:
    """Strip outermost markdown code fence wrappers if the LLM output wrapped everything in ```markdown."""
    stripped = text.strip()
    match = re.match(r"^```(?:markdown)?\s*\n(.*)\n```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def is_retryable_exception(exc: Exception) -> bool:
    """Determines whether an exception is transient (network/rate limit/server) or a fatal client error.

    Returns:
        bool: True if retryable, False if fatal (e.g. invalid API key, 400 Bad Request, 401, 403).
    """
    if isinstance(exc, errors.ClientError):
        # 429 Too Many Requests / Resource Exhausted is retryable
        return exc.code == 429

    if isinstance(exc, errors.ServerError):
        # 5xx Server errors are transient and retryable
        return True

    if isinstance(exc, errors.APIError):
        return bool(exc.code == 429 or (exc.code is not None and 500 <= exc.code < 600))

    # Network / transport / timeout errors are transient
    if isinstance(
        exc,
        (TimeoutError, ConnectionError, httpx.TransportError, httpx.TimeoutException),
    ):
        return True

    # Fallback inspection for wrapped errors or custom exception strings
    err_str = str(exc).lower()
    # Explicit fatal keywords
    if any(
        k in err_str
        for k in (
            "api_key_invalid",
            "invalid_argument",
            "permission_denied",
            "unauthenticated",
            "not_found",
        )
    ):
        return False

    # Transient keywords
    return any(
        k in err_str
        for k in (
            "429",
            "resource_exhausted",
            "quota",
            "too many requests",
            "rate limit",
        )
    )


class GeminiVisionParser:
    """Handles calling Gemini 1.5 Flash Vision to parse PDF page images into high-fidelity Markdown."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        concurrency: int | None = None,
    ):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL
        self.concurrency = concurrency or settings.INGESTION_CONCURRENCY
        self.semaphore = asyncio.Semaphore(self.concurrency)
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not configured in settings or environment."
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    async def parse_page_image(
        self,
        image_bytes: bytes,
        page_number: int,
        max_retries: int = 3,
        initial_backoff: float = 2.0,
    ) -> tuple[str, ParsedPageMetadata]:
        """Parses a single page image bytes with bounded concurrency and exponential backoff retry.

        Returns:
            Tuple of (page_markdown_content, ParsedPageMetadata)
        """
        system_instruction = GEMINI_OCR_SYSTEM_PROMPT.replace(
            "{page_number}", str(page_number)
        )
        user_prompt = f"Bóc tách trang {page_number} sang Markdown chuẩn KaTeX/LaTeX và caption hình vẽ theo hướng dẫn."

        async with self.semaphore:
            last_exception: Exception | None = None
            delay = initial_backoff

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        "Processing page %d with Gemini Vision (Attempt %d/%d)...",
                        page_number,
                        attempt,
                        max_retries,
                    )
                    image_part = types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/png",
                    )

                    config = types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.1,
                    )

                    response = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=[image_part, user_prompt],
                        config=config,
                    )

                    raw_text = response.text or ""
                    markdown_content = clean_markdown_fences(raw_text)

                    # Extract metadata flags
                    has_formula = bool(
                        re.search(r"(?<!\\)\$.+?(?<!\\)\$", markdown_content, re.DOTALL)
                    )
                    has_image = bool(
                        re.search(r"\[Hình vẽ trang \d+:", markdown_content)
                    )

                    metadata = ParsedPageMetadata(
                        page_number=page_number,
                        has_formula=has_formula,
                        has_image=has_image,
                        char_count=len(markdown_content),
                        file_path="",  # Will be populated by service when saved
                    )

                    return markdown_content, metadata

                except Exception as exc:
                    last_exception = exc

                    # Fail fast immediately on non-retryable fatal errors (e.g., 400 Invalid API Key, 401, 403)
                    if not is_retryable_exception(exc):
                        logger.error(
                            "Non-retryable/fatal error on page %d (will not retry): %s",
                            page_number,
                            exc,
                        )
                        raise RuntimeError(
                            f"Fatal error parsing page {page_number}: {exc}"
                        ) from exc

                    error_str = str(exc).lower()
                    is_rate_limit = (
                        "429" in error_str
                        or "quota" in error_str
                        or "resource_exhausted" in error_str
                        or (isinstance(exc, errors.APIError) and exc.code == 429)
                    )
                    log_prefix = (
                        f"Rate limit exceeded (429/Quota) on page {page_number}"
                        if is_rate_limit
                        else f"Transient error parsing page {page_number}"
                    )
                    logger.warning(
                        "%s on attempt %d/%d: %s. Backoff %.1fs...",
                        log_prefix,
                        attempt,
                        max_retries,
                        exc,
                        delay,
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
                        delay *= 2.0
                    else:
                        break

            raise RuntimeError(
                f"Failed to parse page {page_number} after {max_retries} attempts: {last_exception}"
            ) from last_exception
