from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdminUserItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str | None = None
    avatar_url: str | None = None
    role: str
    is_active: bool
    daily_token_limit: int
    used_token_today: int
    total_tokens_used: int
    documents_count: int
    chat_sessions_count: int
    current_streak: int = 0
    longest_streak: int = 0
    last_checkin_date: date | None = None
    created_at: datetime


class AdminUsersSummary(BaseModel):
    total_users: int
    active_users: int
    suspended_users: int
    admin_users: int
    total_tokens_today: int
    total_tokens_all_time: int
    near_limit_users: int


class AdminUsersListResponse(BaseModel):
    summary: AdminUsersSummary
    users: list[AdminUserItem]


class AdminUpdateUserRequest(BaseModel):
    is_active: bool | None = None
    role: Literal["user", "admin"] | None = None
    daily_token_limit: int | None = Field(default=None, ge=0, le=10_000_000)
    reset_today_tokens: bool = False
