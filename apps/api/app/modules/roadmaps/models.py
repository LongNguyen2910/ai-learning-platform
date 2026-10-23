import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.documents.models import Document, Subject
    from app.modules.study_sessions.models import StudySession


class Roadmap(Base):
    __tablename__ = "roadmaps"

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
        index=True,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subjects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    available_hours_per_day: Mapped[float] = mapped_column(
        Float, default=2.0, nullable=False
    )
    progress_percentage: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="roadmaps")
    subject: Mapped["Subject"] = relationship("Subject", back_populates="roadmaps")
    nodes: Mapped[List["RoadmapNode"]] = relationship(
        "RoadmapNode", back_populates="roadmap", cascade="all, delete-orphan"
    )


class RoadmapNode(Base):
    __tablename__ = "roadmap_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    roadmap_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmaps.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_node_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    target_page_start: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    target_page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_minutes: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False
    )
    is_unlocked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_roadmap_nodes_roadmap_id", "roadmap_id"),
    )

    # Relationships
    roadmap: Mapped["Roadmap"] = relationship("Roadmap", back_populates="nodes")
    parent_node: Mapped[Optional["RoadmapNode"]] = relationship(
        "RoadmapNode",
        remote_side=[id],
        back_populates="child_nodes",
    )
    child_nodes: Mapped[List["RoadmapNode"]] = relationship(
        "RoadmapNode",
        back_populates="parent_node",
        cascade="all, delete-orphan",
    )
    document: Mapped[Optional["Document"]] = relationship(
        "Document", back_populates="roadmap_nodes"
    )
    study_sessions: Mapped[List["StudySession"]] = relationship(
        "StudySession", back_populates="roadmap_node"
    )
