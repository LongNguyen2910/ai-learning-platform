import uuid

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.study_sessions.exceptions import (
    DocumentMismatchError,
    RoadmapNodeMismatchError,
    StudySessionNotFoundError,
    SubjectNotFoundError,
)
from app.modules.study_sessions.models import StudySession
from app.modules.study_sessions.repository import StudySessionRepository
from app.modules.study_sessions.schemas import StudySessionCreateRequest


class StudySessionService:
    """Application Service orchestrating study session tracking business rules."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = StudySessionRepository(session)

    async def record_session(
        self, user_id: uuid.UUID, request: StudySessionCreateRequest
    ) -> StudySession:
        subject_valid = await self.repository.subject_exists_for_user(
            request.subject_id, user_id
        )
        if not subject_valid:
            raise SubjectNotFoundError(
                f"Subject {request.subject_id} not found or unauthorized for user."
            )

        if request.document_id is not None:
            doc_valid = await self.repository.document_matches_user_and_subject(
                request.document_id, user_id, request.subject_id
            )
            if not doc_valid:
                raise DocumentMismatchError(
                    f"Document {request.document_id} not found or does not belong to this subject."
                )

        if request.roadmap_node_id is not None:
            node_valid = await self.repository.roadmap_node_matches_user_and_subject(
                request.roadmap_node_id, user_id, request.subject_id
            )
            if not node_valid:
                raise RoadmapNodeMismatchError(
                    f"Roadmap node {request.roadmap_node_id} not found or does not belong to this subject."
                )

        return await self.repository.create_study_session(
            user_id=user_id,
            subject_id=request.subject_id,
            duration_minutes=request.duration_minutes,
            session_type=request.session_type,
            document_id=request.document_id,
            roadmap_node_id=request.roadmap_node_id,
            completed_at=request.completed_at,
        )

    async def list_sessions(
        self,
        user_id: uuid.UUID,
        subject_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StudySession]:
        return await self.repository.get_user_sessions(
            user_id=user_id,
            subject_id=subject_id,
            limit=limit,
            offset=offset,
        )

    async def delete_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        deleted = await self.repository.delete_study_session(session_id, user_id)
        if not deleted:
            raise StudySessionNotFoundError(
                f"Study session {session_id} not found or unauthorized for user."
            )
