from dataclasses import dataclass
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
Nhiệm vụ của bạn là phân tích một hoặc nhiều tài liệu học liệu thuộc cùng một môn học và mục tiêu của người học để tổng hợp cấu trúc mục lục phân cấp thống nhất gồm các Chương (Chapters) và các Chủ đề/Bài học chi tiết (Topics).

QUY TẮC BẮT BUỘC:
1. Hợp nhất thông minh các tài liệu theo trình tự logic kiến thức của môn học.
2. Với mỗi Chương và mỗi Chủ đề, BẮT BUỘC điền đúng `document_id` (UUID của tài liệu nguồn chứa nội dung đó từ danh sách tài liệu cung cấp) và phạm vi trang (`target_page_start`, `target_page_end`) tương ứng trong tài liệu đó.
3. Với mỗi chủ đề, đánh giá độ phức tạp (complexity_level: 1 = Dễ/Định nghĩa, 2 = Trung bình/Ứng dụng, 3 = Phức tạp/Toán cao cấp).
4. Đánh dấu is_core: true nếu kiến thức đó là trọng tâm bắt buộc để đạt được mục tiêu học tập, false nếu là nội dung tham khảo thêm/mở rộng.
"""


@dataclass
class SourceDocumentInput:
    """Represents a parsed source document participating in multi-document curriculum synthesis."""

    document_id: str
    title: str
    total_pages: int
    doc_dir: Path


class AICurriculumExtractor:
    """Interacts with Gemini to extract structured curriculum outlines from one or multiple documents."""

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
        document_id: str | None = None,
    ) -> RawCurriculumOutline:
        """Extracts structured curriculum from a single document (backwards compatible)."""
        return await self.extract_multi_document_outline(
            documents=[
                SourceDocumentInput(
                    document_id=document_id or "",
                    title=title,
                    total_pages=total_pages,
                    doc_dir=doc_dir,
                )
            ],
            roadmap_title=title,
            study_goal=study_goal,
        )

    async def extract_multi_document_outline(
        self,
        documents: list[SourceDocumentInput],
        roadmap_title: str,
        study_goal: str | None = None,
        weak_topics: list[str] | None = None,
        incorrect_questions_summary: list[str] | None = None,
        iteration: int = 1,
    ) -> RawCurriculumOutline:
        """Synthesizes a unified curriculum outline across multiple documents of a subject."""
        if not documents:
            return self._generate_fallback_outline(
                roadmap_title, 1, None, weak_topics=weak_topics, iteration=iteration
            )

        if not settings.GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not set. Generating fallback outline.")
            return self._generate_multi_doc_fallback(
                documents,
                roadmap_title,
                weak_topics=weak_topics,
                iteration=iteration,
            )

        max_chars_per_doc = max(3500, 14000 // max(1, len(documents)))
        docs_context_parts: list[str] = []
        for idx, doc in enumerate(documents, start=1):
            excerpt = self._read_document_excerpt(
                doc.doc_dir, max_chars=max_chars_per_doc
            )
            docs_context_parts.append(
                f"=== TÀI LIỆU #{idx} ===\n"
                f"- document_id: {doc.document_id}\n"
                f"- Tiêu đề: {doc.title}\n"
                f"- Tổng số trang: {doc.total_pages}\n"
                f"- Trích đoạn nội dung / Mục lục:\n{excerpt}\n"
            )

        joined_docs_context = "\n\n".join(docs_context_parts)
        remediation_section = ""
        if weak_topics or incorrect_questions_summary or iteration > 1:
            weak_str = (
                ", ".join(weak_topics)
                if weak_topics
                else "Các chủ đề nâng cao và vận dụng"
            )
            wrong_q_str = (
                "\n".join(f"  * {item}" for item in incorrect_questions_summary[:10])
                if incorrect_questions_summary
                else "  * Người học đạt dưới 50% trong bài kiểm tra tổng kết."
            )
            remediation_section = (
                f"\n=== CHẾ ĐỘ HỌC LẠI CHUYÊN SÂU (ADAPTIVE REMEDIATION - LẦN #{iteration}) ===\n"
                f"Người học vừa KHÔNG ĐẠT (< 50%) bài kiểm tra tổng kết của lộ trình trước.\n"
                f"- Các chủ đề bị hổng kiến thức (Weak Topics): {weak_str}\n"
                f"- Chi tiết các phần làm sai:\n{wrong_q_str}\n"
                f"YÊU CẦU BẮT BUỘC CHO LỘ TRÌNH MỚI:\n"
                f"1. Thiết kế lộ trình DÀI HƠN và CHI TIẾT HƠN lộ trình thông thường (nhiều Chương và Chủ đề con hơn).\n"
                f"2. Tại các vùng trang/chủ đề liên quan đến '{weak_str}', hãy TÁCH NHỎ thành nhiều Topic chuyên sâu (ví dụ: Lý thuyết cốt lõi, Phân tích bản chất & các bẫy thường gặp, Bài tập vận dụng chuyên sâu).\n"
                f"3. Đặt `complexity_level = 3` và `is_core = true` cho tất cả các chủ đề thuộc phần làm sai để hệ thống phân bổ nhiều thời gian học hơn.\n\n"
            )

        user_prompt = (
            f"Tên lộ trình môn học: {roadmap_title}\n"
            f"Số lượng tài liệu nguồn: {len(documents)}\n"
            f"Mục tiêu người học: {study_goal or 'Nắm vững kiến thức toàn diện của môn học'}\n"
            f"{remediation_section}"
            f"Danh sách tài liệu thuộc môn học:\n{joined_docs_context}"
        )

        candidate_models = [
            settings.GEMINI_MODEL,
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
        ]
        unique_models = list(dict.fromkeys([m for m in candidate_models if m]))

        try:
            response = None
            last_err = None
            for model_name in unique_models:
                try:
                    response = await self.client.aio.models.generate_content(
                        model=model_name,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=CURRICULUM_EXTRACTION_SYSTEM_PROMPT,
                            response_mime_type="application/json",
                            response_schema=RawCurriculumOutline,
                            temperature=0.2,
                        ),
                    )
                    if response:
                        break
                except Exception as model_err:
                    last_err = model_err
                    if "503" in str(model_err) or "UNAVAILABLE" in str(model_err):
                        continue
                    raise model_err

            if not response and last_err:
                raise last_err

            parsed_outline = getattr(response, "parsed", None)
            if isinstance(parsed_outline, RawCurriculumOutline):
                valid_doc_ids = {d.document_id for d in documents if d.document_id}
                default_doc_id = documents[0].document_id or None
                for ch in parsed_outline.chapters:
                    if not ch.document_id or ch.document_id not in valid_doc_ids:
                        ch.document_id = default_doc_id
                    for tp in ch.topics:
                        if not tp.document_id or tp.document_id not in valid_doc_ids:
                            tp.document_id = ch.document_id or default_doc_id
                return parsed_outline

            raise CurriculumExtractionFailedException("Gemini returned invalid schema.")
        except Exception as exc:
            logger.error("Curriculum extraction failed: %s. Using fallback.", exc)
            return self._generate_multi_doc_fallback(
                documents,
                roadmap_title,
                weak_topics=weak_topics,
                iteration=iteration,
            )

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

    def _generate_multi_doc_fallback(
        self,
        documents: list[SourceDocumentInput],
        roadmap_title: str,
        weak_topics: list[str] | None = None,
        iteration: int = 1,
    ) -> RawCurriculumOutline:
        chapters: list[RawChapterOutline] = []
        for doc in documents:
            single = self._generate_fallback_outline(
                doc.title,
                doc.total_pages,
                doc.document_id or None,
                weak_topics=weak_topics,
                iteration=iteration,
            )
            for ch in single.chapters:
                if len(documents) > 1:
                    ch.title = f"[{doc.title}] {ch.title}"
                chapters.append(ch)

        return RawCurriculumOutline(
            title=roadmap_title,
            summary=f"Lộ trình tổng hợp từ {len(documents)} tài liệu",
            chapters=chapters,
        )

    def _generate_fallback_outline(
        self,
        title: str,
        total_pages: int,
        document_id: str | None = None,
        weak_topics: list[str] | None = None,
        iteration: int = 1,
    ) -> RawCurriculumOutline:
        """Generates a deterministic proportional syllabus when API is unavailable."""
        pages = max(1, total_pages)
        half = max(1, pages // 2)

        chapters = [
            RawChapterOutline(
                title="Phần 1: Kiến thức nền tảng và Lý thuyết cơ sở",
                description="Các khái niệm và nguyên lý cốt lõi",
                document_id=document_id,
                target_page_start=1,
                target_page_end=half,
                topics=[
                    RawStudyTopic(
                        title="Khái niệm mở đầu và Định nghĩa",
                        description="Nắm vững thuật ngữ căn bản",
                        document_id=document_id,
                        target_page_start=1,
                        target_page_end=max(1, half // 2),
                        is_core=True,
                        complexity_level=1 if iteration == 1 else 2,
                    ),
                    RawStudyTopic(
                        title="Phương pháp tính toán và Định lý",
                        description="Các công thức và bài toán ví dụ",
                        document_id=document_id,
                        target_page_start=max(1, half // 2) + 1,
                        target_page_end=half,
                        is_core=True,
                        complexity_level=2 if iteration == 1 else 3,
                    ),
                ],
            ),
            RawChapterOutline(
                title="Phần 2: Ứng dụng chuyên sâu và Luyện tập",
                description="Các bài toán tổng hợp và chuyên đề",
                document_id=document_id,
                target_page_start=min(pages, half + 1),
                target_page_end=pages,
                topics=[
                    RawStudyTopic(
                        title="Chuyên đề nâng cao và Bài tập",
                        description="Vận dụng giải quyết các tình huống khó",
                        document_id=document_id,
                        target_page_start=min(pages, half + 1),
                        target_page_end=pages,
                        is_core=True,
                        complexity_level=3,
                    )
                ],
            ),
        ]

        if weak_topics or iteration > 1:
            remedial_topics: list[RawStudyTopic] = []
            focus_items = weak_topics or ["Tổng hợp & Khắc phục lỗi sai trọng tâm"]
            for idx, wt in enumerate(focus_items, start=1):
                remedial_topics.append(
                    RawStudyTopic(
                        title=f"Ôn tập chuyên sâu #{idx}: {wt} (Lý thuyết & Bản chất)",
                        description=f"Đào sâu lại phần kiến thức chưa đạt trong bài kiểm tra: {wt}",
                        document_id=document_id,
                        target_page_start=1,
                        target_page_end=pages,
                        is_core=True,
                        complexity_level=3,
                    )
                )
                remedial_topics.append(
                    RawStudyTopic(
                        title=f"Thực hành khắc phục lỗi sai #{idx}: {wt} (Vận dụng)",
                        description=f"Luyện tập phân tích các câu hỏi dễ nhầm lẫn về {wt}",
                        document_id=document_id,
                        target_page_start=1,
                        target_page_end=pages,
                        is_core=True,
                        complexity_level=3,
                    )
                )

            chapters.append(
                RawChapterOutline(
                    title=f"Phần 3: Chuyên đề Củng cố & Khắc phục Lỗ hổng (Lần #{iteration})",
                    description="Chương trình đào sâu tập trung vào các phần làm sai ở bài kiểm tra trước",
                    document_id=document_id,
                    target_page_start=1,
                    target_page_end=pages,
                    topics=remedial_topics,
                )
            )

        return RawCurriculumOutline(
            title=title,
            summary=f"Lộ trình chuẩn cho tài liệu {title} ({pages} trang)",
            chapters=chapters,
        )
