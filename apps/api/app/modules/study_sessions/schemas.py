import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StudySessionCreateRequest(BaseModel):
    subject_id: uuid.UUID
    duration_minutes: int = Field(
        ...,
        ge=1,
        le=180,
        description="Thoi gian hoc thuc te tu 1 den 180 phut",
    )
    document_id: Optional[uuid.UUID] = None
    roadmap_node_id: Optional[uuid.UUID] = None
    session_type: str = Field(
        default="pomodoro",
        max_length=20,
        description="Loai phien hoc: pomodoro, deep_work, review",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="Thoi gian hoan thanh (neu client khong truyen, server se lay gio hien tai)",
    )

    @field_validator("completed_at")
    @classmethod
    def validate_completed_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is not None:
            now = datetime.now(v.tzinfo or UTC)
            if v > now + timedelta(minutes=5):
                raise ValueError("completed_at cannot be in the future.")
        return v


class StudySessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    subject_id: Optional[uuid.UUID]
    document_id: Optional[uuid.UUID]
    roadmap_node_id: Optional[uuid.UUID]
    duration_minutes: int
    session_type: str
    completed_at: datetime
