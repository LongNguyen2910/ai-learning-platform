from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"


class QuizOptionItem(BaseModel):
    key: str = Field(description="Mã đáp án: A, B, C hoặc D")
    text: str = Field(description="Nội dung chi tiết của lựa chọn")


class GeneratedQuestionItem(BaseModel):
    question_text: str = Field(description="Nội dung câu hỏi trắc nghiệm")
    bloom_level: BloomLevel = Field(
        description="Cấp độ Bloom: remember, understand hoặc apply"
    )
    options: list[QuizOptionItem] = Field(description="Đúng 4 lựa chọn A, B, C, D")
    correct_option: str = Field(description="Đáp án đúng: A, B, C hoặc D")
    explanation: str = Field(
        description="Giải thích ngắn gọn vì sao đáp án đúng dựa vào tài liệu"
    )
    target_page: int = Field(
        description="Số trang tài liệu chính xác nơi xuất hiện kiến thức này"
    )
    topic_tag: str = Field(description="Nhãn chủ đề hoặc khái niệm chính")


class GeneratedQuizPayload(BaseModel):
    title: str = Field(description="Tiêu đề gợi ý phù hợp cho bộ Quiz")
    questions: list[GeneratedQuestionItem] = Field(
        description="Danh sách các câu hỏi được sinh"
    )


class QuizGenerateRequest(BaseModel):
    document_id: UUID
    num_questions: int = Field(default=5, ge=5, le=10)
    page_start: int | None = Field(default=1, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    topic_tag: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=255)


class QuizQuestionResponse(BaseModel):
    id: UUID
    question_text: str
    bloom_level: str
    options: list[QuizOptionItem]
    correct_option: str
    explanation: str | None = None
    target_page: int | None = None
    topic_tag: str | None = None

    model_config = {"from_attributes": True}


class QuizResponse(BaseModel):
    id: UUID
    document_id: UUID
    subject_id: UUID | None = None
    title: str
    total_questions: int
    time_limit_minutes: int
    created_at: datetime
    questions: list[QuizQuestionResponse]

    model_config = {"from_attributes": True}
