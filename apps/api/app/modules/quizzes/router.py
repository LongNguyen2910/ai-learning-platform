import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.quizzes.exceptions import (
    DocumentNotFoundError,
    DocumentNotReadyError,
    GeminiGenerationError,
    InsufficientQuestionsError,
    InvalidPageRangeError,
    QuizNotFoundError,
)
from app.modules.quizzes.schemas import (
    QuizCreateRequest,
    QuizGenerateRequest,
    QuizResponse,
)
from app.modules.quizzes.service import quiz_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quizzes", tags=["Quizzes"])


@router.get(
    "",
    response_model=list[QuizResponse],
    status_code=status.HTTP_200_OK,
    summary="Lấy danh sách các bộ quiz của người dùng hiện tại",
)
async def list_quizzes(
    subject_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[QuizResponse]:
    """Lấy danh sách các bộ quiz đã tạo của người dùng hiện tại, sắp xếp mới nhất trước."""
    quizzes = await quiz_service.list_user_quizzes(
        db=db,
        user_id=current_user.id,
        subject_id=subject_id,
    )
    return [QuizResponse.model_validate(q) for q in quizzes]


@router.post(
    "",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an interleaved practice quiz (FR-20)",
    description="Combines 70% current lesson questions with 30% historical review questions and shuffles them.",
)
async def create_quiz(
    payload: QuizCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizResponse:
    try:
        quiz = await quiz_service.create_interleaved_quiz(
            user_id=current_user.id,
            payload=payload,
            db=db,
        )
        return QuizResponse.model_validate(quiz)
    except InsufficientQuestionsError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(err),
        ) from err


@router.post(
    "/generate",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Sinh bộ câu hỏi trắc nghiệm tự động từ tài liệu bằng Gemini",
)
async def generate_quiz(
    request: QuizGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizResponse:
    """Sinh bộ câu hỏi trắc nghiệm chuẩn Bloom và lưu trực tiếp vào cơ sở dữ liệu."""
    try:
        quiz = await quiz_service.generate_quiz(
            db=db,
            user_id=current_user.id,
            request=request,
        )
        return QuizResponse.model_validate(quiz)
    except DocumentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DocumentNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except InvalidPageRangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except GeminiGenerationError as exc:
        logger.error("Error generating quiz: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get(
    "/{quiz_id}",
    response_model=QuizResponse,
    status_code=status.HTTP_200_OK,
    summary="Get quiz details by ID",
)
async def get_quiz(
    quiz_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QuizResponse:
    """Lấy thông tin chi tiết của một bộ quiz theo ID thuộc sở hữu của người dùng hiện tại."""
    try:
        quiz = await quiz_service.get_quiz_by_id(
            db=db,
            quiz_id=quiz_id,
            user_id=current_user.id,
        )
        return QuizResponse.model_validate(quiz)
    except QuizNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{quiz_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Xóa một bộ quiz của người dùng hiện tại",
)
async def delete_quiz(
    quiz_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Xóa bộ quiz theo ID nếu thuộc quyền sở hữu của người dùng hiện tại."""
    try:
        await quiz_service.delete_quiz(
            db=db,
            quiz_id=quiz_id,
            user_id=current_user.id,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except QuizNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

