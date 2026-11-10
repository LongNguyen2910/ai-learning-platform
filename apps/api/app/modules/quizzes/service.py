from datetime import UTC, datetime
import logging
import uuid

from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.modules.documents.models import Document
from app.modules.documents.storage import DocumentStorage, document_storage
from app.modules.quizzes.exceptions import (
    DocumentNotFoundError,
    DocumentNotReadyError,
    GeminiGenerationError,
    InvalidPageRangeError,
    QuizNotFoundError,
)
from app.modules.quizzes.models import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from app.modules.quizzes.prompt import (
    QUIZ_GENERATOR_SYSTEM_PROMPT,
    build_quiz_generation_prompt,
)
from app.modules.quizzes.schemas import (
    GeneratedQuizPayload,
    QuizAttemptCreateRequest,
    QuizAttemptCreateResponse,
    QuizGenerateRequest,
)

logger = logging.getLogger(__name__)


class QuizService:
    """Orchestrates quiz generation using Gemini Structured Output and DB persistence."""

    def __init__(
        self,
        client: genai.Client | None = None,
        storage: DocumentStorage | None = None,
    ) -> None:
        self._client = client
        self.storage = storage or document_storage

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    async def generate_quiz(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        request: QuizGenerateRequest,
    ) -> Quiz:
        """Generates a structured quiz from document pages and saves it atomically."""
        # 1. Verify document existence and ownership (IDOR defense)
        stmt = select(Document).where(Document.id == request.document_id)
        result = await db.execute(stmt)
        document = result.scalar_one_or_none()

        if not document or document.user_id != user_id:
            raise DocumentNotFoundError(request.document_id)

        # 2. Check document status
        if document.status not in ("ready", "completed"):
            raise DocumentNotReadyError(
                request.document_id,
                reason=f"Tài liệu đang ở trạng thái '{document.status}', chưa sẵn sàng tạo quiz.",
            )

        # 3. Validate page range
        page_start = request.page_start or 1
        page_end = request.page_end or document.total_pages

        if (
            page_start < 1
            or page_end < page_start
            or page_end > document.total_pages
            or page_start > document.total_pages
        ):
            raise InvalidPageRangeError(
                f"Khoảng trang [{page_start}, {page_end}] không hợp lệ cho tài liệu có {document.total_pages} trang."
            )

        # 4. Extract context from markdown page files with explicit page delimiters
        doc_dir = self.storage.get_document_dir(str(document.id))
        pages_dir = doc_dir / "pages"

        page_blocks: list[str] = []
        for p in range(page_start, page_end + 1):
            page_file = pages_dir / f"page_{p}.md"
            content = ""
            if page_file.is_file():
                try:
                    content = page_file.read_text(encoding="utf-8").strip()
                except Exception as read_err:
                    logger.warning("Error reading %s: %s", page_file, read_err)

            if not content:
                # Fallback to storage get_document_content if available
                doc_content = self.storage.get_document_content(
                    str(document.id), page_number=p
                )
                if doc_content and doc_content.content:
                    content = doc_content.content.strip()

            if content:
                page_blocks.append(
                    f"=== BẮT ĐẦU TRANG {p} ===\n{content}\n=== KẾT THÚC TRANG {p} ==="
                )

        if not page_blocks:
            raise DocumentNotReadyError(
                request.document_id,
                reason="Không tìm thấy nội dung văn bản của các trang được chọn.",
            )

        context_text = "\n\n".join(page_blocks)

        # 5. Build prompt & call Gemini structured output with model fallback on 503
        user_prompt = build_quiz_generation_prompt(
            document_title=document.title,
            context_text=context_text,
            num_questions=request.num_questions,
            topic_tag=request.topic_tag,
        )

        candidate_models = [
            settings.GEMINI_MODEL,
            "gemini-3.1-flash-lite",
            "gemini-3-flash-preview",
        ]
        # Deduplicate while preserving order
        unique_models = list(dict.fromkeys([m for m in candidate_models if m]))

        response = None
        last_error = None

        for model_name in unique_models:
            try:
                logger.info("Generating quiz with Gemini model: %s", model_name)
                response = await self.client.aio.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=QUIZ_GENERATOR_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=GeneratedQuizPayload,
                        temperature=0.3,
                    ),
                )
                if response:
                    break
            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                if "503" in err_str or "UNAVAILABLE" in err_str:
                    logger.warning(
                        "Model '%s' returned 503 UNAVAILABLE. Falling back to next candidate model...",
                        model_name,
                    )
                    continue
                logger.error(
                    "Gemini API call failed with model '%s': %s", model_name, exc
                )
                raise GeminiGenerationError(str(exc)) from exc

        if not response:
            logger.error("All Gemini model candidates failed: %s", last_error)
            raise GeminiGenerationError(str(last_error)) from last_error

        parsed_payload = getattr(response, "parsed", None)
        if not isinstance(parsed_payload, GeneratedQuizPayload):
            raw_text = getattr(response, "text", None) or ""
            try:
                parsed_payload = GeneratedQuizPayload.model_validate_json(raw_text)
            except Exception as parse_exc:
                logger.error(
                    "Failed to parse Gemini response as GeneratedQuizPayload: %s. Raw: %s",
                    parse_exc,
                    raw_text,
                )
                raise GeminiGenerationError(
                    "Phản hồi từ Gemini không đúng định dạng JSON Schema yêu cầu."
                ) from parse_exc

        if not parsed_payload.questions:
            raise GeminiGenerationError("Mô hình AI không sinh được câu hỏi nào.")

        # 6. Atomic DB Persistence
        quiz_title = request.title or parsed_payload.title or f"Quiz: {document.title}"
        quiz = Quiz(
            id=uuid.uuid4(),
            user_id=user_id,
            document_id=document.id,
            subject_id=document.subject_id,
            title=quiz_title,
            is_interleaved=False,
            total_questions=len(parsed_payload.questions),
            time_limit_minutes=15,
        )
        db.add(quiz)
        await db.flush()

        for q in parsed_payload.questions:
            bloom_val = (
                q.bloom_level.value
                if hasattr(q.bloom_level, "value")
                else str(q.bloom_level)
            )
            options_json = [
                opt.model_dump() if hasattr(opt, "model_dump") else dict(opt)
                for opt in q.options
            ]
            question_db = QuizQuestion(
                id=uuid.uuid4(),
                quiz_id=quiz.id,
                question_text=q.question_text,
                bloom_level=bloom_val,
                options=options_json,
                correct_option=q.correct_option,
                explanation=q.explanation,
                target_page=q.target_page,
                topic_tag=q.topic_tag,
                source_document_id=document.id,
                source_document_title=document.title,
            )
            db.add(question_db)

        await db.commit()

        # 7. Reload quiz with questions relationship eagerly loaded
        query_stmt = (
            select(Quiz).options(selectinload(Quiz.questions)).where(Quiz.id == quiz.id)
        )
        saved_result = await db.execute(query_stmt)
        return saved_result.scalar_one()

    async def list_user_quizzes(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None = None,
    ) -> list[Quiz]:
        """Lists standalone quizzes belonging to the authorized user, newest first."""
        stmt = (
            select(Quiz)
            .options(selectinload(Quiz.questions))
            .where(Quiz.user_id == user_id, Quiz.roadmap_id.is_(None))
        )
        if subject_id is not None:
            stmt = stmt.where(Quiz.subject_id == subject_id)
        stmt = stmt.order_by(Quiz.created_at.desc())
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_quiz_by_id(
        self,
        db: AsyncSession,
        quiz_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Quiz:
        """Retrieves a quiz and its questions for the authorized user."""
        stmt = (
            select(Quiz)
            .options(selectinload(Quiz.questions))
            .where(Quiz.id == quiz_id, Quiz.user_id == user_id)
        )
        result = await db.execute(stmt)
        quiz = result.scalar_one_or_none()
        if not quiz:
            raise QuizNotFoundError(quiz_id)
        return quiz

    async def delete_quiz(
        self,
        db: AsyncSession,
        quiz_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Deletes a quiz owned by the authorized user."""
        stmt = select(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id)
        result = await db.execute(stmt)
        quiz = result.scalar_one_or_none()
        if not quiz:
            raise QuizNotFoundError(quiz_id)
        await db.delete(quiz)
        await db.commit()

    async def record_quiz_attempt(
        self,
        db: AsyncSession,
        quiz_id: uuid.UUID,
        user_id: uuid.UUID,
        request: QuizAttemptCreateRequest,
    ) -> QuizAttemptCreateResponse:
        """Persists a completed QuizAttempt and its QuizAttemptAnswers for flashcard extraction."""
        quiz = await self.get_quiz_by_id(db=db, quiz_id=quiz_id, user_id=user_id)
        answers_map = {
            a.question_id: a.selected_option.strip().upper()
            for a in request.answers
        }

        total_q = len(quiz.questions)
        total_correct = 0
        now_utc = datetime.now(UTC)

        attempt = QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=user_id,
            score=0.0,
            total_correct=0,
            total_incorrect=0,
            completed_at=now_utc,
        )
        db.add(attempt)
        await db.flush()

        for q in quiz.questions:
            selected = answers_map.get(q.id, "-")
            is_correct = selected == q.correct_option.strip().upper()
            if is_correct:
                total_correct += 1
            ans_row = QuizAttemptAnswer(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                question_id=q.id,
                selected_option=selected[:10] if selected else "-",
                is_correct=is_correct,
            )
            db.add(ans_row)

        total_incorrect = max(0, total_q - total_correct)
        score = round((total_correct / total_q) * 100.0, 2) if total_q > 0 else 0.0
        attempt.score = score
        attempt.total_correct = total_correct
        attempt.total_incorrect = total_incorrect

        await db.commit()
        return QuizAttemptCreateResponse(
            attempt_id=attempt.id,
            quiz_id=quiz.id,
            score=score,
            total_correct=total_correct,
            total_incorrect=total_incorrect,
            completed_at=now_utc,
        )


quiz_service = QuizService()
