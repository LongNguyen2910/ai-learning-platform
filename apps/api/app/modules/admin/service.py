from datetime import datetime, time, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.admin.schemas import (
    AdminUpdateUserRequest,
    AdminUserItem,
    AdminUsersListResponse,
    AdminUsersSummary,
)
from app.modules.analytics.models import TokenUsageLog
from app.modules.auth.models import User
from app.modules.chat.models import ChatMessage, ChatSession
from app.modules.documents.models import Document

ADMIN_RESET_ACTION = "admin_reset_today"


class AdminUserNotFoundError(Exception):
    pass


class AdminUserService:
    async def _build_user_items(
        self,
        db: AsyncSession,
        users: list[User],
    ) -> list[AdminUserItem]:
        if not users:
            return []

        user_ids = [u.id for u in users]
        today_start = datetime.combine(
            datetime.now(timezone.utc).date(),
            time.min,
            tzinfo=timezone.utc,
        )

        # Latest same-day reset timestamp per user (if admin reset today's counter)
        reset_rows = (
            await db.execute(
                select(
                    TokenUsageLog.user_id,
                    func.max(TokenUsageLog.created_at).label("last_reset_at"),
                )
                .where(
                    TokenUsageLog.user_id.in_(user_ids),
                    TokenUsageLog.action_type == ADMIN_RESET_ACTION,
                    TokenUsageLog.created_at >= today_start,
                )
                .group_by(TokenUsageLog.user_id)
            )
        ).all()
        reset_cutoff_by_user: dict[UUID, datetime] = {
            row[0]: row[1] for row in reset_rows if row[0] is not None and row[1] is not None
        }

        # Aggregate chat session counts and total chat message tokens
        chat_totals_rows = (
            await db.execute(
                select(
                    ChatSession.user_id,
                    func.count(func.distinct(ChatSession.id)).label("sessions_count"),
                    func.coalesce(func.sum(ChatMessage.token_count), 0).label("chat_tokens_total"),
                    func.coalesce(
                        func.sum(
                            case(
                                (ChatMessage.created_at >= today_start, ChatMessage.token_count),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("chat_tokens_today_raw"),
                )
                .select_from(ChatSession)
                .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
                .where(ChatSession.user_id.in_(user_ids))
                .group_by(ChatSession.user_id)
            )
        ).all()

        sessions_count_map: dict[UUID, int] = {}
        chat_tokens_total_map: dict[UUID, int] = {}
        chat_tokens_today_map: dict[UUID, int] = {}
        for row in chat_totals_rows:
            uid = row[0]
            sessions_count_map[uid] = int(row[1] or 0)
            chat_tokens_total_map[uid] = int(row[2] or 0)
            chat_tokens_today_map[uid] = int(row[3] or 0)

        # Recompute post-reset today chat tokens only for users who were reset today
        if reset_cutoff_by_user:
            for uid, cutoff in reset_cutoff_by_user.items():
                post_reset_tokens = await db.scalar(
                    select(func.coalesce(func.sum(ChatMessage.token_count), 0))
                    .select_from(ChatMessage)
                    .join(ChatSession, ChatSession.id == ChatMessage.session_id)
                    .where(
                        ChatSession.user_id == uid,
                        ChatMessage.created_at > cutoff,
                    )
                )
                chat_tokens_today_map[uid] = int(post_reset_tokens or 0)

        # Aggregate TokenUsageLog totals per user
        log_rows = (
            await db.execute(
                select(
                    TokenUsageLog.user_id,
                    func.coalesce(func.sum(TokenUsageLog.total_tokens), 0).label("log_tokens_total"),
                )
                .where(TokenUsageLog.user_id.in_(user_ids))
                .group_by(TokenUsageLog.user_id)
            )
        ).all()
        log_tokens_total_map: dict[UUID, int] = {
            row[0]: int(row[1] or 0) for row in log_rows if row[0] is not None
        }

        # Aggregate Document counts per user
        doc_rows = (
            await db.execute(
                select(
                    Document.user_id,
                    func.count(Document.id).label("documents_count"),
                )
                .where(Document.user_id.in_(user_ids))
                .group_by(Document.user_id)
            )
        ).all()
        documents_count_map: dict[UUID, int] = {
            row[0]: int(row[1] or 0) for row in doc_rows if row[0] is not None
        }

        items: list[AdminUserItem] = []
        for user in users:
            chat_today = chat_tokens_today_map.get(user.id, 0)
            chat_total = chat_tokens_total_map.get(user.id, 0)
            log_total = log_tokens_total_map.get(user.id, 0)

            used_today = max(int(user.used_token_today or 0), chat_today)
            total_used = max(chat_total, log_total, used_today)

            items.append(
                AdminUserItem(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    avatar_url=user.avatar_url,
                    role=user.role,
                    is_active=user.is_active,
                    daily_token_limit=int(user.daily_token_limit or 0),
                    used_token_today=used_today,
                    total_tokens_used=total_used,
                    documents_count=documents_count_map.get(user.id, 0),
                    chat_sessions_count=sessions_count_map.get(user.id, 0),
                    current_streak=int(user.current_streak or 0),
                    longest_streak=int(user.longest_streak or 0),
                    last_checkin_date=user.last_checkin_date,
                    created_at=user.created_at,
                )
            )

        return items

    async def list_users_with_stats(
        self,
        db: AsyncSession,
        search: str | None = None,
        status_filter: str = "all",
        sort_by: str = "created_at",
    ) -> AdminUsersListResponse:
        all_users = list((await db.scalars(select(User))).all())
        all_items = await self._build_user_items(db, all_users)

        summary = AdminUsersSummary(
            total_users=len(all_items),
            active_users=sum(1 for u in all_items if u.is_active),
            suspended_users=sum(1 for u in all_items if not u.is_active),
            admin_users=sum(1 for u in all_items if u.role == "admin"),
            total_tokens_today=sum(u.used_token_today for u in all_items),
            total_tokens_all_time=sum(u.total_tokens_used for u in all_items),
            near_limit_users=sum(
                1
                for u in all_items
                if u.daily_token_limit > 0
                and u.used_token_today >= 0.8 * u.daily_token_limit
            ),
        )

        filtered = all_items
        if search and search.strip():
            q = search.strip().lower()
            filtered = [
                u
                for u in filtered
                if q in u.email.lower()
                or (u.full_name and q in u.full_name.lower())
            ]

        if status_filter == "active":
            filtered = [u for u in filtered if u.is_active]
        elif status_filter == "suspended":
            filtered = [u for u in filtered if not u.is_active]
        elif status_filter == "admin":
            filtered = [u for u in filtered if u.role == "admin"]

        if sort_by == "tokens_today":
            filtered.sort(
                key=lambda u: (u.used_token_today, u.total_tokens_used, u.created_at),
                reverse=True,
            )
        elif sort_by == "tokens_total":
            filtered.sort(
                key=lambda u: (u.total_tokens_used, u.used_token_today, u.created_at),
                reverse=True,
            )
        else:
            filtered.sort(key=lambda u: u.created_at, reverse=True)

        return AdminUsersListResponse(summary=summary, users=filtered)

    async def update_user(
        self,
        db: AsyncSession,
        current_admin: User,
        target_user_id: UUID,
        req: AdminUpdateUserRequest,
    ) -> AdminUserItem:
        target_user = await db.scalar(select(User).where(User.id == target_user_id))
        if target_user is None:
            raise AdminUserNotFoundError("User not found.")

        if target_user.id == current_admin.id:
            if req.is_active is False:
                raise ValueError("Cannot suspend your own Administrator account.")
            if req.role is not None and req.role != "admin":
                raise ValueError("Cannot demote your own Administrator account.")

        if target_user.role == "admin":
            if req.role is not None and req.role != "admin":
                raise ValueError("Cannot demote another Administrator account.")
            if req.is_active is False:
                raise ValueError("Cannot suspend an Administrator account.")

        effective_is_active = (
            req.is_active if req.is_active is not None else bool(target_user.is_active)
        )
        if req.role == "admin" and not effective_is_active:
            raise ValueError(
                "Cannot promote a suspended account to Admin. Please unlock the account first."
            )

        if req.is_active is not None:
            target_user.is_active = req.is_active
        if req.role is not None:
            target_user.role = req.role
        if req.daily_token_limit is not None:
            target_user.daily_token_limit = req.daily_token_limit
        if req.reset_today_tokens:
            target_user.used_token_today = 0
            db.add(
                TokenUsageLog(
                    user_id=target_user.id,
                    action_type=ADMIN_RESET_ACTION,
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                )
            )

        db.add(target_user)
        await db.commit()
        await db.refresh(target_user)

        items = await self._build_user_items(db, [target_user])
        return items[0]

    async def delete_user(
        self,
        db: AsyncSession,
        current_admin: User,
        target_user_id: UUID,
    ) -> None:
        target_user = await db.scalar(select(User).where(User.id == target_user_id))
        if target_user is None:
            raise AdminUserNotFoundError("User not found.")

        if target_user.id == current_admin.id:
            raise ValueError("Cannot delete your own Administrator account.")

        if target_user.role == "admin":
            raise ValueError("Cannot delete an Administrator account.")

        if target_user.avatar_url and target_user.avatar_url.startswith(
            "/api/v1/auth/avatars/"
        ):
            avatar_name = target_user.avatar_url.rsplit("/", 1)[-1]
            avatar_path = Path(settings.UPLOAD_DIR) / "avatars" / avatar_name
            if avatar_path.is_file():
                try:
                    avatar_path.unlink()
                except OSError:
                    pass

        await db.delete(target_user)
        await db.commit()


admin_user_service = AdminUserService()
