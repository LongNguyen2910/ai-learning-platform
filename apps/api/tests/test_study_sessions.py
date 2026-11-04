import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.study_sessions.models import StudySession


@pytest.fixture
def current_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="pomodoro_tester@example.com",
        hashed_password="hashed_pwd",
        full_name="Pomodoro Tester",
        role="user",
        is_active=True,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def auth_client(current_user: User, mock_db: AsyncMock):
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_create_study_session_duration_below_min_returns_422(auth_client: TestClient):
    payload = {
        "subject_id": str(uuid.uuid4()),
        "duration_minutes": 0,
    }
    resp = auth_client.post("/api/v1/study-sessions", json=payload)
    assert resp.status_code == 422


def test_create_study_session_duration_above_max_returns_422(auth_client: TestClient):
    payload = {
        "subject_id": str(uuid.uuid4()),
        "duration_minutes": 181,
    }
    resp = auth_client.post("/api/v1/study-sessions", json=payload)
    assert resp.status_code == 422


def test_create_study_session_future_completed_at_returns_422(auth_client: TestClient):
    payload = {
        "subject_id": str(uuid.uuid4()),
        "duration_minutes": 25,
        "completed_at": "2099-01-01T00:00:00Z",
    }
    resp = auth_client.post("/api/v1/study-sessions", json=payload)
    assert resp.status_code == 422
    assert "future" in resp.text.lower()


@patch("app.modules.study_sessions.service.StudySessionRepository.subject_exists_for_user")
def test_create_study_session_subject_not_found_returns_404(
    mock_subject_exists: AsyncMock, auth_client: TestClient
):
    mock_subject_exists.return_value = False
    payload = {
        "subject_id": str(uuid.uuid4()),
        "duration_minutes": 25,
    }
    resp = auth_client.post("/api/v1/study-sessions", json=payload)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@patch("app.modules.study_sessions.service.StudySessionRepository.subject_exists_for_user")
@patch("app.modules.study_sessions.service.StudySessionRepository.document_matches_user_and_subject")
def test_create_study_session_document_mismatch_returns_400(
    mock_doc_match: AsyncMock,
    mock_subject_exists: AsyncMock,
    auth_client: TestClient,
):
    mock_subject_exists.return_value = True
    mock_doc_match.return_value = False
    payload = {
        "subject_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "duration_minutes": 25,
    }
    resp = auth_client.post("/api/v1/study-sessions", json=payload)
    assert resp.status_code == 400
    assert "document" in resp.json()["detail"].lower()


@patch("app.modules.study_sessions.service.StudySessionRepository.subject_exists_for_user")
@patch("app.modules.study_sessions.service.StudySessionRepository.roadmap_node_matches_user_and_subject")
def test_create_study_session_roadmap_node_mismatch_returns_400(
    mock_node_match: AsyncMock,
    mock_subject_exists: AsyncMock,
    auth_client: TestClient,
):
    mock_subject_exists.return_value = True
    mock_node_match.return_value = False
    payload = {
        "subject_id": str(uuid.uuid4()),
        "roadmap_node_id": str(uuid.uuid4()),
        "duration_minutes": 45,
    }
    resp = auth_client.post("/api/v1/study-sessions", json=payload)
    assert resp.status_code == 400
    assert "roadmap node" in resp.json()["detail"].lower()


@patch("app.modules.study_sessions.service.StudySessionRepository.subject_exists_for_user")
@patch("app.modules.study_sessions.service.StudySessionRepository.create_study_session")
def test_create_study_session_success(
    mock_create: AsyncMock,
    mock_subject_exists: AsyncMock,
    auth_client: TestClient,
    current_user: User,
):
    mock_subject_exists.return_value = True
    subject_id = uuid.uuid4()
    session_id = uuid.uuid4()
    now = datetime.now(UTC)

    mock_create.return_value = StudySession(
        id=session_id,
        user_id=current_user.id,
        subject_id=subject_id,
        duration_minutes=25,
        session_type="pomodoro",
        completed_at=now,
    )

    payload = {
        "subject_id": str(subject_id),
        "duration_minutes": 25,
        "session_type": "pomodoro",
    }
    resp = auth_client.post("/api/v1/study-sessions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["id"] == str(session_id)
    assert data["user_id"] == str(current_user.id)
    assert data["duration_minutes"] == 25
    assert data["session_type"] == "pomodoro"


def test_create_study_session_unauthorized():
    with TestClient(app) as anonymous_client:
        payload = {
            "subject_id": str(uuid.uuid4()),
            "duration_minutes": 25,
        }
        resp = anonymous_client.post("/api/v1/study-sessions", json=payload)
        assert resp.status_code in (401, 403)


def test_post_unprefixed_api_study_sessions_returns_404(auth_client: TestClient):
    """Xac nhan duong dan khong co /v1 da bi go bo."""
    payload = {
        "subject_id": str(uuid.uuid4()),
        "duration_minutes": 25,
    }
    resp = auth_client.post("/api/study-sessions", json=payload)
    assert resp.status_code == 404


@patch("app.modules.study_sessions.service.StudySessionRepository.get_user_sessions")
def test_list_study_sessions_success(
    mock_get_sessions: AsyncMock, auth_client: TestClient, current_user: User
):
    """Kiem tra GET /api/v1/study-sessions tra ve danh sach phien hoc."""
    subject_id = uuid.uuid4()
    mock_get_sessions.return_value = [
        StudySession(
            id=uuid.uuid4(),
            user_id=current_user.id,
            subject_id=subject_id,
            duration_minutes=25,
            session_type="pomodoro",
            completed_at=datetime.now(UTC),
        ),
        StudySession(
            id=uuid.uuid4(),
            user_id=current_user.id,
            subject_id=subject_id,
            duration_minutes=50,
            session_type="deep_work",
            completed_at=datetime.now(UTC),
        ),
    ]

    resp = auth_client.get(f"/api/v1/study-sessions?subject_id={subject_id}&limit=10&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["duration_minutes"] == 25
    assert data[1]["session_type"] == "deep_work"


@patch("app.modules.study_sessions.service.StudySessionRepository.delete_study_session")
def test_delete_study_session_success(
    mock_delete: AsyncMock, auth_client: TestClient
):
    """Kiem tra DELETE /api/v1/study-sessions/{session_id} thanh cong tra ve 204."""
    mock_delete.return_value = True
    session_id = uuid.uuid4()
    resp = auth_client.delete(f"/api/v1/study-sessions/{session_id}")
    assert resp.status_code == 204


@patch("app.modules.study_sessions.service.StudySessionRepository.delete_study_session")
def test_delete_study_session_not_found_returns_404(
    mock_delete: AsyncMock, auth_client: TestClient
):
    """Kiem tra DELETE /api/v1/study-sessions/{session_id} khong tim thay tra ve 404."""
    mock_delete.return_value = False
    session_id = uuid.uuid4()
    resp = auth_client.delete(f"/api/v1/study-sessions/{session_id}")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


