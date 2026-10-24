import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.database import AsyncSessionLocal, engine
from app.main import app
from app.modules.auth.dependencies import require_role
from app.modules.auth.exceptions import InvalidTokenException
from app.modules.auth.models import User
from app.modules.auth.security import PasswordHasher, TokenManager


@pytest_asyncio.fixture(autouse=True)
async def cleanup_engine():
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


def test_password_hasher_basics_and_salting():
    raw = "SuperSecret123!"
    hash1 = PasswordHasher.hash(raw)
    hash2 = PasswordHasher.hash(raw)

    # Must produce different hashes due to unique salts
    assert hash1 != hash2
    assert PasswordHasher.verify(raw, hash1) is True
    assert PasswordHasher.verify(raw, hash2) is True
    assert PasswordHasher.verify("WrongPass123!", hash1) is False
    assert PasswordHasher.verify(raw, "invalid_hash_string") is False
    assert PasswordHasher.verify(raw, "") is False


def test_password_hasher_unicode():
    raw = "MậtKhẩu_Siêu_Bảo_Mật_#123@!💡"
    hashed = PasswordHasher.hash(raw)
    assert PasswordHasher.verify(raw, hashed) is True
    assert PasswordHasher.verify("SaiMatKhau", hashed) is False


def test_token_manager_claims_and_decoding():
    user_id = str(uuid.uuid4())
    data = {"sub": user_id, "email": "test@example.com", "role": "user"}
    token = TokenManager.create_access_token(data)
    assert isinstance(token, str)

    payload = TokenManager.decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["email"] == data["email"]
    assert payload["role"] == "user"
    assert "exp" in payload
    assert "iat" in payload


def test_token_manager_expired_and_tampered():
    data = {"sub": str(uuid.uuid4()), "email": "test@example.com", "role": "user"}
    # Token expired 10 seconds ago
    expired_token = TokenManager.create_access_token(
        data, expires_delta=timedelta(seconds=-10)
    )
    with pytest.raises(InvalidTokenException):
        TokenManager.decode_access_token(expired_token)

    # Tampered token
    valid_token = TokenManager.create_access_token(data)
    tampered = valid_token[:-4] + "abcd"
    with pytest.raises(InvalidTokenException):
        TokenManager.decode_access_token(tampered)

    # Garbage token string
    with pytest.raises(InvalidTokenException):
        TokenManager.decode_access_token("not.a.valid.jwt")


@pytest.mark.asyncio
async def test_auth_endpoints_lifecycle(async_client):
    test_email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    password = "ValidPassword123!"

    # 1. Register
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": test_email,
            "password": password,
            "full_name": "Nguyen Van A",
        },
    )
    assert reg_resp.status_code == 201, reg_resp.text
    reg_data = reg_resp.json()
    assert "access_token" in reg_data
    assert reg_data["token_type"] == "bearer"
    assert reg_data["user"]["email"] == test_email
    assert reg_data["user"]["full_name"] == "Nguyen Van A"
    assert reg_data["user"]["role"] == "user"
    assert reg_data["user"]["is_active"] is True
    assert reg_data["user"]["daily_token_limit"] == 50000
    assert reg_data["user"]["used_token_today"] == 0
    assert "hashed_password" not in reg_data["user"]

    token = reg_data["access_token"]

    # 2. Register Duplicate Email -> 400
    dup_resp = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": test_email,
            "password": password,
        },
    )
    assert dup_resp.status_code == 400
    assert "Email already registered" in dup_resp.json()["detail"]

    # 3. Login Valid -> 200
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": test_email,
            "password": password,
        },
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert "access_token" in login_data
    assert login_data["user"]["email"] == test_email

    # 4. Login Invalid Password -> 401
    bad_pass_resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": test_email,
            "password": "WrongPassword!",
        },
    )
    assert bad_pass_resp.status_code == 401
    assert "WWW-Authenticate" in bad_pass_resp.headers

    # 5. Login Non-existent User -> 401
    bad_user_resp = await async_client.post(
        "/api/v1/auth/login",
        json={
            "email": "non_existent_999@example.com",
            "password": password,
        },
    )
    assert bad_user_resp.status_code == 401

    # 6. GET /me with Token -> 200
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["email"] == test_email
    assert me_data["full_name"] == "Nguyen Van A"

    # 7. GET /me without Token -> 401
    unauth_resp = await async_client.get("/api/v1/auth/me")
    assert unauth_resp.status_code == 401


@pytest.mark.asyncio
async def test_register_validation_errors(async_client):
    # Invalid email formats
    for bad_email in ["notanemail", "user@", "@domain.com", "user space@domain.com"]:
        res = await async_client.post(
            "/api/v1/auth/register",
            json={"email": bad_email, "password": "Password123!"},
        )
        assert res.status_code == 422, f"Expected 422 for bad email: {bad_email}"

    # Password too short (< 8 chars)
    short_pass_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "valid@example.com", "password": "short"},
    )
    assert short_pass_res.status_code == 422

    # Missing fields
    missing_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "valid@example.com"},
    )
    assert missing_res.status_code == 422


@pytest.mark.asyncio
async def test_account_suspended_lifecycle(async_client):
    test_email = f"suspended_{uuid.uuid4().hex[:8]}@example.com"
    password = "ValidPassword123!"

    # 1. Register active user
    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"email": test_email, "password": password},
    )
    assert reg_resp.status_code == 201
    token = reg_resp.json()["access_token"]

    # 2. Deactivate user in database (is_active = False)
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.email == test_email))
        assert user is not None
        user.is_active = False
        await session.commit()

    # 3. Attempt Login -> 403 Forbidden
    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": test_email, "password": password},
    )
    assert login_resp.status_code == 403
    assert "suspended" in login_resp.json()["detail"].lower()

    # 4. Attempt GET /me with old token -> 403 Forbidden
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 403
    assert "suspended" in me_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_protected_routes_token_validation(async_client):
    # Expired token -> 401
    user_id = str(uuid.uuid4())
    expired_token = TokenManager.create_access_token(
        {"sub": user_id, "email": "test@example.com", "role": "user"},
        expires_delta=timedelta(seconds=-10),
    )
    res_expired = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res_expired.status_code == 401

    # Corrupted token -> 401
    res_corrupted = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.valid.token"},
    )
    assert res_corrupted.status_code == 401

    # Token with missing 'sub' claim -> 401
    token_missing_sub = TokenManager.create_access_token(
        {"email": "nosub@example.com", "role": "user"}
    )
    res_nosub = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_missing_sub}"},
    )
    assert res_nosub.status_code == 401


@pytest.mark.asyncio
async def test_require_role_checker():
    # User with role 'user'
    regular_user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        role="user",
        is_active=True,
    )
    # Admin checker rejects regular user
    admin_checker = require_role(["admin"])
    with pytest.raises(HTTPException) as exc_info:
        await admin_checker(current_user=regular_user)
    assert exc_info.value.status_code == 403
    assert "Insufficient permissions" in exc_info.value.detail

    # User checker permits regular user
    user_checker = require_role(["user", "admin"])
    checked_user = await user_checker(current_user=regular_user)
    assert checked_user == regular_user
