import uuid
from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ExtractionSourceType(str, Enum):
    QUIZ_ATTEMPT = "quiz_attempt"
    CHAT_SESSION = "chat_session"


class FlashcardExtractRequest(BaseModel):
    source_type: ExtractionSourceType = Field(..., description="Loại nguồn trích xuất")
    source_id: uuid.UUID = Field(
        ..., description="ID của lượt làm quiz hoặc phiên chat"
    )
    message_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Danh sách ID tin nhắn cụ thể nếu trích xuất từ chat",
    )


class ExtractedFlashcardItem(BaseModel):
    front_text: str = Field(
        ...,
        description="Mặt trước: Thuật ngữ, câu hỏi khái niệm hoặc tên công thức",
    )
    back_text: str = Field(
        ...,
        description="Mặt sau: Định nghĩa, bản chất, công thức chuẩn và lưu ý cốt lõi",
    )
    category: Literal["term", "concept", "formula"] = Field(
        ...,
        description="Phân loại thẻ: thuật ngữ, khái niệm hoặc công thức",
    )
    context_snippet: str | None = Field(
        default=None,
        description="Đoạn trích dẫn gốc ngắn giúp gợi nhớ ngữ cảnh",
    )
    trigger_reason: str | None = Field(
        default=None,
        description="Lý do tạo: lỗi sai hoặc ngộ nhận cần củng cố",
    )
    target_page: int | None = Field(
        default=None,
        description="Số trang tài liệu tham chiếu (nếu có)",
    )


class GeneratedFlashcardsPayload(BaseModel):
    """Payload schema cho Gemini Structured Output."""

    cards: list[ExtractedFlashcardItem] = Field(
        default_factory=list,
        description="Danh sách thẻ flashcard được trích xuất và chuẩn hóa",
    )


class FlashcardExtractResponse(BaseModel):
    source_type: ExtractionSourceType
    source_id: uuid.UUID
    cards: list[ExtractedFlashcardItem]
    total_extracted: int
    message: str | None = None


class FlashcardItemCreate(BaseModel):
    front_text: str = Field(..., min_length=1, description="Mặt trước của thẻ")
    back_text: str = Field(..., min_length=1, description="Mặt sau của thẻ")
    page_number: int | None = Field(
        default=None, ge=1, description="Số trang tham chiếu"
    )


class FlashcardBulkCreateRequest(BaseModel):
    deck_id: uuid.UUID = Field(..., description="ID của Deck sẽ lưu thẻ vào")
    cards: list[FlashcardItemCreate] = Field(
        ...,
        min_length=1,
        description="Danh sách thẻ cần lưu",
    )


class FlashcardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deck_id: uuid.UUID
    user_id: uuid.UUID
    front_text: str
    back_text: str
    page_number: int | None = None
    repetition_number: int
    easiness_factor: float
    interval_days: int
    due_date: date
    created_at: datetime


class FlashcardBulkCreateResponse(BaseModel):
    deck_id: uuid.UUID
    created_count: int
    cards: list[FlashcardResponse]


class FlashcardDeckCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=1000)
    subject_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None


class FlashcardDeckGenerateRequest(BaseModel):
    document_id: uuid.UUID
    num_cards: int = Field(default=8, ge=3, le=20)
    page_start: int | None = Field(default=1, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, max_length=150)


class FlashcardDeckSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    created_at: datetime
    total_cards: int = 0
    due_count: int = 0
    mastered_count: int = 0


class FlashcardDeckDetailResponse(FlashcardDeckSummaryResponse):
    cards: list[FlashcardResponse] = Field(default_factory=list)


class FlashcardUpdateRequest(BaseModel):
    front_text: str = Field(..., min_length=1)
    back_text: str = Field(..., min_length=1)
    page_number: int | None = Field(default=None, ge=1)


FlashcardReviewRating = Literal["again", "hard", "good", "easy"]


class FlashcardReviewRequest(BaseModel):
    rating: FlashcardReviewRating

