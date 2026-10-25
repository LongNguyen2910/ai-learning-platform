from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.modules.auth.exceptions import InvalidTokenException


class PasswordHasher:
    @staticmethod
    def hash(password: str) -> str:
        salt = bcrypt.gensalt()
        # Truncate to 72 bytes safe limit for bcrypt
        pwd_bytes = password.encode("utf-8")[:72]
        return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

    @staticmethod
    def verify(plain_password: str, hashed_password: str) -> bool:
        try:
            pwd_bytes = plain_password.encode("utf-8")[:72]
            hashed_bytes = hashed_password.encode("utf-8")
            return bcrypt.checkpw(pwd_bytes, hashed_bytes)
        except (ValueError, TypeError):
            return False


class TokenManager:
    @staticmethod
    def create_access_token(
        data: dict[str, Any], expires_delta: timedelta | None = None
    ) -> str:
        to_encode = data.copy()
        now = datetime.now(UTC)
        expire = now + (
            expires_delta
            if expires_delta is not None
            else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        to_encode.update({"exp": expire, "iat": now})
        return jwt.encode(
            to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
        )

    @staticmethod
    def decode_access_token(token: str) -> dict[str, Any]:
        try:
            return jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
            )
        except JWTError as exc:
            raise InvalidTokenException("Invalid or expired token") from exc
