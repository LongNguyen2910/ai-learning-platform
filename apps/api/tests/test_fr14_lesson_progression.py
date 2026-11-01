import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app.core.models_registry
from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.roadmaps.domain.node_progression_calculator import (
    NodeProgressionCalculator,
)
from app.modules.roadmaps.exceptions import (
    NodeLockedException,
    NodeNotLeafException,
)
from app.modules.roadmaps.models import Roadmap, RoadmapNode


# ============================================================================
# FIXTURES
# ============================================================================
@pytest.fixture
def student_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student_fr14@example.com",
        hashed_password="hashed_pwd",
        full_name="Sinh Viên FR14",
        role="user",
        is_active=True,
    )


@pytest.fixture
def other_student_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="other_fr14@example.com",
        hashed_password="hashed_pwd",
        full_name="Sinh Viên Khác",
        role="user",
        is_active=True,
    )


@pytest.fixture
def admin_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="admin_fr14@example.com",
        hashed_password="hashed_pwd",
        full_name="Admin FR14",
        role="admin",
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


def build_two_chapter_roadmap(user_id: uuid.UUID):
    """Creates a sample two-chapter roadmap structure:
    Chapter 1 (Giới hạn hàm số):
      Topic 1.1:
        Block 1: 30 mins (unlocked=True, completed=False)
        Block 2: 30 mins (unlocked=False, completed=False)
    Chapter 2 (Đạo hàm và vi phân):
      Topic 2.1:
        Block 3: 40 mins (unlocked=False, completed=False)
    Total leaf minutes: 30 + 30 + 40 = 100 mins.
    """
    roadmap_id = uuid.uuid4()
    ch1_id = uuid.uuid4()
    top1_id = uuid.uuid4()
    b1_id = uuid.uuid4()
    b2_id = uuid.uuid4()

    ch2_id = uuid.uuid4()
    top2_id = uuid.uuid4()
    b3_id = uuid.uuid4()

    roadmap = Roadmap(
        id=roadmap_id,
        user_id=user_id,
        subject_id=uuid.uuid4(),
        title="Lộ trình Giải tích 1 (FR-14 Test)",
        progress_percentage=0.0,
        status="active",
        created_at=datetime.now(UTC),
    )

    nodes = [
        RoadmapNode(
            id=ch1_id,
            roadmap_id=roadmap_id,
            parent_node_id=None,
            title="Chương 1: Giới hạn hàm số",
            order_index=1,
            estimated_minutes=0,
            is_unlocked=True,
            is_completed=False,
        ),
        RoadmapNode(
            id=top1_id,
            roadmap_id=roadmap_id,
            parent_node_id=ch1_id,
            title="Chủ đề 1.1: Định nghĩa giới hạn",
            order_index=2,
            estimated_minutes=0,
            is_unlocked=True,
            is_completed=False,
        ),
        RoadmapNode(
            id=b1_id,
            roadmap_id=roadmap_id,
            parent_node_id=top1_id,
            title="Khối 1: Giới hạn dãy số",
            order_index=3,
            estimated_minutes=30,
            is_unlocked=True,
            is_completed=False,
        ),
        RoadmapNode(
            id=b2_id,
            roadmap_id=roadmap_id,
            parent_node_id=top1_id,
            title="Khối 2: Giới hạn một bên",
            order_index=4,
            estimated_minutes=30,
            is_unlocked=False,
            is_completed=False,
        ),
        RoadmapNode(
            id=ch2_id,
            roadmap_id=roadmap_id,
            parent_node_id=None,
            title="Chương 2: Đạo hàm và vi phân",
            order_index=5,
            estimated_minutes=0,
            is_unlocked=True,
            is_completed=False,
        ),
        RoadmapNode(
            id=top2_id,
            roadmap_id=roadmap_id,
            parent_node_id=ch2_id,
            title="Chủ đề 2.1: Quy tắc đạo hàm",
            order_index=6,
            estimated_minutes=0,
            is_unlocked=True,
            is_completed=False,
        ),
        RoadmapNode(
            id=b3_id,
            roadmap_id=roadmap_id,
            parent_node_id=top2_id,
            title="Khối 3: Đạo hàm hàm hợp",
            order_index=7,
            estimated_minutes=40,
            is_unlocked=False,
            is_completed=False,
        ),
    ]

    return roadmap, nodes, (ch1_id, top1_id, b1_id, b2_id, ch2_id, top2_id, b3_id)


