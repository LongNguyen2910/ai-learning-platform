import logging
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.flashcards.schemas import (
    FlashcardBulkCreateRequest,
    FlashcardBulkCreateResponse,
    FlashcardDeckCreateRequest,
    FlashcardDeckDetailResponse,
    FlashcardDeckGenerateRequest,
    FlashcardDeckSummaryResponse,
    FlashcardExtractRequest,
    FlashcardExtractResponse,
    FlashcardItemCreate,
    FlashcardResponse,
    FlashcardReviewRequest,
    FlashcardUpdateRequest,
)
from app.modules.flashcards.service import flashcard_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/flashcards", tags=["Flashcards"])


@router.get(
    "/decks",
    response_model=list[FlashcardDeckSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="Lấy danh sách bộ thẻ Flashcard của người dùng",
)
async def list_flashcard_decks(
    subject_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FlashcardDeckSummaryResponse]:
    return await flashcard_service.list_decks(
        db=db,
        user_id=current_user.id,
        subject_id=subject_id,
    )


@router.post(
    "/decks",
    response_model=FlashcardDeckDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Tạo bộ thẻ Flashcard mới",
)
async def create_flashcard_deck(
    request: FlashcardDeckCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardDeckDetailResponse:
    return await flashcard_service.create_deck(
        db=db,
        user_id=current_user.id,
        request=request,
    )


@router.post(
    "/decks/generate",
    response_model=FlashcardDeckDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sinh bộ thẻ Flashcard tự động từ tài liệu PDF bằng AI",
)
async def generate_flashcard_deck(
    request: FlashcardDeckGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardDeckDetailResponse:
    return await flashcard_service.generate_deck_from_document(
        db=db,
        user_id=current_user.id,
        request=request,
    )


@router.get(
    "/decks/{deck_id}",
    response_model=FlashcardDeckDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Lấy chi tiết bộ thẻ kèm danh sách các thẻ Flashcard",
)
async def get_flashcard_deck(
    deck_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardDeckDetailResponse:
    return await flashcard_service.get_deck_detail(
        db=db,
        user_id=current_user.id,
        deck_id=deck_id,
    )


@router.delete(
    "/decks/{deck_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa bộ thẻ Flashcard",
)
async def delete_flashcard_deck(
    deck_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await flashcard_service.delete_deck(
        db=db,
        user_id=current_user.id,
        deck_id=deck_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/decks/{deck_id}/cards",
    response_model=FlashcardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Thêm 1 thẻ Flashcard mới vào Deck",
)
async def create_single_flashcard(
    deck_id: uuid.UUID,
    request: FlashcardItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    return await flashcard_service.create_card(
        db=db,
        user_id=current_user.id,
        deck_id=deck_id,
        request=request,
    )


@router.put(
    "/cards/{card_id}",
    response_model=FlashcardResponse,
    status_code=status.HTTP_200_OK,
    summary="Cập nhật nội dung thẻ Flashcard",
)
async def update_single_flashcard(
    card_id: uuid.UUID,
    request: FlashcardUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    return await flashcard_service.update_card(
        db=db,
        user_id=current_user.id,
        card_id=card_id,
        request=request,
    )


@router.delete(
    "/cards/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa 1 thẻ Flashcard",
)
async def delete_single_flashcard(
    card_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await flashcard_service.delete_card(
        db=db,
        user_id=current_user.id,
        card_id=card_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/cards/{card_id}/review",
    response_model=FlashcardResponse,
    status_code=status.HTTP_200_OK,
    summary="Chấm mức độ nhớ SM-2 cho thẻ Flashcard (again | hard | good | easy)",
)
async def review_flashcard(
    card_id: uuid.UUID,
    request: FlashcardReviewRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardResponse:
    return await flashcard_service.review_card_sm2(
        db=db,
        user_id=current_user.id,
        card_id=card_id,
        request=request,
    )


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
