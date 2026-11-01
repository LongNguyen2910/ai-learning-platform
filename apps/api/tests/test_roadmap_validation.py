import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.roadmaps.domain.node_progression_calculator import (
    NodeProgressionCalculator,
)
from app.modules.roadmaps.domain.study_block_pacing_calculator import (
    StudyBlockPacingCalculator,
)
from app.modules.roadmaps.exceptions import (
    InvalidStudyGoalException,
    PrerequisiteNotCompletedException,
)
from app.modules.roadmaps.models import Roadmap, RoadmapNode
from app.modules.roadmaps.schemas import (
    RawChapterOutline,
    RawCurriculumOutline,
    RawStudyTopic,
    RoadmapGenerateRequest,
)


@pytest.fixture
def student_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student_validate@example.com",
        hashed_password="hashed_pwd",
        full_name="Sinh Viên Validate",
        role="user",
        is_active=True,
    )


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def auth_client(student_user: User, mock_db: AsyncMock):
    app.dependency_overrides[get_current_user] = lambda: student_user
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ============================================================================
# 1. GENERATION & TARGET DATE VALIDATION (Year 2171 Bug Fix)
# ============================================================================
def test_target_date_exceeding_365_days_raises_422(auth_client: TestClient):
    """Kiem tra loi khi dat target_date den nam 2171 -> chan bang HTTP 422."""
    payload = {
        "subject_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "title": "Lo trinh nam 2171",
        "target_date": "2171-12-31",
        "available_hours_per_day": 2.0,
    }
    resp = auth_client.post("/api/v1/roadmaps/generate", json=payload)
    assert resp.status_code == 422
    assert "target_date cannot be more than 1 year" in str(resp.json())


def test_schema_rejects_target_date_over_1_year():
    with pytest.raises(ValidationError) as exc:
        RoadmapGenerateRequest(
            subject_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            title="Lo trinh qua xa",
            target_date=date.today() + timedelta(days=400),
            available_hours_per_day=2.0,
        )
    assert "target_date cannot be more than 1 year" in str(exc.value)


def test_schema_rejects_blank_title():
    with pytest.raises(ValidationError) as exc:
        RoadmapGenerateRequest(
            subject_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            title="   ",
            target_date=date.today() + timedelta(days=30),
            available_hours_per_day=2.0,
        )
    assert "title must have at least 2 non-whitespace characters" in str(exc.value)


def test_schema_rejects_study_goal_exceeding_1000_chars():
    with pytest.raises(ValidationError) as exc:
        RoadmapGenerateRequest(
            subject_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            title="Lo trinh tieu chuan",
            target_date=date.today() + timedelta(days=30),
            available_hours_per_day=2.0,
            study_goal="A" * 1001,
        )
    assert "study_goal cannot exceed 1000 characters" in str(exc.value)


# ============================================================================
# 2. CURRICULUM & STUDY BLOCK PACING DOMAIN VALIDATION
# ============================================================================
def test_raw_study_topic_page_range_normalized():
    """Trang bi dao nguoc tu LLM duoc tu dong chuan hoa start <= end."""
    topic = RawStudyTopic(
        title="Chu de dao nguoc",
        target_page_start=15,
        target_page_end=10,
    )
    assert topic.target_page_start == 10
    assert topic.target_page_end == 15


def test_raw_chapter_page_range_normalized():
    """Trang chuong dao nguoc duoc tu dong chuan hoa start <= end."""
    ch = RawChapterOutline(
        title="Chuong dao nguoc",
        target_page_start=50,
        target_page_end=20,
    )
    assert ch.target_page_start == 20
    assert ch.target_page_end == 50


def test_pacing_calculator_rejects_far_future_date():
    calc = StudyBlockPacingCalculator()
    today = date(2026, 10, 28)
    far_future = today + timedelta(days=400)
    with pytest.raises(InvalidStudyGoalException) as exc:
        calc.calculate_available_minutes(far_future, today, 2.0)
    assert "target_date cannot exceed 366 days" in str(exc.value)


def test_pacing_calculator_rejects_invalid_hours():
    calc = StudyBlockPacingCalculator()
    today = date(2026, 10, 28)
    target = today + timedelta(days=30)
    with pytest.raises(InvalidStudyGoalException) as exc:
        calc.calculate_available_minutes(target, today, 15.0)
    assert "available_hours_per_day must be between" in str(exc.value)


