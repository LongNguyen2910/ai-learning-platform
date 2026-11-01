import uuid
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app.core.models_registry
from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.documents.models import Document, Subject
from app.modules.roadmaps.models import Roadmap, RoadmapNode
from app.modules.roadmaps.router import _global_task_registry
from app.modules.roadmaps.schemas import RoadmapTaskStatusResponse


@pytest.fixture
def mock_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student@example.com",
        hashed_password="hashed_pwd",
        full_name="Sinh Viên A",
        role="user",
        is_active=True,
    )


@pytest.fixture
def admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="admin@example.com",
        hashed_password="hashed_pwd",
        full_name="Quản Trị Viên",
        role="admin",
        is_active=True,
    )


@pytest.fixture
def other_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="other@example.com",
        hashed_password="hashed_pwd",
        full_name="Người Dùng Khác",
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
def client(mock_user: User, mock_db: AsyncMock):
    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_generate_roadmap_endpoint_success(client: TestClient, mock_user: User):
    subject_id = uuid.uuid4()
    document_id = uuid.uuid4()
    future_date = date.today() + timedelta(days=14)

    payload = {
        "subject_id": str(subject_id),
        "document_id": str(document_id),
        "title": "Lộ trình Giải tích 1 trong 2 tuần",
        "target_date": future_date.isoformat(),
        "available_hours_per_day": 2.5,
        "study_goal": "Đạt điểm 9+",
    }

    with (
        patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls,
        patch("app.modules.roadmaps.router._execute_roadmap_pipeline"),
    ):
        mock_repo = mock_repo_cls.return_value
        fake_subject = Subject(id=subject_id, user_id=mock_user.id, name="Giải tích 1")
        fake_doc = Document(id=document_id, user_id=mock_user.id, title="Doc 1", status="ready")
        fake_roadmap = Roadmap(
            id=uuid.uuid4(),
            user_id=mock_user.id,
            subject_id=subject_id,
            title=payload["title"],
            target_date=future_date,
            available_hours_per_day=2.5,
            status="generating",
            progress_percentage=0.0,
            created_at=datetime.now(UTC),
        )
        mock_repo.get_subject_by_id = AsyncMock(return_value=fake_subject)
        mock_repo.get_document_by_id = AsyncMock(return_value=fake_doc)
        mock_repo.create_roadmap = AsyncMock(return_value=fake_roadmap)

        response = client.post("/api/v1/roadmaps/generate", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert "task_id" in data
        assert data["roadmap_id"] == str(fake_roadmap.id)
        assert data["status"] == "processing"
        assert data["progress_percent"] == 10
        mock_repo.create_roadmap.assert_awaited_once()


def test_generate_roadmap_endpoint_subject_not_found(client: TestClient):
    subject_id = uuid.uuid4()
    document_id = uuid.uuid4()
    future_date = date.today() + timedelta(days=14)

    payload = {
        "subject_id": str(subject_id),
        "document_id": str(document_id),
        "title": "Lộ trình",
        "target_date": future_date.isoformat(),
        "available_hours_per_day": 2.0,
    }

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_subject_by_id = AsyncMock(return_value=None)

        response = client.post("/api/v1/roadmaps/generate", json=payload)

        assert response.status_code == 404
        assert f"Subject with id '{subject_id}' was not found" in response.json()["detail"]


def test_generate_roadmap_endpoint_subject_forbidden(client: TestClient, other_user: User):
    subject_id = uuid.uuid4()
    document_id = uuid.uuid4()
    future_date = date.today() + timedelta(days=14)

    payload = {
        "subject_id": str(subject_id),
        "document_id": str(document_id),
        "title": "Lộ trình",
        "target_date": future_date.isoformat(),
        "available_hours_per_day": 2.0,
    }

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        # Subject belongs to other_user
        mock_repo.get_subject_by_id = AsyncMock(
            return_value=Subject(id=subject_id, user_id=other_user.id, name="Khác")
        )

        response = client.post("/api/v1/roadmaps/generate", json=payload)

        assert response.status_code == 404


def test_generate_roadmap_endpoint_document_not_parsed(client: TestClient, mock_user: User):
    subject_id = uuid.uuid4()
    document_id = uuid.uuid4()
    future_date = date.today() + timedelta(days=14)

    payload = {
        "subject_id": str(subject_id),
        "document_id": str(document_id),
        "title": "Lộ trình",
        "target_date": future_date.isoformat(),
        "available_hours_per_day": 2.0,
    }

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_subject_by_id = AsyncMock(
            return_value=Subject(id=subject_id, user_id=mock_user.id, name="Giải tích 1")
        )
        mock_repo.get_document_by_id = AsyncMock(return_value=None)

        response = client.post("/api/v1/roadmaps/generate", json=payload)

        assert response.status_code == 404
        assert f"Document '{document_id}' is not parsed" in response.json()["detail"]


def test_generate_roadmap_past_date_validation_error(client: TestClient):
    past_date = date.today() - timedelta(days=1)
    payload = {
        "subject_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "title": "Lộ trình quá hạn",
        "target_date": past_date.isoformat(),
        "available_hours_per_day": 2.0,
    }

    response = client.post("/api/v1/roadmaps/generate", json=payload)
    assert response.status_code == 422
    assert "target_date must be in the future" in str(response.json())


def test_generate_roadmap_invalid_hours_validation_error(client: TestClient):
    future_date = date.today() + timedelta(days=10)
    # available_hours_per_day < 0.5
    payload = {
        "subject_id": str(uuid.uuid4()),
        "document_id": str(uuid.uuid4()),
        "title": "Lộ trình thời gian quá ít",
        "target_date": future_date.isoformat(),
        "available_hours_per_day": 0.1,
    }

    response = client.post("/api/v1/roadmaps/generate", json=payload)
    assert response.status_code == 422


def test_get_task_status_endpoint_found(client: TestClient):
    task_id = f"task_{uuid.uuid4().hex[:8]}"
    _global_task_registry[task_id] = RoadmapTaskStatusResponse(
        task_id=task_id,
        roadmap_id=uuid.uuid4(),
        status="processing",
        progress_percent=60,
        message="Đang tính toán phân bổ...",
    )

    response = client.get(f"/api/v1/roadmaps/tasks/{task_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == task_id
    assert data["progress_percent"] == 60
    assert data["status"] == "processing"

    # Cleanup registry
    del _global_task_registry[task_id]


def test_get_task_status_endpoint_not_found(client: TestClient):
    response = client.get("/api/v1/roadmaps/tasks/non-existent-task-999")
    assert response.status_code == 404
    assert "was not found" in response.json()["detail"]


def test_get_roadmap_tree_endpoint_success(client: TestClient, mock_user: User):
    roadmap_id = uuid.uuid4()
    chapter_id = uuid.uuid4()
    topic_id = uuid.uuid4()
    block_id = uuid.uuid4()

    chapter = RoadmapNode(
        id=chapter_id,
        roadmap_id=roadmap_id,
        parent_node_id=None,
        title="Chương 1: Đạo hàm",
        description="Nền tảng",
        order_index=1,
        target_page_start=1,
        target_page_end=10,
        estimated_minutes=0,
        is_unlocked=True,
        is_completed=False,
    )
    topic = RoadmapNode(
        id=topic_id,
        roadmap_id=roadmap_id,
        parent_node_id=chapter_id,
        title="Chủ đề 1.1: Định nghĩa đạo hàm",
        description="Khái niệm",
        order_index=2,
        target_page_start=1,
        target_page_end=5,
        estimated_minutes=0,
        is_unlocked=True,
        is_completed=False,
    )
    block = RoadmapNode(
        id=block_id,
        roadmap_id=roadmap_id,
        parent_node_id=topic_id,
        title="Khối 1: Quy tắc tính đạo hàm",
        description="Bài học 25p",
        order_index=3,
        target_page_start=1,
        target_page_end=5,
        estimated_minutes=25,
        is_unlocked=True,
        is_completed=False,
    )

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Giải tích 1",
        target_date=date.today() + timedelta(days=7),
        available_hours_per_day=2.0,
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
        nodes=[chapter, topic, block],
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)

        response = client.get(f"/api/v1/roadmaps/{roadmap_id}/tree")
        assert response.status_code == 200
        data = response.json()

        assert data["roadmap"]["id"] == str(roadmap_id)
        assert data["total_nodes"] == 3
        assert data["total_estimated_minutes"] == 25

        tree = data["tree"]
        assert len(tree) == 1
        assert tree[0]["id"] == str(chapter_id)
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["id"] == str(topic_id)
        assert len(tree[0]["children"][0]["children"]) == 1
        assert tree[0]["children"][0]["children"][0]["id"] == str(block_id)


def test_get_roadmap_tree_endpoint_not_found(client: TestClient):
    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=None)

        random_id = uuid.uuid4()
        response = client.get(f"/api/v1/roadmaps/{random_id}/tree")
        assert response.status_code == 404
        assert "was not found" in response.json()["detail"]


