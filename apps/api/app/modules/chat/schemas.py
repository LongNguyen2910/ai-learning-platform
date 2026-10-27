from pydantic import BaseModel, Field


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
