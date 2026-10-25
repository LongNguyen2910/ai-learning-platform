from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.exceptions import (
    AccountSuspendedException,
    EmailAlreadyExistsException,
    InvalidCredentialsException,
)
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.modules.auth.security import PasswordHasher, TokenManager


class AuthService:
    async def register_user(
        self, db: AsyncSession, req: UserRegisterRequest
    ) -> TokenResponse:
        existing = await db.scalar(select(User).where(User.email == req.email))
        if existing:
            raise EmailAlreadyExistsException()

        hashed_password = PasswordHasher.hash(req.password)
        new_user = User(
            email=req.email,
            hashed_password=hashed_password,
            full_name=req.full_name,
            role="user",
            is_active=True,
            daily_token_limit=50000,
            used_token_today=0,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        token = TokenManager.create_access_token(
            {"sub": str(new_user.id), "email": new_user.email, "role": new_user.role}
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(new_user),
        )

    async def authenticate_user(
        self, db: AsyncSession, req: UserLoginRequest
    ) -> TokenResponse:
        user = await db.scalar(select(User).where(User.email == req.email))
        if not user:
            raise InvalidCredentialsException()

        if not PasswordHasher.verify(req.password, user.hashed_password):
            raise InvalidCredentialsException()

        if not user.is_active:
            raise AccountSuspendedException()

        token = TokenManager.create_access_token(
            {"sub": str(user.id), "email": user.email, "role": user.role}
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user=UserResponse.model_validate(user),
        )

    async def get_user_by_id(
        self, db: AsyncSession, user_id: UUID
    ) -> User | None:
        return await db.scalar(select(User).where(User.id == user_id))


auth_service = AuthService()
