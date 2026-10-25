from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class UserRegisterRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(default=None, max_length=100)


class UserLoginRequest(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN, max_length=255)
    password: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    daily_token_limit: int
    used_token_today: int
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class TokenPayload(BaseModel):
    sub: str
    email: str
    role: str
    exp: int