# ============================================================================
# 1. DOMAIN UNIT TESTS (NodeProgressionCalculator - FR-14)
# ============================================================================
class TestFR14DomainProgression:
    """Kiểm tra logic nghiệp vụ chuyển trạng thái bài học (is_unlocked, is_completed)."""

    def test_complete_study_block_unlocks_next_leaf_and_updates_progress(self, student_user: User):
        """Hoàn thành khối 1:
        - Khối 1: is_completed = True, completed_at được ghi nhận.
        - Khối 2: is_unlocked = True (mở khóa chặng kế tiếp).
        - Tiến độ roadmap: 30 / 100 = 30%.
        - Chủ đề và Chương 1 chưa hoàn thành vì Khối 2 chưa xong.
        """
        _, nodes, (_ch1, _top1, b1, b2, _, _, _) = build_two_chapter_roadmap(student_user.id)
        calculator = NodeProgressionCalculator()
        now = datetime.now(UTC)

        result = calculator.calculate_completion(nodes, b1, now)

        assert b1 in result.completed_node_ids
        assert b2 in result.unlocked_node_ids
        assert nodes[2].is_completed is True
        assert nodes[2].completed_at == now
        assert nodes[3].is_unlocked is True
        assert result.progress_percentage == 30.0
        assert result.roadmap_status == "active"
        assert nodes[0].is_completed is False
        assert nodes[1].is_completed is False

    def test_complete_last_block_of_chapter_cascades_and_unlocks_next_chapter(self, student_user: User):
        """Hoàn thành khối 2 (khối cuối của Chương 1):
        - Mở khóa Khối 3 (thuộc Chương 2).
        - Lan truyền hoàn thành: Chủ đề 1.1 và Chương 1 đều chuyển sang is_completed = True.
        - Tiến độ: (30 + 30) / 100 = 60%.
        """
        _, nodes, (ch1, top1, b1, b2, _ch2, _, b3) = build_two_chapter_roadmap(student_user.id)
        calculator = NodeProgressionCalculator()
        now = datetime.now(UTC)

        # Hoàn thành Khối 1 trước
        calculator.calculate_completion(nodes, b1, now)

        # Hoàn thành Khối 2
        result = calculator.calculate_completion(nodes, b2, now)

        assert b2 in result.completed_node_ids
        assert top1 in result.completed_node_ids
        assert ch1 in result.completed_node_ids
        assert b3 in result.unlocked_node_ids
        assert nodes[0].is_completed is True
        assert nodes[1].is_completed is True
        assert nodes[4].is_completed is False  # Chương 2 chưa xong
        assert nodes[6].is_unlocked is True   # Khối 3 đã mở khóa
        assert result.progress_percentage == 60.0
        assert result.roadmap_status == "active"

    def test_complete_all_blocks_completes_entire_roadmap(self, student_user: User):
        """Hoàn thành toàn bộ các khối:
        - Chương 2 và Chủ đề 2.1 chuyển is_completed = True.
        - Tiến độ đạt 100.0%.
        - Trạng thái Roadmap chuyển sang 'completed'.
        """
        _, nodes, (_ch1, _top1, b1, b2, ch2, top2, b3) = build_two_chapter_roadmap(student_user.id)
        calculator = NodeProgressionCalculator()
        now = datetime.now(UTC)

        calculator.calculate_completion(nodes, b1, now)
        calculator.calculate_completion(nodes, b2, now)
        result = calculator.calculate_completion(nodes, b3, now)

        assert b3 in result.completed_node_ids
        assert top2 in result.completed_node_ids
        assert ch2 in result.completed_node_ids
        assert result.unlocked_node_ids == []
        assert nodes[4].is_completed is True
        assert nodes[5].is_completed is True
        assert result.progress_percentage == 100.0
        assert result.roadmap_status == "completed"

    def test_cannot_complete_locked_block(self, student_user: User):
        """Không thể hoàn thành chặng học đang bị khóa (is_unlocked=False)."""
        _, nodes, (_, _, _, b2, _, _, _) = build_two_chapter_roadmap(student_user.id)
        calculator = NodeProgressionCalculator()

        with pytest.raises(NodeLockedException):
            calculator.calculate_completion(nodes, b2)

    def test_cannot_complete_non_leaf_parent_node(self, student_user: User):
        """Không thể gọi hoàn thành trực tiếp trên Chapter hoặc Topic cha."""
        _, nodes, (ch1, top1, _, _, _, _, _) = build_two_chapter_roadmap(student_user.id)
        calculator = NodeProgressionCalculator()

        with pytest.raises(NodeNotLeafException):
            calculator.calculate_completion(nodes, ch1)

        with pytest.raises(NodeNotLeafException):
            calculator.calculate_completion(nodes, top1)

    def test_completion_is_idempotent(self, student_user: User):
        """Gọi hoàn thành nhiều lần trên 1 bài đã hoàn thành không gây lỗi và không unlock thừa."""
        _, nodes, (_, _, b1, _, _, _, _) = build_two_chapter_roadmap(student_user.id)
        calculator = NodeProgressionCalculator()
        now = datetime.now(UTC)

        # Lần 1
        res1 = calculator.calculate_completion(nodes, b1, now)
        assert res1.progress_percentage == 30.0

        # Lần 2 (idempotent)
        res2 = calculator.calculate_completion(nodes, b1, now)
        assert res2.completed_node_ids == [b1]
        assert res2.unlocked_node_ids == []
        assert res2.progress_percentage == 30.0


