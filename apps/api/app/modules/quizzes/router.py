import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.quizzes.exceptions import (
    InsufficientQuestionsError,
    QuizNotFoundError,
)
from app.modules.quizzes.schemas import QuizCreateRequest, QuizResponse
from app.modules.quizzes.service import QuizService

router = APIRouter(prefix="/quizzes", tags=["Quizzes"])


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
    service = QuizService(db)
    try:
        quiz = await service.create_interleaved_quiz(current_user.id, payload)
        return QuizResponse.model_validate(quiz)
    except InsufficientQuestionsError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(err),
        ) from err


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
    service = QuizService(db)
    try:
        quiz = await service.get_quiz(current_user.id, quiz_id)
        return QuizResponse.model_validate(quiz)
    except QuizNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
