import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.modules.auth.models import User
    from app.modules.chat.models import ChatSession
    from app.modules.flashcards.models import FlashcardDeck
    from app.modules.quizzes.models import Quiz
    from app.modules.roadmaps.models import Roadmap, RoadmapNode
    from app.modules.study_sessions.models import StudySession


class Subject(Base):
    __tablename__ = "subjects"

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
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    color_hex: Mapped[str] = mapped_column(
        String(10), default="#4F46E5", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subjects")
    documents: Mapped[List["Document"]] = relationship(
        "Document", back_populates="subject"
    )
    roadmaps: Mapped[List["Roadmap"]] = relationship(
        "Roadmap", back_populates="subject", cascade="all, delete-orphan"
    )
    study_sessions: Mapped[List["StudySession"]] = relationship(
        "StudySession", back_populates="subject"
    )
    flashcard_decks: Mapped[List["FlashcardDeck"]] = relationship(
        "FlashcardDeck", back_populates="subject", cascade="all, delete-orphan"
    )
    quizzes: Mapped[List["Quiz"]] = relationship(
        "Quiz", back_populates="subject"
    )


class Document(Base):
    __tablename__ = "documents"

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
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    file_size_kb: Mapped[int] = mapped_column(Integer, nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="uploading", nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_documents_user_id", "user_id"),
        Index("idx_documents_subject_id", "subject_id"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="documents")
    subject: Mapped[Optional["Subject"]] = relationship(
        "Subject", back_populates="documents"
    )
    roadmap_nodes: Mapped[List["RoadmapNode"]] = relationship(
        "RoadmapNode", back_populates="document"
    )
    study_sessions: Mapped[List["StudySession"]] = relationship(
        "StudySession", back_populates="document"
    )
    chat_sessions: Mapped[List["ChatSession"]] = relationship(
        "ChatSession", back_populates="document", cascade="all, delete-orphan"
    )
    flashcard_decks: Mapped[List["FlashcardDeck"]] = relationship(
        "FlashcardDeck", back_populates="document"
    )
    quizzes: Mapped[List["Quiz"]] = relationship(
        "Quiz", back_populates="document", cascade="all, delete-orphan"
    )
