from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_active_user
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
from app.modules.auth.service import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(
    req: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        return await auth_service.register_user(db, req)
    except EmailAlreadyExistsException as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate user and issue access token",
)
async def login(
    req: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        return await auth_service.authenticate_user(db, req)
    except InvalidCredentialsException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except AccountSuspendedException as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
) -> UserResponse:
    return UserResponse.model_validate(current_user)
