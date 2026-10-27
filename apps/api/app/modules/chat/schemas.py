import json
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RAGChunkSearchRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=2,
        max_length=1000,
        description="Nội dung câu hỏi cần tra cứu",
    )
    page_number: int | None = Field(
        default=None,
        ge=1,
        description="Giới hạn số trang (tùy chọn)",
    )
    similarity_top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Số lượng chunk tối đa cần lấy",
    )
    score_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Ngưỡng điểm tương đồng tối thiểu",
    )


class RetrievedChunkDTO(BaseModel):
    chunk_id: str
    page_number: int
    chunk_index: int
    score: float
    content: str
    has_formula: bool
    has_image: bool
    citation_tag: str  # Ví dụ: "[[Trang 14]]"


class RAGChunkSearchResponse(BaseModel):
    document_id: str
    query: str
    total_retrieved: int
    chunks: list[RetrievedChunkDTO]


# ============================================================================
# Chat sessions & Socratic streaming
# ============================================================================


class ChatSessionCreateRequest(BaseModel):
    document_id: uuid.UUID
    title: str = Field(default="Hội thoại mới", min_length=1, max_length=255)


class ChatSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    title: str
    created_at: datetime | None = None


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    sender: Literal["user", "assistant"]
    content: str
    socratic_tier: int
    citations: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime | None = None


class ChatRequest(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Nội dung tin nhắn của học viên",
    )
    socratic_enabled: bool = Field(
        default=False,
        description="Trạng thái công tắc 'Chế độ Socratic Gia sư' trên Workspace",
    )
    new_question: bool = Field(
        default=False,
        description="Học viên bắt đầu một bài tập mới -> reset về Tầng 1",
    )
    requested_tier: int | None = Field(
        default=None,
        ge=1,
        le=3,
        description="Ép tầng Socratic cụ thể (tùy chọn, phục vụ debug/QA)",
    )
    page_number: int | None = Field(
        default=None,
        ge=1,
        description="Giới hạn truy vấn RAG theo trang PDF đang xem (tùy chọn)",
    )


ChatMode = Literal["socratic", "normal", "refusal"]


class SSEStreamEvent(BaseModel):
    """Envelope cho mỗi SSE event: `event: <event>\\ndata: <json(data)>\\n\\n`."""

    event: Literal["meta", "citations", "token", "done", "error"]
    data: dict[str, Any]

    def encode(self) -> str:
        payload = json.dumps(self.data, ensure_ascii=False, default=str)
        return f"event: {self.event}\ndata: {payload}\n\n"
