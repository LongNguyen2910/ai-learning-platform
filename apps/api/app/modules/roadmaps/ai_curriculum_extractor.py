import logging
from pathlib import Path

from google import genai
from google.genai import types

from app.core.config import settings
from app.modules.roadmaps.exceptions import CurriculumExtractionFailedException
from app.modules.roadmaps.schemas import (
    RawChapterOutline,
    RawCurriculumOutline,
    RawStudyTopic,
)

logger = logging.getLogger(__name__)

CURRICULUM_EXTRACTION_SYSTEM_PROMPT = """Bạn là một chuyên gia sư phạm và phân tích giáo trình học thuật.
Nhiệm vụ của bạn là phân tích tài liệu học liệu và mục tiêu của người học để xây dựng cấu trúc mục lục phân cấp chuẩn gồm các Chương (Chapters) và các Chủ đề/Bài học chi tiết (Topics).

QUY TẮC BẮT BUỘC:
1. Xác định chính xác phạm vi trang (target_page_start, target_page_end) cho từng chương và từng chủ đề dựa trên mục lục hoặc nội dung văn bản.
2. Với mỗi chủ đề, đánh giá độ phức tạp (complexity_level: 1 = Dễ/Định nghĩa, 2 = Trung bình/Ứng dụng, 3 = Phức tạp/Toán cao cấp).
3. Đánh dấu is_core: true nếu kiến thức đó là trọng tâm bắt buộc để đạt được mục tiêu học tập, false nếu là nội dung tham khảo thêm/mở rộng.
"""


class AICurriculumExtractor:
    """Interacts with Gemini to extract structured curriculum outlines from documents."""

    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    async def extract_outline(
        self,
        doc_dir: Path,
        total_pages: int,
        title: str,
        study_goal: str | None = None,
    ) -> RawCurriculumOutline:
        """Extracts structured curriculum using Gemini Structured Outputs."""
        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not set. Generating fallback outline.")
            return self._generate_fallback_outline(title, total_pages)

        content_excerpt = self._read_document_excerpt(doc_dir)
        user_prompt = (
            f"Tài liệu: {title}\n"
            f"Tổng số trang: {total_pages}\n"
            f"Mục tiêu người học: {study_goal or 'Nắm vững kiến thức toàn diện'}\n\n"
            f"Dưới đây là phần mở đầu/mục lục trích xuất từ tài liệu:\n{content_excerpt}"
        )

        try:
            response = await self.client.aio.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=CURRICULUM_EXTRACTION_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=RawCurriculumOutline,
                    temperature=0.2,
                ),
            )
            parsed_outline = getattr(response, "parsed", None)
            if isinstance(parsed_outline, RawCurriculumOutline):
                return parsed_outline

            raise CurriculumExtractionFailedException("Gemini returned invalid schema.")
        except Exception as exc:
            logger.error("Curriculum extraction failed: %s. Using fallback.", exc)
            return self._generate_fallback_outline(title, total_pages)

    def _read_document_excerpt(self, doc_dir: Path, max_chars: int = 12000) -> str:
        """Reads first section of parsed markdown document to capture Table of Contents."""
        full_doc_path = doc_dir / "full_document.md"
        if not full_doc_path.exists():
            return "Không tìm thấy nội dung chi tiết full_document.md"

        try:
            with open(full_doc_path, "r", encoding="utf-8") as f:
                return f.read(max_chars)
        except Exception as err:
            logger.warning("Error reading document excerpt: %s", err)
            return ""

    def _generate_fallback_outline(
        self, title: str, total_pages: int
    ) -> RawCurriculumOutline:
        """Generates a deterministic proportional syllabus when API is unavailable."""
        pages = max(1, total_pages)
        half = max(1, pages // 2)

        return RawCurriculumOutline(
            title=title,
            summary=f"Lộ trình chuẩn cho tài liệu {title} ({pages} trang)",
            chapters=[
                RawChapterOutline(
                    title="Phần 1: Kiến thức nền tảng và Lý thuyết cơ sở",
                    description="Các khái niệm và nguyên lý cốt lõi",
                    target_page_start=1,
                    target_page_end=half,
                    topics=[
                        RawStudyTopic(
                            title="Khái niệm mở đầu và Định nghĩa",
                            description="Nắm vững thuật ngữ căn bản",
                            target_page_start=1,
                            target_page_end=max(1, half // 2),
                            is_core=True,
                            complexity_level=1,
                        ),
                        RawStudyTopic(
                            title="Phương pháp tính toán và Định lý",
                            description="Các công thức và bài toán ví dụ",
                            target_page_start=max(1, half // 2) + 1,
                            target_page_end=half,
                            is_core=True,
                            complexity_level=2,
                        ),
                    ],
                ),
                RawChapterOutline(
                    title="Phần 2: Ứng dụng chuyên sâu và Luyện tập",
                    description="Các bài toán tổng hợp và chuyên đề",
                    target_page_start=min(pages, half + 1),
                    target_page_end=pages,
                    topics=[
                        RawStudyTopic(
                            title="Chuyên đề nâng cao và Bài tập",
                            description="Vận dụng giải quyết các tình huống khó",
                            target_page_start=min(pages, half + 1),
                            target_page_end=pages,
                            is_core=True,
                            complexity_level=3,
                        )
                    ],
                ),
            ],
        )