# ============================================================================
# 2. ENDPOINT TESTS (POST /api/v1/roadmaps/nodes/{node_id}/complete - FR-14)
# ============================================================================
class TestFR14CompleteNodeEndpoint:
    """Kiểm tra toàn diện REST API endpoint hoàn thành bài học và mở khóa chặng sau."""

    def test_endpoint_complete_node_success(self, auth_client: TestClient, student_user: User):
        """Gọi POST hoàn thành Khối 1 thành công (HTTP 200), mở khóa Khối 2."""
        roadmap, nodes, (_, _, b1, b2, _, _, _) = build_two_chapter_roadmap(student_user.id)

        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=nodes[2])  # b1
            mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)
            mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)
            mock_repo.session.flush = AsyncMock()

            resp = auth_client.post(f"/api/v1/roadmaps/nodes/{b1}/complete")

            assert resp.status_code == 200
            data = resp.json()
            assert data["completed_node_id"] == str(b1)
            assert data["unlocked_node_ids"] == [str(b2)]
            assert data["progress_percentage"] == 30.0
            assert data["roadmap_status"] == "active"
            assert nodes[3].is_unlocked is True
            assert nodes[2].is_completed is True

    def test_endpoint_cross_chapter_unlock(self, auth_client: TestClient, student_user: User):
        """Hoàn thành khối cuối Chương 1 sẽ mở khóa khối đầu Chương 2 qua endpoint."""
        roadmap, nodes, (_ch1, _top1, _b1, b2, _, _, b3) = build_two_chapter_roadmap(student_user.id)
        # Giả lập Khối 1 đã xong trước đó
        nodes[2].is_completed = True

        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=nodes[3])  # b2 (đã được unlock)
            nodes[3].is_unlocked = True
            mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)
            mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)
            mock_repo.session.flush = AsyncMock()

            resp = auth_client.post(f"/api/v1/roadmaps/nodes/{b2}/complete")

            assert resp.status_code == 200
            data = resp.json()
            assert data["completed_node_id"] == str(b2)
            assert data["unlocked_node_ids"] == [str(b3)]
            assert data["progress_percentage"] == 60.0
            assert data["roadmap_status"] == "active"
            assert nodes[0].is_completed is True  # Chapter 1 cascaded
            assert nodes[6].is_unlocked is True   # Block 3 in Chapter 2 unlocked

    def test_endpoint_complete_final_block_finishes_roadmap(
        self, auth_client: TestClient, student_user: User
    ):
        """Hoàn thành khối cuối cùng của lộ trình -> roadmap_status chuyển sang 'completed'."""
        roadmap, nodes, (_, _, _, _, _, _, b3) = build_two_chapter_roadmap(student_user.id)
        # Giả lập 2 khối trước đã hoàn thành
        nodes[2].is_completed = True
        nodes[3].is_completed = True
        nodes[6].is_unlocked = True  # Khối cuối cùng đã unlock

        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=nodes[6])  # b3
            mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)
            mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)
            mock_repo.session.flush = AsyncMock()

            resp = auth_client.post(f"/api/v1/roadmaps/nodes/{b3}/complete")

            assert resp.status_code == 200
            data = resp.json()
            assert data["completed_node_id"] == str(b3)
            assert data["unlocked_node_ids"] == []
            assert data["progress_percentage"] == 100.0
            assert data["roadmap_status"] == "completed"

    def test_endpoint_complete_idempotent(
        self, auth_client: TestClient, student_user: User
    ):
        """Gọi hoàn thành lặp lại trên bài học đã xong -> trả về 200, không unlock trùng lặp."""
        roadmap, nodes, (_, _, b1, _, _, _, _) = build_two_chapter_roadmap(student_user.id)
        nodes[2].is_completed = True
        nodes[3].is_unlocked = True

        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=nodes[2])  # b1 đã completed
            mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)
            mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)
            mock_repo.session.flush = AsyncMock()

            resp = auth_client.post(f"/api/v1/roadmaps/nodes/{b1}/complete")
            assert resp.status_code == 200
            data = resp.json()
            assert data["completed_node_id"] == str(b1)
            assert data["unlocked_node_ids"] == []
            assert data["progress_percentage"] == 30.0

    def test_endpoint_idor_protection(
        self, auth_client: TestClient, other_student_user: User
    ):
        """Bảo mật IDOR: Sinh viên không được phép hoàn thành bài học của người khác -> 403 Forbidden."""
        # Roadmap thuộc về other_student_user
        roadmap, nodes, (_, _, b1, _, _, _, _) = build_two_chapter_roadmap(other_student_user.id)

        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=nodes[2])
            mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)

            resp = auth_client.post(f"/api/v1/roadmaps/nodes/{b1}/complete")

            assert resp.status_code == 403
            assert "forbidden" in resp.json()["detail"].lower() or "access" in resp.json()["detail"].lower()

    def test_endpoint_admin_can_complete_any_node(
        self, admin_user: User, other_student_user: User, mock_db: AsyncMock
    ):
        """Quyền Admin: Admin có thể hoàn thành bài học thay cho học viên -> 200 OK."""
        app.dependency_overrides[get_current_user] = lambda: admin_user
        app.dependency_overrides[get_db] = lambda: mock_db

        roadmap, nodes, (_, _, b1, _, _, _, _) = build_two_chapter_roadmap(other_student_user.id)

        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=nodes[2])
            mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)
            mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)
            mock_repo.session.flush = AsyncMock()

            with TestClient(app) as client:
                resp = client.post(f"/api/v1/roadmaps/nodes/{b1}/complete")
                assert resp.status_code == 200

        app.dependency_overrides.clear()

    def test_endpoint_locked_block_returns_400(self, auth_client: TestClient, student_user: User):
        """Khối bài học chưa được mở khóa -> 400 Bad Request."""
        roadmap, nodes, (_, _, _, b2, _, _, _) = build_two_chapter_roadmap(student_user.id)

        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=nodes[3])  # b2 is locked
            mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)
            mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)

            resp = auth_client.post(f"/api/v1/roadmaps/nodes/{b2}/complete")

            assert resp.status_code == 400
            assert "locked" in resp.json()["detail"].lower()

    def test_endpoint_parent_node_returns_400(self, auth_client: TestClient, student_user: User):
        """Khối cha (Chapter/Topic) không phải lá bài học -> 400 Bad Request."""
        roadmap, nodes, (ch1, _, _, _, _, _, _) = build_two_chapter_roadmap(student_user.id)

        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=nodes[0])  # ch1
            mock_repo.get_roadmap_by_id = AsyncMock(return_value=roadmap)
            mock_repo.get_nodes_by_roadmap_id = AsyncMock(return_value=nodes)

            resp = auth_client.post(f"/api/v1/roadmaps/nodes/{ch1}/complete")

            assert resp.status_code == 400
            assert "not a leaf" in resp.json()["detail"].lower()

    def test_endpoint_nonexistent_node_returns_404(self, auth_client: TestClient):
        """Node không tồn tại -> 404 Not Found."""
        random_id = uuid.uuid4()
        with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
            mock_repo = mock_repo_cls.return_value
            mock_repo.get_node_by_id = AsyncMock(return_value=None)

            resp = auth_client.post(f"/api/v1/roadmaps/nodes/{random_id}/complete")
            assert resp.status_code == 404

    def test_endpoint_unauthenticated_returns_401(self, mock_db: AsyncMock):
        """Chưa đăng nhập -> 401 Unauthorized."""
        app.dependency_overrides.clear()
        app.dependency_overrides[get_db] = lambda: mock_db

        with TestClient(app) as client:
            resp = client.post(f"/api/v1/roadmaps/nodes/{uuid.uuid4()}/complete")
            assert resp.status_code == 401

        app.dependency_overrides.clear()
