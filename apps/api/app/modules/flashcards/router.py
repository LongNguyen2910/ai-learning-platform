import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.flashcards.exceptions import FlashcardNotFoundError
from app.modules.flashcards.schemas import (
    FlashcardReviewRequest,
    FlashcardReviewResponse,
)
from app.modules.flashcards.service import FlashcardService

router = APIRouter(prefix="/flashcards", tags=["Flashcards"])


@router.post(
    "/{flashcard_id}/review",
    response_model=FlashcardReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Review a flashcard with SM-2 spaced repetition",
    description="Updates repetition count, easiness factor, interval, and next due date based on user rating (0-5 stars).",
)
async def review_flashcard(
    flashcard_id: uuid.UUID,
    payload: FlashcardReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardReviewResponse:
    service = FlashcardService(db)
    try:
        updated = await service.review_flashcard(
            user_id=current_user.id,
            flashcard_id=flashcard_id,
            rating=payload.rating,
            review_date=payload.review_date,
        )
        return FlashcardReviewResponse.model_validate(updated)
    except FlashcardNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