def test_get_roadmap_tree_endpoint_forbidden_idor(
    client: TestClient, other_user: User
):
    roadmap_id = uuid.uuid4()
    # Roadmap owned by other_user, while client is authenticated as mock_user
    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=other_user.id,
        subject_id=uuid.uuid4(),
        title="Bí mật riêng tư",
        target_date=date.today() + timedelta(days=7),
        available_hours_per_day=2.0,
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
        nodes=[],
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)

        response = client.get(f"/api/v1/roadmaps/{roadmap_id}/tree")
        assert response.status_code == 403
        assert "You do not have access" in response.json()["detail"]


def test_get_roadmap_tree_endpoint_admin_allowed(
    admin_user: User, other_user: User, mock_db: AsyncMock
):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: mock_db

    roadmap_id = uuid.uuid4()
    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=other_user.id,
        subject_id=uuid.uuid4(),
        title="Lộ trình học của học viên",
        target_date=date.today() + timedelta(days=7),
        available_hours_per_day=2.0,
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
        nodes=[],
    )

    with (
        patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls,
        TestClient(app) as test_client,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)

        response = test_client.get(f"/api/v1/roadmaps/{roadmap_id}/tree")
        assert response.status_code == 200

    app.dependency_overrides.clear()


def test_get_roadmap_details_endpoint(client: TestClient, mock_user: User):
    roadmap_id = uuid.uuid4()
    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Chi tiết lộ trình",
        target_date=date.today() + timedelta(days=5),
        available_hours_per_day=1.5,
        progress_percentage=15.0,
        status="active",
        created_at=datetime.now(UTC),
        nodes=[],
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)

        response = client.get(f"/api/v1/roadmaps/{roadmap_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(roadmap_id)
        assert data["title"] == "Chi tiết lộ trình"
        assert data["progress_percentage"] == 15.0


def test_list_subject_roadmaps_endpoint(client: TestClient, mock_user: User):
    subject_id = uuid.uuid4()
    fake_subject = Subject(id=subject_id, user_id=mock_user.id, name="Toán")
    rm1 = Roadmap(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        subject_id=subject_id,
        title="Lộ trình 1",
        target_date=date.today() + timedelta(days=5),
        available_hours_per_day=2.0,
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    rm2 = Roadmap(
        id=uuid.uuid4(),
        user_id=mock_user.id,
        subject_id=subject_id,
        title="Lộ trình 2",
        target_date=date.today() + timedelta(days=10),
        available_hours_per_day=1.0,
        progress_percentage=50.0,
        status="active",
        created_at=datetime.now(UTC),
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_subject_by_id = AsyncMock(return_value=fake_subject)
        mock_repo.get_roadmaps_by_subject = AsyncMock(return_value=[rm1, rm2])

        response = client.get(f"/api/v1/roadmaps/subject/{subject_id}")
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 2
        assert items[0]["id"] == str(rm1.id)
        assert items[0]["roadmap_id"] == str(rm1.id)
        assert items[1]["id"] == str(rm2.id)
        assert items[1]["roadmap_id"] == str(rm2.id)


def test_list_subject_roadmaps_not_found(client: TestClient):
    subject_id = uuid.uuid4()
    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_subject_by_id = AsyncMock(return_value=None)

        response = client.get(f"/api/v1/roadmaps/subject/{subject_id}")
        assert response.status_code == 404


def test_list_subject_roadmaps_forbidden(client: TestClient, other_user: User):
    subject_id = uuid.uuid4()
    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_subject_by_id = AsyncMock(
            return_value=Subject(id=subject_id, user_id=other_user.id, name="Khác")
        )

        response = client.get(f"/api/v1/roadmaps/subject/{subject_id}")
        assert response.status_code == 403


def test_generate_roadmap_endpoint_with_session_mode(client: TestClient, mock_user: User):
    subject_id = uuid.uuid4()
    document_id = uuid.uuid4()
    future_date = date.today() + timedelta(days=14)

    payload = {
        "subject_id": str(subject_id),
        "document_id": str(document_id),
        "title": "Lộ trình Deep Work",
        "target_date": future_date.isoformat(),
        "available_hours_per_day": 2.0,
        "session_mode": "deep_work",
    }

    with (
        patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls,
        patch("app.modules.roadmaps.router._execute_roadmap_pipeline") as mock_pipeline,
    ):
        mock_repo = mock_repo_cls.return_value
        fake_subject = Subject(id=subject_id, user_id=mock_user.id, name="Vật lý đại cương")
        fake_doc = Document(id=document_id, user_id=mock_user.id, title="Doc 1", status="ready")
        fake_roadmap = Roadmap(
            id=uuid.uuid4(),
            user_id=mock_user.id,
            subject_id=subject_id,
            title=payload["title"],
            target_date=future_date,
            available_hours_per_day=2.0,
            status="generating",
            progress_percentage=0.0,
            created_at=datetime.now(UTC),
        )
        mock_repo.get_subject_by_id = AsyncMock(return_value=fake_subject)
        mock_repo.get_document_by_id = AsyncMock(return_value=fake_doc)
        mock_repo.create_roadmap = AsyncMock(return_value=fake_roadmap)

        response = client.post("/api/v1/roadmaps/generate", json=payload)

        assert response.status_code == 202
        data = response.json()
        assert data["roadmap_id"] == str(fake_roadmap.id)
        mock_pipeline.assert_called_once()
        req_arg = mock_pipeline.call_args[0][2]
        assert req_arg.session_mode.value == "deep_work"


def test_complete_node_endpoint_success(client: TestClient, mock_user: User):
    roadmap_id = uuid.uuid4()
    node1_id = uuid.uuid4()
    node2_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Roadmap Test",
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    node1 = RoadmapNode(
        id=node1_id,
        roadmap_id=roadmap_id,
        parent_node_id=uuid.uuid4(),
        title="Block 1",
        order_index=1,
        estimated_minutes=30,
        is_unlocked=True,
        is_completed=False,
    )
    node2 = RoadmapNode(
        id=node2_id,
        roadmap_id=roadmap_id,
        parent_node_id=node1.parent_node_id,
        title="Block 2",
        order_index=2,
        estimated_minutes=30,
        is_unlocked=False,
        is_completed=False,
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=node1)
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=[node1, node2])
        mock_repo.session.flush = AsyncMock()

        resp = client.post(f"/api/v1/roadmaps/nodes/{node1_id}/complete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed_node_id"] == str(node1_id)
        assert data["unlocked_node_ids"] == [str(node2_id)]
        assert data["progress_percentage"] == 50.0
        assert data["roadmap_status"] == "active"


def test_complete_node_endpoint_forbidden_for_other_user(
    client: TestClient, mock_user: User, other_user: User
):
    roadmap_id = uuid.uuid4()
    node1_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=other_user.id,  # Owned by other user
        subject_id=uuid.uuid4(),
        title="Roadmap Test",
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    node1 = RoadmapNode(
        id=node1_id,
        roadmap_id=roadmap_id,
        parent_node_id=uuid.uuid4(),
        title="Block 1",
        order_index=1,
        estimated_minutes=30,
        is_unlocked=True,
        is_completed=False,
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=node1)
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)

        resp = client.post(f"/api/v1/roadmaps/nodes/{node1_id}/complete")
        assert resp.status_code == 403


def test_complete_node_endpoint_locked_node_bad_request(
    client: TestClient, mock_user: User
):
    roadmap_id = uuid.uuid4()
    node_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Roadmap Test",
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    node = RoadmapNode(
        id=node_id,
        roadmap_id=roadmap_id,
        parent_node_id=uuid.uuid4(),
        title="Locked Block",
        order_index=2,
        estimated_minutes=30,
        is_unlocked=False,
        is_completed=False,
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=node)
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=[node])

        resp = client.post(f"/api/v1/roadmaps/nodes/{node_id}/complete")
        assert resp.status_code == 400
        assert "locked" in resp.json()["detail"].lower()


