import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class QuestionCreateSchema(BaseModel):
    question_text: str = Field(..., min_length=1)
    bloom_level: str = Field(default="remember_understand", max_length=30)
    options: list[dict[str, Any]] = Field(..., min_length=2)
    correct_option: str = Field(..., max_length=5)
    explanation: str | None = None
    target_page: int | None = None
    topic_tag: str | None = Field(default=None, max_length=100)


class QuizCreateRequest(BaseModel):
    document_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    title: str = Field(..., min_length=1, max_length=255)
    total_questions: int = Field(default=10, ge=1, le=50)
    time_limit_minutes: int = Field(default=15, ge=1, le=180)
    new_questions: list[QuestionCreateSchema] = Field(..., min_length=1)
    seed: int | None = None


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_text: str
    bloom_level: str
    options: list[dict[str, Any]]
    explanation: str | None = None
    target_page: int | None = None
    topic_tag: str | None = None


class QuizResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID
    subject_id: uuid.UUID | None = None
    title: str
    is_interleaved: bool
    total_questions: int
    time_limit_minutes: int
    created_at: datetime
    questions: list[QuestionResponse] = Field(default_factory=list)