def test_pacing_calculator_rejects_empty_curriculum():
    calc = StudyBlockPacingCalculator()
    today = date(2026, 10, 28)
    target = today + timedelta(days=30)
    curriculum = RawCurriculumOutline(title="Rong", chapters=[])
    with pytest.raises(InvalidStudyGoalException) as exc:
        calc.allocate(curriculum, target, today, 2.0)
    assert "Curriculum must contain at least one chapter" in str(exc.value)


# ============================================================================
# 3. LESSON PROGRESSION & STATUS VALIDATION (FR-14)
# ============================================================================
def test_cannot_complete_node_out_of_order():
    """Khong the hoan thanh Block 2 neu Block 1 chua completed du Block 2 da duoc set unlocked."""
    calc = NodeProgressionCalculator()
    b1_id = uuid.uuid4()
    b2_id = uuid.uuid4()
    ch_id = uuid.uuid4()
    top_id = uuid.uuid4()
    roadmap_id = uuid.uuid4()

    nodes = [
        RoadmapNode(id=ch_id, roadmap_id=roadmap_id, parent_node_id=None, title="Ch 1", order_index=1, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=top_id, roadmap_id=roadmap_id, parent_node_id=ch_id, title="Top 1", order_index=2, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=b1_id, roadmap_id=roadmap_id, parent_node_id=top_id, title="Block 1", order_index=3, estimated_minutes=30, is_unlocked=True, is_completed=False),
        RoadmapNode(id=b2_id, roadmap_id=roadmap_id, parent_node_id=top_id, title="Block 2", order_index=4, estimated_minutes=30, is_unlocked=True, is_completed=False),
    ]

    with pytest.raises(PrerequisiteNotCompletedException) as exc:
        calc.calculate_completion(nodes, b2_id)
    assert "before previous node" in str(exc.value)


def test_endpoint_rejects_out_of_order_completion(auth_client: TestClient, student_user: User):
    """Endpoint tra ve HTTP 400 khi hoan thanh dot bien bo qua chieu thu tu."""
    roadmap_id = uuid.uuid4()
    ch_id = uuid.uuid4()
    top_id = uuid.uuid4()
    b1_id = uuid.uuid4()
    b2_id = uuid.uuid4()

    roadmap = Roadmap(
        id=roadmap_id,
        user_id=student_user.id,
        subject_id=uuid.uuid4(),
        title="Roadmap Test",
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    nodes = [
        RoadmapNode(id=ch_id, roadmap_id=roadmap_id, parent_node_id=None, title="Ch 1", order_index=1, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=top_id, roadmap_id=roadmap_id, parent_node_id=ch_id, title="Top 1", order_index=2, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=b1_id, roadmap_id=roadmap_id, parent_node_id=top_id, title="Block 1", order_index=3, estimated_minutes=30, is_unlocked=True, is_completed=False),
        RoadmapNode(id=b2_id, roadmap_id=roadmap_id, parent_node_id=top_id, title="Block 2", order_index=4, estimated_minutes=30, is_unlocked=True, is_completed=False),
    ]

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=nodes[3])  # b2
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)
        mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)

        resp = auth_client.post(f"/api/v1/roadmaps/nodes/{b2_id}/complete")
        assert resp.status_code == 400
        assert "before previous node" in resp.json()["detail"].lower()


def test_endpoint_rejects_completing_archived_roadmap(auth_client: TestClient, student_user: User):
    """Endpoint tra ve HTTP 400 khi roadmap da bi archived."""
    roadmap_id = uuid.uuid4()
    ch_id = uuid.uuid4()
    top_id = uuid.uuid4()
    b1_id = uuid.uuid4()

    roadmap = Roadmap(
        id=roadmap_id,
        user_id=student_user.id,
        subject_id=uuid.uuid4(),
        title="Roadmap Archived",
        progress_percentage=0.0,
        status="archived",
        created_at=datetime.now(UTC),
    )
    nodes = [
        RoadmapNode(id=ch_id, roadmap_id=roadmap_id, parent_node_id=None, title="Ch 1", order_index=1, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=top_id, roadmap_id=roadmap_id, parent_node_id=ch_id, title="Top 1", order_index=2, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=b1_id, roadmap_id=roadmap_id, parent_node_id=top_id, title="Block 1", order_index=3, estimated_minutes=30, is_unlocked=True, is_completed=False),
    ]

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=nodes[2])  # b1
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)

        resp = auth_client.post(f"/api/v1/roadmaps/nodes/{b1_id}/complete")
        assert resp.status_code == 400
        assert "archived" in resp.json()["detail"].lower()