def test_complete_node_endpoint_not_found(client: TestClient, mock_user: User):
    nonexistent_id = uuid.uuid4()
    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=None)

        resp = client.post(f"/api/v1/roadmaps/nodes/{nonexistent_id}/complete")
        assert resp.status_code == 404


def test_complete_node_endpoint_parent_node_bad_request(
    client: TestClient, mock_user: User
):
    roadmap_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Roadmap Test",
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    chapter_node = RoadmapNode(
        id=parent_id,
        roadmap_id=roadmap_id,
        parent_node_id=None,
        title="Chương 1",
        order_index=1,
        estimated_minutes=0,
        is_unlocked=True,
        is_completed=False,
    )
    leaf_node = RoadmapNode(
        id=child_id,
        roadmap_id=roadmap_id,
        parent_node_id=parent_id,
        title="Khối 1",
        order_index=2,
        estimated_minutes=30,
        is_unlocked=True,
        is_completed=False,
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=chapter_node)
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=[chapter_node, leaf_node])

        resp = client.post(f"/api/v1/roadmaps/nodes/{parent_id}/complete")
        assert resp.status_code == 400
        assert "not a leaf study block" in resp.json()["detail"].lower()


def test_complete_node_endpoint_final_block_completes_roadmap(
    client: TestClient, mock_user: User
):
    roadmap_id = uuid.uuid4()
    node_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Roadmap Test",
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    leaf_node = RoadmapNode(
        id=node_id,
        roadmap_id=roadmap_id,
        parent_node_id=uuid.uuid4(),
        title="Khối duy nhất",
        order_index=1,
        estimated_minutes=45,
        is_unlocked=True,
        is_completed=False,
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=leaf_node)
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=[leaf_node])
        mock_repo.session.flush = AsyncMock()

        resp = client.post(f"/api/v1/roadmaps/nodes/{node_id}/complete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed_node_id"] == str(node_id)
        assert data["unlocked_node_ids"] == []
        assert data["progress_percentage"] == 100.0
        assert data["roadmap_status"] == "completed"




