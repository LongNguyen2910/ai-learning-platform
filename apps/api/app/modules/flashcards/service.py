import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from google import genai
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.modules.documents.models import Document
from app.modules.documents.storage import DocumentStorage, document_storage
from app.modules.flashcards.models import Flashcard, FlashcardDeck
from app.modules.flashcards.prompt import (
    FLASHCARD_DECK_GENERATION_SYSTEM_PROMPT,
    FLASHCARD_EXTRACTION_SYSTEM_PROMPT,
    build_document_flashcard_prompt,
    build_quiz_extraction_prompt,
)
from app.modules.flashcards.schemas import (
    ExtractedFlashcardItem,
    ExtractionSourceType,
    FlashcardBulkCreateRequest,
    FlashcardBulkCreateResponse,
    FlashcardDeckCreateRequest,
    FlashcardDeckDetailResponse,
    FlashcardDeckGenerateRequest,
    FlashcardDeckSummaryResponse,
    FlashcardExtractRequest,
    FlashcardExtractResponse,
    FlashcardItemCreate,
    FlashcardResponse,
    FlashcardReviewRequest,
    FlashcardUpdateRequest,
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

    @staticmethod
    def _build_deck_summary(deck: FlashcardDeck) -> FlashcardDeckSummaryResponse:
        today = datetime.now(UTC).date()
        cards = list(deck.flashcards or [])
        total_cards = len(cards)
        due_count = sum(1 for c in cards if c.due_date <= today)
        mastered_count = sum(
            1 for c in cards if c.repetition_number >= 2 and c.interval_days >= 6
        )
        return FlashcardDeckSummaryResponse(
            id=deck.id,
            user_id=deck.user_id,
            subject_id=deck.subject_id,
            document_id=deck.document_id,
            title=deck.title,
            description=deck.description,
            created_at=deck.created_at,
            total_cards=total_cards,
            due_count=due_count,
            mastered_count=mastered_count,
        )

    async def list_decks(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        subject_id: uuid.UUID | None = None,
    ) -> list[FlashcardDeckSummaryResponse]:
        stmt = (
            select(FlashcardDeck)
            .where(FlashcardDeck.user_id == user_id)
            .options(selectinload(FlashcardDeck.flashcards))
            .order_by(FlashcardDeck.created_at.desc())
        )
        if subject_id is not None:
            stmt = stmt.where(FlashcardDeck.subject_id == subject_id)
        result = await db.execute(stmt)
        decks = list(result.scalars().all())
        return [self._build_deck_summary(d) for d in decks]

    async def create_deck(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        request: FlashcardDeckCreateRequest,
    ) -> FlashcardDeckDetailResponse:
        resolved_subject_id = request.subject_id
        if request.document_id and resolved_subject_id is None:
            doc_res = await db.execute(
                select(Document).where(
                    Document.id == request.document_id,
                    Document.user_id == user_id,
                )
            )
            doc = doc_res.scalar_one_or_none()
            if doc and doc.subject_id:
                resolved_subject_id = doc.subject_id

        now_utc = datetime.now(UTC)
        deck = FlashcardDeck(
            id=uuid.uuid4(),
            user_id=user_id,
            subject_id=resolved_subject_id,
            document_id=request.document_id,
            title=request.title.strip(),
            description=request.description.strip()
            if request.description
            else None,
            created_at=now_utc,
        )
        db.add(deck)
        await db.commit()
        return FlashcardDeckDetailResponse(
            id=deck.id,
            user_id=deck.user_id,
            subject_id=deck.subject_id,
            document_id=deck.document_id,
            title=deck.title,
            description=deck.description,
            created_at=deck.created_at,
            total_cards=0,
            due_count=0,
            mastered_count=0,
            cards=[],
        )

    async def get_deck_detail(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        deck_id: uuid.UUID,
    ) -> FlashcardDeckDetailResponse:
        stmt = (
            select(FlashcardDeck)
            .where(
                FlashcardDeck.id == deck_id,
                FlashcardDeck.user_id == user_id,
            )
            .options(selectinload(FlashcardDeck.flashcards))
        )
        result = await db.execute(stmt)
        deck = result.scalar_one_or_none()
        if not deck:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bộ thẻ (Deck) không tồn tại hoặc bạn không có quyền truy cập.",
            )
        summary = self._build_deck_summary(deck)
        sorted_cards = sorted(
            deck.flashcards or [],
            key=lambda c: (c.due_date, c.created_at),
        )
        return FlashcardDeckDetailResponse(
            **summary.model_dump(),
            cards=[FlashcardResponse.model_validate(c) for c in sorted_cards],
        )

    async def delete_deck(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        deck_id: uuid.UUID,
    ) -> None:
        stmt = select(FlashcardDeck).where(
            FlashcardDeck.id == deck_id,
            FlashcardDeck.user_id == user_id,
        )
        result = await db.execute(stmt)
        deck = result.scalar_one_or_none()
        if not deck:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bộ thẻ (Deck) không tồn tại hoặc bạn không có quyền truy cập.",
            )
        await db.delete(deck)
        await db.commit()

    async def generate_deck_from_document(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        request: FlashcardDeckGenerateRequest,
        storage: DocumentStorage | None = None,
    ) -> FlashcardDeckDetailResponse:
        doc_stmt = select(Document).where(
            Document.id == request.document_id,
            Document.user_id == user_id,
        )
        doc_res = await db.execute(doc_stmt)
        document = doc_res.scalar_one_or_none()
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Tài liệu không tồn tại hoặc bạn không có quyền truy cập.",
            )
        if document.status not in ("ready", "completed"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tài liệu chưa xử lý xong, chưa thể sinh bộ thẻ Flashcard.",
            )

        page_start = request.page_start or 1
        page_end = request.page_end or document.total_pages
        if (
            page_start < 1
            or page_end < page_start
            or page_end > document.total_pages
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Khoảng trang [{page_start}, {page_end}] không hợp lệ.",
            )

        doc_storage = storage or document_storage
        doc_dir = doc_storage.get_document_dir(str(document.id))
        pages_dir = doc_dir / "pages"

        page_blocks: list[str] = []
        for p in range(page_start, page_end + 1):
            page_file = pages_dir / f"page_{p}.md"
            content = ""
            if page_file.is_file():
                try:
                    content = page_file.read_text(encoding="utf-8").strip()
                except Exception:
                    content = ""
            if not content:
                doc_content = doc_storage.get_document_content(
                    str(document.id), page_number=p
                )
                if doc_content and doc_content.content:
                    content = doc_content.content.strip()
            if content:
                page_blocks.append(
                    f"=== BẮT ĐẦU TRANG {p} ===\n{content}\n=== KẾT THÚC TRANG {p} ==="
                )

        if not page_blocks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Không tìm thấy nội dung văn bản trong khoảng trang đã chọn.",
            )

        user_prompt = build_document_flashcard_prompt(
            document_title=document.title,
            context_text="\n\n".join(page_blocks),
            num_cards=request.num_cards,
        )

        candidate_models = list(
            dict.fromkeys(
                filter(
                    None,
                    [
                        settings.GEMINI_MODEL,
                        "gemini-2.5-flash",
                        "gemini-1.5-flash",
                    ],
                )
            )
        )

        response = None
        last_error = None
        for model_name in candidate_models:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=FLASHCARD_DECK_GENERATION_SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        response_schema=GeneratedFlashcardsPayload,
                        temperature=0.25,
                    ),
                )
                if response:
                    break
            except Exception as exc:
                last_error = exc
                if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                    continue
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Lỗi khi gọi AI sinh Flashcard: {exc}",
                ) from exc

        if not response:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Dịch vụ AI hiện không khả dụng: {last_error}",
            )

        parsed_payload = getattr(response, "parsed", None)
        if not isinstance(parsed_payload, GeneratedFlashcardsPayload):
            raw_text = getattr(response, "text", None) or ""
            parsed_payload = GeneratedFlashcardsPayload.model_validate_json(
                raw_text
            )

        now_utc = datetime.now(UTC)
        today = now_utc.date()
        deck_title = (
            request.title.strip()
            if request.title and request.title.strip()
            else f"{document.title} (Pages {page_start}–{page_end})"
        )[:150]

        deck = FlashcardDeck(
            id=uuid.uuid4(),
            user_id=user_id,
            subject_id=document.subject_id,
            document_id=document.id,
            title=deck_title,
            description=f"AI-synthesized active recall deck from {document.title} (pp. {page_start}–{page_end}).",
            created_at=now_utc,
        )
        db.add(deck)
        await db.flush()

        created_cards: list[Flashcard] = []
        for item in parsed_payload.cards:
            card = Flashcard(
                id=uuid.uuid4(),
                deck_id=deck.id,
                user_id=user_id,
                front_text=item.front_text.strip(),
                back_text=item.back_text.strip(),
                page_number=item.target_page or page_start,
                repetition_number=0,
                easiness_factor=2.5,
                interval_days=1,
                due_date=today,
                created_at=now_utc,
            )
            created_cards.append(card)

        db.add_all(created_cards)
        await db.commit()

        return FlashcardDeckDetailResponse(
            id=deck.id,
            user_id=deck.user_id,
            subject_id=deck.subject_id,
            document_id=deck.document_id,
            title=deck.title,
            description=deck.description,
            created_at=deck.created_at,
            total_cards=len(created_cards),
            due_count=len(created_cards),
            mastered_count=0,
            cards=[FlashcardResponse.model_validate(c) for c in created_cards],
        )

    async def create_card(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        deck_id: uuid.UUID,
        request: FlashcardItemCreate,
    ) -> FlashcardResponse:
        stmt = select(FlashcardDeck).where(
            FlashcardDeck.id == deck_id,
            FlashcardDeck.user_id == user_id,
        )
        res = await db.execute(stmt)
        deck = res.scalar_one_or_none()
        if not deck:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Bộ thẻ (Deck) không tồn tại hoặc bạn không có quyền truy cập.",
            )
        now_utc = datetime.now(UTC)
        card = Flashcard(
            id=uuid.uuid4(),
            deck_id=deck.id,
            user_id=user_id,
            front_text=request.front_text.strip(),
            back_text=request.back_text.strip(),
            page_number=request.page_number,
            repetition_number=0,
            easiness_factor=2.5,
            interval_days=1,
            due_date=now_utc.date(),
            created_at=now_utc,
        )
        db.add(card)
        await db.commit()
        await db.refresh(card)
        return FlashcardResponse.model_validate(card)

    async def update_card(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        card_id: uuid.UUID,
        request: FlashcardUpdateRequest,
    ) -> FlashcardResponse:
        stmt = select(Flashcard).where(
            Flashcard.id == card_id,
            Flashcard.user_id == user_id,
        )
        res = await db.execute(stmt)
        card = res.scalar_one_or_none()
        if not card:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thẻ Flashcard không tồn tại.",
            )
        card.front_text = request.front_text.strip()
        card.back_text = request.back_text.strip()
        card.page_number = request.page_number
        await db.commit()
        await db.refresh(card)
        return FlashcardResponse.model_validate(card)

    async def delete_card(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        card_id: uuid.UUID,
    ) -> None:
        stmt = select(Flashcard).where(
            Flashcard.id == card_id,
            Flashcard.user_id == user_id,
        )
        res = await db.execute(stmt)
        card = res.scalar_one_or_none()
        if not card:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thẻ Flashcard không tồn tại.",
            )
        await db.delete(card)
        await db.commit()

    async def review_card_sm2(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        card_id: uuid.UUID,
        request: FlashcardReviewRequest,
    ) -> FlashcardResponse:
        """Applies the SuperMemo SM-2 algorithm based on rating (again, hard, good, easy)."""
        stmt = select(Flashcard).where(
            Flashcard.id == card_id,
            Flashcard.user_id == user_id,
        )
        res = await db.execute(stmt)
        card = res.scalar_one_or_none()
        if not card:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thẻ Flashcard không tồn tại.",
            )

        quality_map = {
            "again": 1,
            "hard": 3,
            "good": 4,
            "easy": 5,
        }
        q = quality_map[request.rating]
        rep = card.repetition_number or 0
        ef = card.easiness_factor or 2.5
        interval = card.interval_days or 1

        if q < 3:
            rep = 0
            interval = 1
        else:
            if rep == 0:
                interval = 1 if q == 3 else (3 if q == 4 else 4)
            elif rep == 1:
                interval = 3 if q == 3 else (6 if q == 4 else 8)
            else:
                multiplier = ef * (1.2 if q == 5 else (0.85 if q == 3 else 1.0))
                interval = max(1, int(round(interval * multiplier)))
            rep += 1

        new_ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        card.easiness_factor = round(max(1.3, new_ef), 2)
        card.repetition_number = rep
        card.interval_days = interval

        today = datetime.now(UTC).date()
        # If rated 'again', keep due today so the student knows it still needs work; otherwise schedule ahead
        card.due_date = (
            today if request.rating == "again" else today + timedelta(days=interval)
        )

        await db.commit()
        await db.refresh(card)
        return FlashcardResponse.model_validate(card)


flashcard_service = FlashcardService()
