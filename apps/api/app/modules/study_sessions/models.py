import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.documents.models import Document, Subject
    from app.modules.roadmaps.models import RoadmapNode


class StudySession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="SET NULL"),
        nullable=True,
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    roadmap_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmap_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    session_type: Mapped[str] = mapped_column(
        String(20), default="pomodoro", nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_study_sessions_user_date", "user_id", "completed_at"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="study_sessions")
    subject: Mapped[Optional["Subject"]] = relationship(
        "Subject", back_populates="study_sessions"
    )
    document: Mapped[Optional["Document"]] = relationship(
        "Document", back_populates="study_sessions"
    )
    roadmap_node: Mapped[Optional["RoadmapNode"]] = relationship(
        "RoadmapNode", back_populates="study_sessions"
    )
