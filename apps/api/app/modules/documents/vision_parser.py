import asyncio
import logging
import re

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import settings
from app.modules.documents.schemas import ParsedPageMetadata

logger = logging.getLogger(__name__)

_OCR_CORE_INSTRUCTIONS = """YÊU CẦU BẮT BUỘC:
1. CÔNG THỨC TOÁN HỌC:
   - Toàn bộ công thức nội dòng (inline) PHẢI được bọc trong cặp dấu `$`: ví dụ `$E = mc^2$`, `$f(x) = \\int_0^1 x dx$`.
   - Toàn bộ công thức dạng khối (block/display) PHẢI được đặt trên dòng riêng và bọc trong cặp dấu `$$`:
     $$
     \\lim_{x \\to 0} \\frac{\\sin x}{x} = 1
     $$
   - Chuẩn hóa toàn bộ ký hiệu toán về mã LaTeX chuẩn (dùng \\frac, \\sum, \\int, \\alpha, \\beta...). Tuyệt đối không dùng ký tự Unicode rời rạc thay cho công thức toán.

2. HÌNH ẢNH, SƠ ĐỒ & ĐỒ THỊ:
   - Với mỗi sơ đồ, hình vẽ, đồ thị xuất hiện trên trang, hãy tạo một khối mô tả riêng theo đúng định dạng:
     [Hình vẽ trang {page_placeholder}: <Mô tả chi tiết nội dung, các trục tọa độ, xu hướng dữ liệu hoặc ý nghĩa kỹ thuật của sơ đồ>]

3. ĐỘ NGUYÊN VĂN (FIDELITY):
   - Giữ nguyên toàn bộ cấu trúc tiêu đề (#, ##, ###), danh sách gạch đầu dòng, bảng biểu (Markdown Table).
   - Tuyệt đối KHÔNG tự ý tóm tắt, KHÔNG diễn giải lại, KHÔNG thêm lời chào hay ghi chú ngoài lề. Chỉ trả về nội dung Markdown thuần túy."""

GEMINI_OCR_SYSTEM_PROMPT = f"""Bạn là chuyên gia OCR và số hóa tài liệu học thuật kỹ thuật cao. Nhiệm vụ của bạn là bóc tách toàn bộ nội dung từ hình ảnh trang tài liệu được cung cấp sang định dạng Markdown chuẩn với độ chính xác nguyên văn 100% (High Fidelity).

{_OCR_CORE_INSTRUCTIONS.replace("{page_placeholder}", "{page_number}")}
"""

