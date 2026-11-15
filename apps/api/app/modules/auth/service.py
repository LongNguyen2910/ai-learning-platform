from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.exceptions import (
    AccountSuspendedException,
    EmailAlreadyExistsException,
    InvalidCredentialsException,
)
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    DailyCheckinResponse,
    DeleteAccountRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.modules.auth.security import PasswordHasher, TokenManager

ALLOWED_AVATAR_TYPES: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_AVATAR_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MILESTONE_DAYS = (3, 7, 14, 30)


class AuthService:
    async def register_user(
        self, db: AsyncSession, req: UserRegisterRequest
    ) -> TokenResponse:
        existing = await db.scalar(select(User).where(User.email == req.email))
        if existing:
            raise EmailAlreadyExistsException()

        existing_any_user = await db.scalar(select(User.id).limit(1))
        initial_role = "admin" if existing_any_user is None else "user"

        hashed_password = PasswordHasher.hash(req.password)
        new_user = User(
            email=req.email,
            hashed_password=hashed_password,
            full_name=req.full_name,
            role=initial_role,
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

    async def update_profile(
        self, db: AsyncSession, user: User, req: UserUpdateRequest
    ) -> User:
        if "full_name" in req.model_fields_set or req.full_name is not None:
            user.full_name = req.full_name.strip() if req.full_name else None
        if "avatar_url" in req.model_fields_set:
            user.avatar_url = req.avatar_url.strip() if req.avatar_url else None
        if "equipped_milestone" in req.model_fields_set:
            if req.equipped_milestone is not None and (
                req.equipped_milestone not in MILESTONE_DAYS
                or req.equipped_milestone > (user.longest_streak or 0)
            ):
                raise ValueError("Milestone reward is not unlocked yet.")
            user.equipped_milestone = req.equipped_milestone
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def process_daily_checkin(
        self,
        db: AsyncSession,
        user: User,
        client_date: date | None = None,
    ) -> DailyCheckinResponse:
        server_today = datetime.now(timezone.utc).date()
        if client_date is not None and abs((client_date - server_today).days) <= 1:
            today = client_date
        else:
            today = server_today

        if user.last_checkin_date == today:
            return DailyCheckinResponse(
                user=UserResponse.model_validate(user),
                is_new_day_checkin=False,
                newly_unlocked_milestone=None,
                streak_reset=False,
            )

        if user.last_checkin_date == today - timedelta(days=1):
            user.current_streak = (user.current_streak or 0) + 1
            streak_reset = False
        else:
            streak_reset = bool(
                user.last_checkin_date is not None and (user.current_streak or 0) > 1
            )
            user.current_streak = 1

        user.total_checkin_days = (user.total_checkin_days or 0) + 1
        user.last_checkin_date = today

        newly_unlocked: int | None = None
        if user.current_streak > (user.longest_streak or 0):
            user.longest_streak = user.current_streak
            if user.current_streak in MILESTONE_DAYS:
                newly_unlocked = user.current_streak
                user.equipped_milestone = newly_unlocked

        if user.equipped_milestone is None:
            unlocked = [m for m in MILESTONE_DAYS if m <= (user.longest_streak or 0)]
            if unlocked:
                user.equipped_milestone = unlocked[-1]

        db.add(user)
        await db.commit()
        await db.refresh(user)

        return DailyCheckinResponse(
            user=UserResponse.model_validate(user),
            is_new_day_checkin=True,
            newly_unlocked_milestone=newly_unlocked,
            streak_reset=streak_reset,
        )

    async def upload_avatar(
        self,
        db: AsyncSession,
        user: User,
        filename: str | None,
        content_type: str | None,
        file_bytes: bytes,
    ) -> User:
        normalized_type = (content_type or "").lower().strip()
        ext = ALLOWED_AVATAR_TYPES.get(normalized_type)
        if not ext and filename:
            suffix = Path(filename).suffix.lower()
            if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                ext = ".jpg" if suffix == ".jpeg" else suffix

        if not ext:
            raise ValueError(
                "Invalid image format. Allowed formats: PNG, JPG, WEBP, GIF."
            )

        if not file_bytes:
            raise ValueError("Uploaded image file is empty.")

        if len(file_bytes) > MAX_AVATAR_SIZE_BYTES:
            raise ValueError("Avatar image size must not exceed 5 MB.")

        avatars_dir = Path(settings.UPLOAD_DIR) / "avatars"
        avatars_dir.mkdir(parents=True, exist_ok=True)

        # Remove old local avatar file if one exists
        if user.avatar_url and user.avatar_url.startswith("/api/v1/auth/avatars/"):
            old_name = user.avatar_url.rsplit("/", 1)[-1]
            old_path = avatars_dir / old_name
            if old_path.is_file():
                try:
                    old_path.unlink()
                except OSError:
                    pass

        safe_name = f"{user.id.hex}_{uuid.uuid4().hex[:8]}{ext}"
        target_path = avatars_dir / safe_name
        target_path.write_bytes(file_bytes)

        user.avatar_url = f"/api/v1/auth/avatars/{safe_name}"
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    async def change_password(
        self, db: AsyncSession, user: User, req: ChangePasswordRequest
    ) -> None:
        if not PasswordHasher.verify(req.current_password, user.hashed_password):
            raise InvalidCredentialsException("Current password is incorrect.")

        if req.current_password == req.new_password:
            raise ValueError("New password must be different from current password.")

        user.hashed_password = PasswordHasher.hash(req.new_password)
        db.add(user)
        await db.commit()

    async def delete_account(
        self, db: AsyncSession, user: User, req: DeleteAccountRequest
    ) -> None:
        if not PasswordHasher.verify(req.current_password, user.hashed_password):
            raise InvalidCredentialsException("Current password is incorrect.")

        await db.delete(user)
        await db.commit()

    async def toggle_role(self, db: AsyncSession, user: User) -> User:
        user.role = "user" if user.role == "admin" else "admin"
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


auth_service = AuthService()
