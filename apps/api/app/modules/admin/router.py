from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.admin.schemas import (
    AdminUpdateUserRequest,
    AdminUserItem,
    AdminUsersListResponse,
)
from app.modules.admin.service import AdminUserNotFoundError, admin_user_service
from app.modules.auth.dependencies import require_role
from app.modules.auth.models import User
from app.modules.auth.schemas import MessageResponse

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get(
    "/users",
    response_model=AdminUsersListResponse,
    status_code=status.HTTP_200_OK,
    summary="List users with AI token usage statistics (Admin only)",
)
async def list_admin_users(
    current_admin: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = Query(default=None, max_length=255),
    status_filter: Literal["all", "active", "suspended", "admin"] = Query(
        default="all"
    ),
    sort_by: Literal["created_at", "tokens_today", "tokens_total"] = Query(
        default="created_at"
    ),
) -> AdminUsersListResponse:
    return await admin_user_service.list_users_with_stats(
        db=db,
        search=search,
        status_filter=status_filter,
        sort_by=sort_by,
    )


@router.patch(
    "/users/{user_id}",
    response_model=AdminUserItem,
    status_code=status.HTTP_200_OK,
    summary="Update user active status, role, or daily token limit (Admin only)",
)
async def update_admin_user(
    user_id: UUID,
    req: AdminUpdateUserRequest,
    current_admin: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserItem:
    try:
        return await admin_user_service.update_user(
            db=db,
            current_admin=current_admin,
            target_user_id=user_id,
            req=req,
        )
    except AdminUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/users/{user_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Permanently delete a user account and cascaded data (Admin only)",
)
async def delete_admin_user(
    user_id: UUID,
    current_admin: Annotated[User, Depends(require_role("admin"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    try:
        await admin_user_service.delete_user(
            db=db,
            current_admin=current_admin,
            target_user_id=user_id,
        )
        return MessageResponse(message="User account deleted permanently.")
    except AdminUserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
