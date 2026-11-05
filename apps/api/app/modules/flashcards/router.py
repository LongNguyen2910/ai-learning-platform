import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.flashcards.schemas import (
    FlashcardBulkCreateRequest,
    FlashcardBulkCreateResponse,
    FlashcardExtractRequest,
    FlashcardExtractResponse,
)
from app.modules.flashcards.service import flashcard_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flashcards", tags=["Flashcards"])


@router.post(
    "/extract",
    response_model=FlashcardExtractResponse,
    status_code=status.HTTP_200_OK,
    summary="Trích xuất tự động danh sách cặp thẻ Flashcard (Preview) từ Quiz hoặc Chat",
)
async def extract_flashcards(
    request: FlashcardExtractRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardExtractResponse:
    """Trích xuất các cặp thẻ Flashcard từ các câu hỏi làm sai trong bài kiểm tra

    hoặc từ nội dung trao đổi với AI Tutor.
    """
    return await flashcard_service.extract_flashcards(
        db=db,
        user_id=current_user.id,
        request=request,
    )


@router.post(
    "/bulk",
    response_model=FlashcardBulkCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Lưu hàng loạt thẻ Flashcard đã được học viên duyệt vào Deck",
)
async def bulk_create_flashcards(
    request: FlashcardBulkCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardBulkCreateResponse:
    """Lưu danh sách các thẻ Flashcard sau khi học viên xem trước và chỉnh sửa."""
    return await flashcard_service.bulk_create_flashcards(
        db=db,
        user_id=current_user.id,
        request=request,
    )
