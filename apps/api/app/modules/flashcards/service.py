import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.modules.flashcards.models import Flashcard, FlashcardDeck
from app.modules.flashcards.prompt import (
    FLASHCARD_EXTRACTION_SYSTEM_PROMPT,
    build_quiz_extraction_prompt,
)
from app.modules.flashcards.schemas import (
    ExtractedFlashcardItem,
    ExtractionSourceType,
    FlashcardBulkCreateRequest,
    FlashcardBulkCreateResponse,
    FlashcardExtractRequest,
    FlashcardExtractResponse,
    FlashcardResponse,
    GeneratedFlashcardsPayload,
)
from app.modules.quizzes.models import QuizAttempt, QuizAttemptAnswer

logger = logging.getLogger(__name__)


def _resolve_option_text(options: list[Any], key: str) -> str:
    for opt in options:
        if isinstance(opt, dict) and opt.get("key") == key:
            return f"{key}. {opt.get('text', '')}"
    return key


class FlashcardService:
    """Xử lý nghiệp vụ trích xuất và quản lý thẻ Flashcard."""

    def __init__(self, client: genai.Client | None = None) -> None:
        self._client = client

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    async def extract_flashcards(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        request: FlashcardExtractRequest,
    ) -> FlashcardExtractResponse:
        """Trích xuất flashcards dựa trên source_type được yêu cầu."""
        if request.source_type == ExtractionSourceType.QUIZ_ATTEMPT:
            return await self._extract_from_quiz_attempt(db, user_id, request.source_id)
        elif request.source_type == ExtractionSourceType.CHAT_SESSION:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Trích xuất từ chat hiện hỗ trợ thông qua cơ chế gợi ý thời gian thực (inline suggestion) trong phiên học.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Nguồn trích xuất '{request.source_type}' không được hỗ trợ.",
            )

    async def _extract_from_quiz_attempt(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        attempt_id: uuid.UUID,
    ) -> FlashcardExtractResponse:
        """Trích xuất các cặp flashcard từ các câu hỏi làm sai trong bài quiz."""
        stmt = (
            select(QuizAttempt)
            .where(QuizAttempt.id == attempt_id)
            .options(
                selectinload(QuizAttempt.answers).selectinload(
                    QuizAttemptAnswer.question
                )
            )
        )
        result = await db.execute(stmt)
        attempt = result.scalar_one_or_none()

        if not attempt or attempt.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Lượt làm bài quiz không tồn tại hoặc bạn không có quyền truy cập.",
            )

        if attempt.completed_at is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vui lòng hoàn thành bài kiểm tra trước khi trích xuất flashcard.",
            )

        # Lọc các câu trả lời sai
        wrong_answers = [ans for ans in attempt.answers if not ans.is_correct]

        # Fast path: Nếu không có câu sai nào, trả về rỗng ngay lập tức (tiết kiệm token & latency)
        if not wrong_answers:
            return FlashcardExtractResponse(
                source_type=ExtractionSourceType.QUIZ_ATTEMPT,
                source_id=attempt_id,
                cards=[],
                total_extracted=0,
                message="Chúc mừng! Bạn đã trả lời đúng tất cả các câu hỏi nên không có flashcard củng cố nào cần tạo.",
            )

        # Giới hạn tối đa 10 câu sai tiêu biểu
        sampled_wrong = wrong_answers[:10]

        wrong_items_data: list[dict[str, Any]] = []
        for ans in sampled_wrong:
            q = ans.question
            if not q:
                continue

            options_list = q.options if isinstance(q.options, list) else []

            selected_text = _resolve_option_text(options_list, ans.selected_option)
            correct_text = _resolve_option_text(options_list, q.correct_option)

            wrong_items_data.append(
                {
                    "question_text": q.question_text,
                    "selected_option_text": selected_text,
                    "correct_option_text": correct_text,
                    "explanation": q.explanation,
                    "target_page": q.target_page,
                }
            )

        user_prompt = build_quiz_extraction_prompt(wrong_items_data)

        # Gọi Gemini với Structured Output
        candidate_models = [
            settings.GEMINI_MODEL,
            "gemini-2.5-flash",
            "gemini-1.5-flash",
        ]
        # Loại bỏ trùng lặp trong khi vẫn giữ thứ tự
        candidate_models = list(dict.fromkeys(filter(None, candidate_models)))

        response = None
        last_error = None

        for model_name in candidate_models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=FLASHCARD_EXTRACTION_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=GeneratedFlashcardsPayload,
                        temperature=0.2,
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
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Lỗi khi gọi AI trích xuất flashcard: {exc}",
                ) from exc

        if not response:
            logger.error("All Gemini model candidates failed: %s", last_error)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Dịch vụ AI hiện không khả dụng: {last_error}",
            ) from last_error

        parsed_payload = getattr(response, "parsed", None)
        if not isinstance(parsed_payload, GeneratedFlashcardsPayload):
            raw_text = getattr(response, "text", None) or ""
            try:
                parsed_payload = GeneratedFlashcardsPayload.model_validate_json(
                    raw_text
                )
            except Exception as parse_exc:
                logger.error(
                    "Failed to parse Gemini response as GeneratedFlashcardsPayload: %s. Raw: %s",
                    parse_exc,
                    raw_text,
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Phản hồi từ AI không đúng cấu trúc yêu cầu.",
                ) from parse_exc

        cards: list[ExtractedFlashcardItem] = parsed_payload.cards

        return FlashcardExtractResponse(
            source_type=ExtractionSourceType.QUIZ_ATTEMPT,
            source_id=attempt_id,
            cards=cards,
            total_extracted=len(cards),
            message=f"Đã trích xuất thành công {len(cards)} thẻ flashcard củng cố kiến thức từ các câu làm sai.",
        )

    async def bulk_create_flashcards(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        request: FlashcardBulkCreateRequest,
    ) -> FlashcardBulkCreateResponse:
        """Lưu danh sách thẻ đã duyệt vào Deck."""
        stmt = select(FlashcardDeck).where(FlashcardDeck.id == request.deck_id)
        result = await db.execute(stmt)
        deck = result.scalar_one_or_none()

        if not deck or deck.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bộ thẻ (Deck) không tồn tại hoặc bạn không có quyền truy cập.",
            )

        now_utc = datetime.now(UTC)
        today = now_utc.date()

        created_cards: list[Flashcard] = []
        for item in request.cards:
            card = Flashcard(
                id=uuid.uuid4(),
                deck_id=deck.id,
                user_id=user_id,
                front_text=item.front_text.strip(),
                back_text=item.back_text.strip(),
                page_number=item.page_number,
                repetition_number=0,
                easiness_factor=2.5,
                interval_days=1,
                due_date=today,
                created_at=now_utc,
            )
            created_cards.append(card)

        db.add_all(created_cards)
        await db.commit()

        for card in created_cards:
            await db.refresh(card)

        return FlashcardBulkCreateResponse(
            deck_id=deck.id,
            created_count=len(created_cards),
            cards=[FlashcardResponse.model_validate(c) for c in created_cards],
        )


flashcard_service = FlashcardService()
