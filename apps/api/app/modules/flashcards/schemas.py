import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class FlashcardReviewRequest(BaseModel):
    rating: int = Field(
        ...,
        ge=0,
        le=5,
        description="Rating score between 0 (blackout) and 5 (perfect recall)",
    )
    review_date: date | None = Field(
        default=None,
        description="Optional review date, defaults to current UTC date if omitted",
    )


class FlashcardReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deck_id: uuid.UUID
    repetition_number: int
    easiness_factor: float
    interval_days: int
    due_date: date
