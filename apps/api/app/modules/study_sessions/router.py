import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.study_sessions.exceptions import (
    DocumentMismatchError,
    RoadmapNodeMismatchError,
    StudySessionNotFoundError,
    SubjectNotFoundError,
)
from app.modules.study_sessions.schemas import (
    StudySessionCreateRequest,
    StudySessionResponse,
)
from app.modules.study_sessions.service import StudySessionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/study-sessions", tags=["Study Sessions"])


@router.post(
    "",
    response_model=StudySessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a completed Pomodoro study session",
    description="Ghi nhan thoi luong hoc thuc te cho mot mon hoc (1-180 phut).",
)
async def create_study_session(
    payload: StudySessionCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StudySessionResponse:
    service = StudySessionService(db)
    try:
        session = await service.record_session(current_user.id, payload)
        return StudySessionResponse.model_validate(session)
    except SubjectNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except (DocumentMismatchError, RoadmapNodeMismatchError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.exception("Unexpected error recording study session: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record study session.",
        ) from err


@router.get(
    "",
    response_model=list[StudySessionResponse],
    status_code=status.HTTP_200_OK,
    summary="List completed study sessions",
    description="Lay danh sach nhat ky phien hoc cua nguoi dung, sap xep theo thoi gian moi nhat.",
)
async def list_study_sessions(
    subject_id: Optional[uuid.UUID] = Query(default=None, description="Loc theo mon hoc"),
    limit: int = Query(default=50, ge=1, le=100, description="So luong phien hoc toi da"),
    offset: int = Query(default=0, ge=0, description="Phan trang vi tri bat dau"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[StudySessionResponse]:
    service = StudySessionService(db)
    sessions = await service.list_sessions(
        user_id=current_user.id,
        subject_id=subject_id,
        limit=limit,
        offset=offset,
    )
    return [StudySessionResponse.model_validate(s) for s in sessions]


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a study session",
    description="Xoa mot phien hoc da ghi nhan theo session_id.",
)
async def delete_study_session(
    session_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    service = StudySessionService(db)
    try:
        await service.delete_session(session_id, current_user.id)
    except StudySessionNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except Exception as err:
        logger.exception("Unexpected error deleting study session: %s", err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete study session.",
        ) from err
