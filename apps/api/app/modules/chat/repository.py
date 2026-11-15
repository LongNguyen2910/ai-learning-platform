"""Persistence layer cho ChatSession/ChatMessage.

Mỗi thao tác mở một AsyncSession ngắn hạn từ session factory: an toàn khi gọi bên trong
generator SSE (chạy sau khi request dependency đã kết thúc).
"""

import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import AsyncSessionLocal
from app.modules.analytics.models import TokenUsageLog
from app.modules.auth.models import User
from app.modules.chat.models import ChatMessage, ChatSession
from app.modules.documents.models import Document

SENDER_USER = "user"
SENDER_ASSISTANT = "assistant"


class ChatRepository:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] | None = None
    ) -> None:
        self.session_factory = session_factory or AsyncSessionLocal

    async def get_document(self, document_id: uuid.UUID) -> Document | None:
        async with self.session_factory() as db:
            return await db.scalar(select(Document).where(Document.id == document_id))

    async def ensure_document_from_metadata(
        self, document_id: uuid.UUID, user_id: uuid.UUID, meta: Any
    ) -> Document:
        async with self.session_factory() as db:
            existing = await db.scalar(select(Document).where(Document.id == document_id))
            if existing is not None:
                return existing
            doc = Document(
                id=document_id,
                user_id=user_id,
                title=meta.title,
                file_path=meta.file_path,
                file_type="pdf",
                file_size_kb=meta.file_size_kb,
                total_pages=meta.total_pages,
                status=meta.status,
                error_message=meta.error_message,
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            return doc

    async def create_session(
        self, user_id: uuid.UUID, document_id: uuid.UUID, title: str
    ) -> ChatSession:
        async with self.session_factory() as db:
            session = ChatSession(user_id=user_id, document_id=document_id, title=title)
            db.add(session)
            await db.commit()
            await db.refresh(session)
            return session

    async def get_session(self, session_id: uuid.UUID) -> ChatSession | None:
        async with self.session_factory() as db:
            return await db.scalar(select(ChatSession).where(ChatSession.id == session_id))

    async def get_session_user_quota(self, session_id: uuid.UUID) -> tuple[int, int]:
        """Trả về `(used_token_today, daily_token_limit)` của chủ phiên chat."""
        async with self.session_factory() as db:
            row = (
                await db.execute(
                    select(User.used_token_today, User.daily_token_limit)
                    .join(ChatSession, ChatSession.user_id == User.id)
                    .where(ChatSession.id == session_id)
                )
            ).first()
            if row is None:
                return 0, 0
            return int(row[0] or 0), int(row[1] or 0)

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        async with self.session_factory() as db:
            session = await db.scalar(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            if session is None:
                return False
            await db.delete(session)
            await db.commit()
            return True

    async def list_sessions(
        self,
        user_id: uuid.UUID,
        document_id: uuid.UUID | None = None,
        limit: int = 20,
    ) -> list[ChatSession]:
        """Trả về danh sách phiên hội thoại của học viên (mới nhất trước)."""
        async with self.session_factory() as db:
            stmt = select(ChatSession).where(ChatSession.user_id == user_id)
            if document_id is not None:
                stmt = stmt.where(ChatSession.document_id == document_id)
            stmt = stmt.order_by(desc(ChatSession.created_at), desc(ChatSession.id)).limit(
                limit
            )
            return list((await db.scalars(stmt)).all())

    async def list_recent_messages(
        self, session_id: uuid.UUID, limit: int = 20
    ) -> list[ChatMessage]:
        """Trả về `limit` tin nhắn gần nhất theo thứ tự thời gian tăng dần."""
        async with self.session_factory() as db:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(desc(ChatMessage.created_at), desc(ChatMessage.id))
                .limit(limit)
            )
            rows = list((await db.scalars(stmt)).all())
        rows.reverse()
        return rows

    async def add_message(
        self,
        session_id: uuid.UUID,
        sender: str,
        content: str,
        socratic_tier: int = 0,
        citations: list[dict[str, Any]] | None = None,
        token_count: int = 0,
        mode: str = "standard",
        mode_metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        async with self.session_factory() as db:
            message = ChatMessage(
                session_id=session_id,
                sender=sender,
                content=content,
                mode=mode,
                mode_metadata=mode_metadata or {},
                socratic_tier=socratic_tier,
                citations=citations or [],
                token_count=token_count,
            )
            db.add(message)

            if token_count > 0:
                session = await db.scalar(
                    select(ChatSession).where(ChatSession.id == session_id)
                )
                if session is not None:
                    user = await db.scalar(
                        select(User).where(User.id == session.user_id)
                    )
                    if user is not None:
                        user.used_token_today = int(user.used_token_today or 0) + token_count
                        db.add(user)
                    db.add(
                        TokenUsageLog(
                            user_id=session.user_id,
                            action_type=f"chat_{sender}",
                            input_tokens=token_count if sender == SENDER_USER else 0,
                            output_tokens=token_count if sender != SENDER_USER else 0,
                            total_tokens=token_count,
                        )
                    )

            await db.commit()
            await db.refresh(message)
            return message


chat_repository = ChatRepository()