def test_complete_node_endpoint_idempotent(client: TestClient, mock_user: User):
    roadmap_id = uuid.uuid4()
    node_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Roadmap Test",
        progress_percentage=100.0,
        status="completed",
        created_at=datetime.now(UTC),
    )
    leaf_node = RoadmapNode(
        id=node_id,
        roadmap_id=roadmap_id,
        parent_node_id=uuid.uuid4(),
        title="Khối đã xong",
        order_index=1,
        estimated_minutes=45,
        is_unlocked=True,
        is_completed=True,
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=leaf_node)
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=[leaf_node])
        mock_repo.session.flush = AsyncMock()

        resp = client.post(f"/api/v1/roadmaps/nodes/{node_id}/complete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed_node_id"] == str(node_id)
        assert data["unlocked_node_ids"] == []
        assert data["progress_percentage"] == 100.0
        assert data["roadmap_status"] == "completed"


def test_complete_node_endpoint_admin_allowed_for_other_user(
    admin_user: User, other_user: User, mock_db: AsyncMock
):
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: mock_db

    roadmap_id = uuid.uuid4()
    node_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=other_user.id,  # Owned by other user
        subject_id=uuid.uuid4(),
        title="Other User Roadmap",
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    leaf_node = RoadmapNode(
        id=node_id,
        roadmap_id=roadmap_id,
        parent_node_id=uuid.uuid4(),
        title="Khối học",
        order_index=1,
        estimated_minutes=30,
        is_unlocked=True,
        is_completed=False,
    )

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=leaf_node)
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=[leaf_node])
        mock_repo.session.flush = AsyncMock()

        with TestClient(app) as test_client:
            resp = test_client.post(f"/api/v1/roadmaps/nodes/{node_id}/complete")
            assert resp.status_code == 200
            data = resp.json()
            assert data["completed_node_id"] == str(node_id)
            assert data["progress_percentage"] == 100.0
            assert data["roadmap_status"] == "completed"

    app.dependency_overrides.clear()


