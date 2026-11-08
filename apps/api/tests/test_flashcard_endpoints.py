import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.flashcards.models import Flashcard


@pytest.fixture
def current_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="learner@example.com",
        hashed_password="hashed_pwd",
        full_name="Flashcard Learner",
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


@pytest.fixture
def unauth_client():
    with TestClient(app) as test_client:
        yield test_client


def test_review_endpoint_unauthorized(unauth_client: TestClient):
    card_id = uuid.uuid4()
    resp = unauth_client.post(
        f"/api/v1/flashcards/{card_id}/review",
        json={"rating": 5},
    )
    assert resp.status_code == 401


def test_review_endpoint_validation_error(auth_client: TestClient):
    card_id = uuid.uuid4()

    # Rating > 5
    resp = auth_client.post(
        f"/api/v1/flashcards/{card_id}/review",
        json={"rating": 6},
    )
    assert resp.status_code == 422

    # Rating < 0
    resp = auth_client.post(
        f"/api/v1/flashcards/{card_id}/review",
        json={"rating": -1},
    )
    assert resp.status_code == 422


def test_review_endpoint_flashcard_not_found(auth_client: TestClient, mock_db: AsyncMock):
    card_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    resp = auth_client.post(
        f"/api/v1/flashcards/{card_id}/review",
        json={"rating": 4},
    )
    assert resp.status_code == 404
    assert f"Flashcard with id {card_id} not found" in resp.json()["detail"]


def test_review_endpoint_success_progression(
    auth_client: TestClient,
    current_user: User,
    mock_db: AsyncMock,
):
    card_id = uuid.uuid4()
    deck_id = uuid.uuid4()
    today = date(2026, 11, 8)

    mock_card = Flashcard(
        id=card_id,
        deck_id=deck_id,
        user_id=current_user.id,
        front_text="What is SM-2?",
        back_text="Spaced repetition algorithm",
        repetition_number=1,
        easiness_factor=2.5,
        interval_days=1,
        due_date=today,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_card
    mock_db.execute.return_value = mock_result

    resp = auth_client.post(
        f"/api/v1/flashcards/{card_id}/review",
        json={"rating": 4, "review_date": str(today)},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(card_id)
    assert data["deck_id"] == str(deck_id)
    assert data["repetition_number"] == 2
    assert data["interval_days"] == 6
    assert data["easiness_factor"] == 2.5
    assert data["due_date"] == str(today + timedelta(days=6))
    mock_db.commit.assert_awaited_once()


def test_review_endpoint_lapse_resets(
    auth_client: TestClient,
    current_user: User,
    mock_db: AsyncMock,
):
    card_id = uuid.uuid4()
    deck_id = uuid.uuid4()
    today = date(2026, 11, 8)

    mock_card = Flashcard(
        id=card_id,
        deck_id=deck_id,
        user_id=current_user.id,
        front_text="What is SM-2?",
        back_text="Spaced repetition algorithm",
        repetition_number=3,
        easiness_factor=2.5,
        interval_days=15,
        due_date=today,
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_card
    mock_db.execute.return_value = mock_result

    resp = auth_client.post(
        f"/api/v1/flashcards/{card_id}/review",
        json={"rating": 1, "review_date": str(today)},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["repetition_number"] == 0
    assert data["interval_days"] == 1
    assert data["due_date"] == str(today + timedelta(days=1))
    assert data["easiness_factor"] == 1.96  # 2.5 - 0.54
    mock_db.commit.assert_awaited_once()
