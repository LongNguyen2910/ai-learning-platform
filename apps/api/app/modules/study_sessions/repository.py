import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.documents.models import Document, Subject
from app.modules.roadmaps.models import Roadmap, RoadmapNode
from app.modules.study_sessions.models import StudySession


class StudySessionRepository:
    """Database persistence layer for StudySession module."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def subject_exists_for_user(
        self, subject_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        stmt = (
            select(Subject.id)
            .where(Subject.id == subject_id, Subject.user_id == user_id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def document_matches_user_and_subject(
        self, document_id: uuid.UUID, user_id: uuid.UUID, subject_id: uuid.UUID
    ) -> bool:
        stmt = (
            select(Document.id)
            .where(
                Document.id == document_id,
                Document.user_id == user_id,
                Document.subject_id == subject_id,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def roadmap_node_matches_user_and_subject(
        self, roadmap_node_id: uuid.UUID, user_id: uuid.UUID, subject_id: uuid.UUID
    ) -> bool:
        stmt = (
            select(RoadmapNode.id)
            .join(Roadmap, Roadmap.id == RoadmapNode.roadmap_id)
            .where(
                RoadmapNode.id == roadmap_node_id,
                Roadmap.user_id == user_id,
                Roadmap.subject_id == subject_id,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_study_session(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID,
        duration_minutes: int,
        session_type: str = "pomodoro",
        document_id: Optional[uuid.UUID] = None,
        roadmap_node_id: Optional[uuid.UUID] = None,
        completed_at: Optional[datetime] = None,
    ) -> StudySession:
        study_session = StudySession(
            id=uuid.uuid4(),
            user_id=user_id,
            subject_id=subject_id,
            document_id=document_id,
            roadmap_node_id=roadmap_node_id,
            duration_minutes=duration_minutes,
            session_type=session_type,
        )
        if completed_at is not None:
            study_session.completed_at = completed_at

        try:
            self.session.add(study_session)
            await self.session.commit()
            await self.session.refresh(study_session)
            return study_session
        except Exception:
            await self.session.rollback()
            raise

    async def get_user_sessions(
        self,
        user_id: uuid.UUID,
        subject_id: Optional[uuid.UUID] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StudySession]:
        stmt = (
            select(StudySession)
            .where(StudySession.user_id == user_id)
            .order_by(StudySession.completed_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if subject_id is not None:
            stmt = stmt.where(StudySession.subject_id == subject_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_study_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> bool:
        stmt = (
            select(StudySession)
            .where(
                StudySession.id == session_id,
                StudySession.user_id == user_id,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        target = result.scalar_one_or_none()
        if not target:
            return False

        try:
            await self.session.delete(target)
            await self.session.commit()
            return True
        except Exception:
            await self.session.rollback()
            raise
