from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

DocumentStatus = Literal[
    "uploading", "parsing", "parsed", "indexing", "ready", "failed"
]


class ParsedPageMetadata(BaseModel):
    page_number: int
    has_formula: bool = False
    has_image: bool = False
    char_count: int = 0
    file_path: str


class DocumentMetadata(BaseModel):
    document_id: str
    user_id: str | None = None
    title: str
    file_path: str
    file_size_kb: int
    total_pages: int
    status: DocumentStatus = "uploading"
    error_message: str | None = None
    pages: list[ParsedPageMetadata] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class DocumentUploadResponse(BaseModel):
    document_id: str
    user_id: str | None = None
    title: str
    status: DocumentStatus
    total_pages: int
    message: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    user_id: str | None = None
    title: str
    status: DocumentStatus
    file_size_kb: int = 0
    total_pages: int
    parsed_pages: int
    error_message: str | None = None
    created_at: str
    updated_at: str


class DocumentContentResponse(BaseModel):
    document_id: str
    user_id: str | None = None
    title: str
    status: DocumentStatus
    total_pages: int
    full_content: str | None = None
    pages: list[ParsedPageMetadata] = Field(default_factory=list)


class DocumentDeleteResponse(BaseModel):
    document_id: str
    message: str


class DocumentRetryResponse(BaseModel):
    document_id: str
    title: str
    status: DocumentStatus
    total_pages: int
    message: str
