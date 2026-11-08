from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BloomLevel(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"


class QuizOptionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="allow")

    key: str = Field(description="Mã đáp án: A, B, C hoặc D")
    text: str = Field(description="Nội dung chi tiết của lựa chọn")


class QuestionCreateSchema(BaseModel):
    question_text: str = Field(..., min_length=1)
    bloom_level: str = Field(default="remember_understand", max_length=30)
    options: list[dict[str, Any]] = Field(..., min_length=2)
    correct_option: str = Field(..., max_length=5)
    explanation: str | None = None
    target_page: int | None = None
    topic_tag: str | None = Field(default=None, max_length=100)


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


class QuizCreateRequest(BaseModel):
    document_id: UUID
    subject_id: UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    total_questions: int = Field(default=10, ge=1, le=50)
    time_limit_minutes: int = Field(default=15, ge=1, le=180)
    new_questions: list[QuestionCreateSchema] = Field(..., min_length=1)
    seed: int | None = None


class QuizGenerateRequest(BaseModel):
    document_id: UUID
    num_questions: int = Field(default=5, ge=5, le=10)
    page_start: int | None = Field(default=1, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    topic_tag: str | None = Field(default=None, max_length=100)
    title: str | None = Field(default=None, max_length=255)


class QuizQuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_text: str
    bloom_level: str
    options: list[QuizOptionItem] | list[dict[str, Any]]
    correct_option: str
    explanation: str | None = None
    target_page: int | None = None
    topic_tag: str | None = None


QuestionResponse = QuizQuestionResponse


class QuizResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None = None
    document_id: UUID
    subject_id: UUID | None = None
    title: str
    is_interleaved: bool = False
    total_questions: int
    time_limit_minutes: int = 15
    created_at: datetime
    questions: list[QuizQuestionResponse] = Field(default_factory=list)

    @field_validator("is_interleaved", mode="before")
    @classmethod
    def set_default_is_interleaved(cls, v: Any) -> bool:
        if v is None:
            return False
        return bool(v)