GEMINI_OCR_BATCH_SYSTEM_PROMPT = f"""Bạn là chuyên gia OCR và số hóa tài liệu học thuật kỹ thuật cao. Nhiệm vụ của bạn là bóc tách toàn bộ nội dung từ các hình ảnh trang tài liệu được cung cấp sang định dạng Markdown chuẩn với độ chính xác nguyên văn 100% (High Fidelity).

QUY TẮC BẮT BUỘC VỀ PHÂN TÁCH TRANG:
- Mỗi khi bắt đầu bóc tách một trang mới, bạn PHẢI in ra một thẻ phân tách duy nhất trên một dòng riêng:
<!-- PAGE_BREAK: {{số_trang}} -->
Ví dụ:
<!-- PAGE_BREAK: 1 -->
(Nội dung nguyên văn trang 1)

<!-- PAGE_BREAK: 2 -->
(Nội dung nguyên văn trang 2)

{_OCR_CORE_INSTRUCTIONS.replace("{page_placeholder}", "{số_trang}")}
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
        bool: True if retryable, False if fatal (e.g. invalid API key, 400 Bad Request, 401, 403, or hard daily quota exhausted).
    """
    while hasattr(exc, "exceptions") and exc.exceptions:
        exc = exc.exceptions[0]

    err_str = str(exc).lower()

    # Explicit fatal keywords (including Hard Daily/Billing Quota exhaustion)
    if any(
        k in err_str
        for k in (
            "api_key_invalid",
            "invalid_argument",
            "permission_denied",
            "unauthenticated",
            "not_found",
            "per day",
            "per_day",
            "per-day",
            "daily limit",
            "check your plan and billing",
            "billing account",
        )
    ):
        return False

    if isinstance(exc, errors.ClientError):
        # 429 Too Many Requests / Resource Exhausted is retryable (if not matched hard quota above)
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

    async def parse_page_images_batch(
        self,
        pages: list[tuple[int, bytes]],
        max_retries: int = 3,
        initial_backoff: float = 2.0,
    ) -> dict[int, tuple[str, ParsedPageMetadata]]:
        """Parses a batch of page images in a single Gemini Vision API call.

        Falls back to parsing individual pages if the model response does not cleanly split all pages.

        Args:
            pages: List of (page_number, png_bytes) tuples in the batch.
            max_retries: Maximum retries on transient errors.
            initial_backoff: Initial backoff delay in seconds.

        Returns:
            Dict mapping page_number to (page_markdown_content, ParsedPageMetadata).
        """
        if not pages:
            return {}

        if len(pages) == 1:
            page_num, img_bytes = pages[0]
            content, meta = await self.parse_page_image(
                img_bytes,
                page_num,
                max_retries=max_retries,
                initial_backoff=initial_backoff,
            )
            return {page_num: (content, meta)}

        expected_pages = [p[0] for p in pages]
        pages_str = ", ".join(str(p) for p in expected_pages)

        contents: list[types.Part | str] = [
            f"Dưới đây là {len(pages)} trang tài liệu (các trang: {pages_str}). "
            "Hãy bóc tách nguyên văn từng trang theo thứ tự và bắt đầu mỗi trang bằng thẻ <!-- PAGE_BREAK: {số_trang} -->:"
        ]

        for page_num, img_bytes in pages:
            contents.append(f"=== BẮT ĐẦU TRANG {page_num} ===")
            contents.append(
                types.Part.from_bytes(
                    data=img_bytes,
                    mime_type="image/png",
                )
            )

        async with self.semaphore:
            last_exception: Exception | None = None
            delay = initial_backoff
            raw_text = ""

            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        "Processing batch of %d pages (%s) with Gemini Vision (Attempt %d/%d)...",
                        len(pages),
                        pages_str,
                        attempt,
                        max_retries,
                    )
                    config = types.GenerateContentConfig(
                        system_instruction=GEMINI_OCR_BATCH_SYSTEM_PROMPT,
                        temperature=0.1,
                    )
                    response = await self.client.aio.models.generate_content(
                        model=self.model_name,
                        contents=contents,
                        config=config,
                    )
                    raw_text = response.text or ""
                    break
                except Exception as exc:
                    last_exception = exc
                    if not is_retryable_exception(exc):
                        logger.error(
                            "Non-retryable/fatal error on batch (%s): %s",
                            pages_str,
                            exc,
                        )
                        raise RuntimeError(
                            f"Fatal error parsing batch for pages {pages_str}: {exc}"
                        ) from exc

                    error_str = str(exc).lower()
                    is_rate_limit = (
                        "429" in error_str
                        or "quota" in error_str
                        or "resource_exhausted" in error_str
                        or (isinstance(exc, errors.APIError) and exc.code == 429)
                    )
                    log_prefix = (
                        f"Rate limit exceeded (429/Quota) on batch ({pages_str})"
                        if is_rate_limit
                        else f"Transient error parsing batch ({pages_str})"
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
                        raise RuntimeError(
                            f"Failed to parse batch for pages {pages_str} after {max_retries} attempts: {last_exception}"
                        ) from last_exception

        # Parse markdown response by page separator
        cleaned_text = clean_markdown_fences(raw_text)
        parts = re.split(r"<!--\s*PAGE_BREAK:\s*(\d+)\s*-->", cleaned_text)
        results: dict[int, tuple[str, ParsedPageMetadata]] = {}

        for i in range(1, len(parts), 2):
            try:
                p_num = int(parts[i])
                p_content = parts[i + 1].strip()
                if p_num in expected_pages and p_content:
                    has_formula = bool(
                        re.search(r"(?<!\\)\$.+?(?<!\\)\$", p_content, re.DOTALL)
                    )
                    has_image = bool(
                        re.search(r"\[Hình vẽ trang \d+:", p_content)
                    )
                    meta = ParsedPageMetadata(
                        page_number=p_num,
                        has_formula=has_formula,
                        has_image=has_image,
                        char_count=len(p_content),
                        file_path="",
                    )
                    results[p_num] = (p_content, meta)
            except Exception as e:
                logger.warning("Error parsing split part for page: %s", e)

        # Check for any missing pages and fallback
        missing_pages = [p for p in pages if p[0] not in results]
        if missing_pages:
            missing_nums = [p[0] for p in missing_pages]
            logger.warning(
                "Batch response missed pages %s (received: %s). Falling back to single-page parser...",
                missing_nums,
                list(results.keys()),
            )
            for m_num, m_bytes in missing_pages:
                fb_content, fb_meta = await self.parse_page_image(
                    m_bytes,
                    m_num,
                    max_retries=max_retries,
                    initial_backoff=initial_backoff,
                )
                results[m_num] = (fb_content, fb_meta)

        return results