def test_complete_node_endpoint_cross_chapter_unlock(
    client: TestClient, mock_user: User
):
    roadmap_id = uuid.uuid4()
    ch1_id = uuid.uuid4()
    top1_id = uuid.uuid4()
    b1_id = uuid.uuid4()
    b2_id = uuid.uuid4()

    ch2_id = uuid.uuid4()
    top2_id = uuid.uuid4()
    b3_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Lộ trình Giải tích",
        progress_percentage=30.0,
        status="active",
        created_at=datetime.now(UTC),
    )
    nodes = [
        RoadmapNode(id=ch1_id, roadmap_id=roadmap_id, parent_node_id=None, title="Chương 1", order_index=1, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=top1_id, roadmap_id=roadmap_id, parent_node_id=ch1_id, title="Chủ đề 1", order_index=2, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=b1_id, roadmap_id=roadmap_id, parent_node_id=top1_id, title="Khối 1", order_index=3, estimated_minutes=30, is_unlocked=True, is_completed=True),
        RoadmapNode(id=b2_id, roadmap_id=roadmap_id, parent_node_id=top1_id, title="Khối 2", order_index=4, estimated_minutes=30, is_unlocked=True, is_completed=False),
        RoadmapNode(id=ch2_id, roadmap_id=roadmap_id, parent_node_id=None, title="Chương 2", order_index=5, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=top2_id, roadmap_id=roadmap_id, parent_node_id=ch2_id, title="Chủ đề 2", order_index=6, estimated_minutes=0, is_unlocked=True, is_completed=False),
        RoadmapNode(id=b3_id, roadmap_id=roadmap_id, parent_node_id=top2_id, title="Khối 3", order_index=7, estimated_minutes=40, is_unlocked=False, is_completed=False),
    ]

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_node_by_id = AsyncMock(return_value=nodes[3])  # Completing b2_id
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)
        mock_repo.session.flush = AsyncMock()

        resp = client.post(f"/api/v1/roadmaps/nodes/{b2_id}/complete")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed_node_id"] == str(b2_id)
        # Next leaf in chapter 2 is unlocked
        assert data["unlocked_node_ids"] == [str(b3_id)]
        assert data["progress_percentage"] == 60.0
        assert data["roadmap_status"] == "active"
        # Chapter 1 and Topic 1 were cascaded
        assert nodes[0].is_completed is True
        assert nodes[1].is_completed is True
        assert nodes[6].is_unlocked is True


def test_complete_node_endpoint_unauthenticated(mock_db: AsyncMock):
    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = lambda: mock_db
    with TestClient(app) as unauth_client:
        resp = unauth_client.post(f"/api/v1/roadmaps/nodes/{uuid.uuid4()}/complete")
        assert resp.status_code == 401
    app.dependency_overrides.clear()



