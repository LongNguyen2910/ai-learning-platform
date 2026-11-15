import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio

import app.core.models_registry  # noqa: F401
from app.core.database import AsyncSessionLocal, engine
from app.modules.auth.models import User
from app.modules.documents.models import Subject
from app.modules.roadmaps.domain.roadmap_pacing_adjuster import (
    RoadmapPacingAdjuster,
)
from app.modules.roadmaps.models import Roadmap, RoadmapNode
from app.modules.roadmaps.repository import RoadmapRepository
from app.modules.roadmaps.service import RoadmapService


@pytest_asyncio.fixture(autouse=True)
async def cleanup_db_connections():
    yield
    await engine.dispose()


def _build_test_roadmap(
    target_date: date | None = None,
    available_hours: float = 2.0,
    status: str = "active",
) -> Roadmap:
    r_id = uuid.uuid4()
    return Roadmap(
        id=r_id,
        user_id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        title="Giải tích 1",
        target_date=target_date,
        available_hours_per_day=available_hours,
        progress_percentage=0.0,
        status=status,
    )


def _build_test_tree(
    roadmap_id: uuid.UUID,
    leaf_configs: list[tuple[int, bool]],
) -> list[RoadmapNode]:
    chapter_id = uuid.uuid4()
    nodes: list[RoadmapNode] = [
        RoadmapNode(
            id=chapter_id,
            roadmap_id=roadmap_id,
            parent_node_id=None,
            title="Chương 1",
            order_index=1,
            estimated_minutes=sum(mins for mins, _ in leaf_configs),
            is_unlocked=True,
            is_completed=False,
        )
    ]

    for idx, (mins, completed) in enumerate(leaf_configs, start=2):
        nodes.append(
            RoadmapNode(
                id=uuid.uuid4(),
                roadmap_id=roadmap_id,
                parent_node_id=chapter_id,
                title=f"Block {idx}",
                order_index=idx,
                estimated_minutes=mins,
                is_unlocked=True,
                is_completed=completed,
            )
        )
    return nodes


def test_adjuster_completed_or_no_target_date_does_nothing():
    adjuster = RoadmapPacingAdjuster()
    today = date(2026, 11, 15)

    roadmap_no_target = _build_test_roadmap(target_date=None)
    nodes = _build_test_tree(roadmap_no_target.id, [(30, False)])
    res = adjuster.adjust_if_behind(roadmap_no_target, nodes, today=today)
    assert not res.was_adjusted
    assert res.days_extended == 0

    roadmap_completed = _build_test_roadmap(
        target_date=today + timedelta(days=5), status="completed"
    )
    res_completed = adjuster.adjust_if_behind(roadmap_completed, nodes, today=today)
    assert not res_completed.was_adjusted


def test_adjuster_all_leaf_nodes_completed_does_nothing():
    adjuster = RoadmapPacingAdjuster()
    today = date(2026, 11, 15)
    roadmap = _build_test_roadmap(target_date=today + timedelta(days=1))
    nodes = _build_test_tree(roadmap.id, [(30, True), (45, True)])

    res = adjuster.adjust_if_behind(roadmap, nodes, today=today)
    assert not res.was_adjusted
    assert res.remaining_minutes == 0


def test_adjuster_on_schedule_does_nothing():
    adjuster = RoadmapPacingAdjuster()
    today = date(2026, 11, 15)
    target_date = today + timedelta(days=10)
    roadmap = _build_test_roadmap(target_date=target_date, available_hours=2.0)
    # Available = 10 days * 120m = 1200m. Remaining = 200m
    nodes = _build_test_tree(roadmap.id, [(100, False), (100, False)])

    res = adjuster.adjust_if_behind(roadmap, nodes, today=today)
    assert not res.was_adjusted
    assert res.remaining_minutes == 200
    assert res.available_minutes == 1200
    assert res.days_extended == 0


def test_adjuster_behind_schedule_extends_target_date():
    adjuster = RoadmapPacingAdjuster()
    today = date(2026, 11, 15)
    target_date = today + timedelta(days=1)  # Available = 1 * 120m = 120m
    roadmap = _build_test_roadmap(
        target_date=target_date, available_hours=2.0, status="behind_schedule"
    )
    # Remaining = 360m -> ceil(360 / 120) = 3 days needed from today
    nodes = _build_test_tree(roadmap.id, [(120, False), (120, False), (120, False)])

    res = adjuster.adjust_if_behind(roadmap, nodes, today=today)
    assert res.was_adjusted
    assert res.remaining_minutes == 360
    assert res.available_minutes == 120
    assert res.new_target_date == today + timedelta(days=3)
    assert res.days_extended == 2
    assert res.new_status == "active"
    assert "gia hạn thêm 2 ngày" in (res.message or "")


def test_adjuster_past_target_date_recovers_to_future():
    adjuster = RoadmapPacingAdjuster()
    today = date(2026, 11, 15)
    past_target = today - timedelta(days=3)
    roadmap = _build_test_roadmap(target_date=past_target, available_hours=2.0)
    # Remaining = 120m -> 1 day needed
    nodes = _build_test_tree(roadmap.id, [(120, False)])

    res = adjuster.adjust_if_behind(roadmap, nodes, today=today)
    assert res.was_adjusted
    assert res.new_target_date == today + timedelta(days=1)
    assert res.days_extended == 4  # from -3 to +1


def test_adjuster_horizon_cap():
    adjuster = RoadmapPacingAdjuster()
    today = date(2026, 11, 15)
    target_date = today + timedelta(days=1)
    roadmap = _build_test_roadmap(target_date=target_date, available_hours=1.0)
    # Massive workload: 500 days worth of work
    huge_minutes = 500 * 60
    nodes = _build_test_tree(roadmap.id, [(huge_minutes, False)])

    res = adjuster.adjust_if_behind(roadmap, nodes, today=today)
    assert res.was_adjusted
    assert res.new_target_date == today + timedelta(days=366)


def test_adjuster_already_at_or_past_max_horizon_no_negative_or_zero_extension():
    adjuster = RoadmapPacingAdjuster()
    today = date(2026, 11, 15)
    # Target date is already at the max horizon 366 days
    target_date = today + timedelta(days=366)
    roadmap = _build_test_roadmap(target_date=target_date, available_hours=1.0)
    # Even with huge work, cannot extend beyond max horizon -> days_extended <= 0 -> was_adjusted=False
    nodes = _build_test_tree(roadmap.id, [(600 * 60, False)])

    res = adjuster.adjust_if_behind(roadmap, nodes, today=today)
    assert not res.was_adjusted
    assert res.days_extended == 0


def test_adjuster_archived_status_does_nothing():
    adjuster = RoadmapPacingAdjuster()
    today = date(2026, 11, 15)
    roadmap = _build_test_roadmap(
        target_date=today + timedelta(days=1), status="archived"
    )
    nodes = _build_test_tree(roadmap.id, [(300, False)])
    res = adjuster.adjust_if_behind(roadmap, nodes, today=today)
    assert not res.was_adjusted
    assert res.days_extended == 0


@pytest.mark.asyncio
async def test_service_get_roadmap_tree_lazy_adjusts_and_persists():
    async with AsyncSessionLocal() as db_session:
        user = User(
            id=uuid.uuid4(),
            email=f"fr15_user_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="pw",
            full_name="Student FR15",
            role="student",
        )
        subject = Subject(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Giải tích 1",
            description="Môn học toán",
        )
        db_session.add(user)
        db_session.add(subject)
        await db_session.flush()

        today = date(2026, 11, 15)
        target_date = today + timedelta(days=1)  # 1 day = 120m available
        roadmap = Roadmap(
            id=uuid.uuid4(),
            user_id=user.id,
            subject_id=subject.id,
            title="Lộ trình gấp",
            target_date=target_date,
            available_hours_per_day=2.0,
            progress_percentage=0.0,
            status="behind_schedule",
        )
        db_session.add(roadmap)
        await db_session.flush()

        ch1 = RoadmapNode(
            id=uuid.uuid4(),
            roadmap_id=roadmap.id,
            parent_node_id=None,
            title="Chương 1",
            order_index=1,
            estimated_minutes=360,
            is_unlocked=True,
            is_completed=False,
        )
        db_session.add(ch1)
        await db_session.flush()

        # 3 leaf nodes, 120m each = 360m
        for idx in range(2, 5):
            block = RoadmapNode(
                id=uuid.uuid4(),
                roadmap_id=roadmap.id,
                parent_node_id=ch1.id,
                title=f"Block {idx}",
                order_index=idx,
                estimated_minutes=120,
                is_unlocked=True,
                is_completed=False,
            )
            db_session.add(block)
        await db_session.commit()

        repo = RoadmapRepository(db_session)
        service = RoadmapService(repository=repo)

        tree_response = await service.get_roadmap_tree(roadmap.id, today=today)

        assert tree_response.was_adjusted is True
        assert tree_response.days_extended == 2
        assert tree_response.original_target_date == target_date
        assert tree_response.roadmap.target_date == today + timedelta(days=3)
        assert tree_response.roadmap.status == "active"
        assert "gia hạn thêm 2 ngày" in (tree_response.adjustment_message or "")

        # Check persistence in DB
        reloaded = await repo.get_roadmap_by_id(roadmap.id)
        assert reloaded is not None
        assert reloaded.target_date == today + timedelta(days=3)
        assert reloaded.status == "active"


@pytest.mark.asyncio
async def test_endpoint_get_roadmap_tree_behind_schedule_auto_adjusts_via_api():
    """FR-15 End-to-end: Tests GET /api/v1/roadmaps/{id}/tree with live DB and AsyncClient."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app
    from app.modules.auth.dependencies import get_current_user

    async with AsyncSessionLocal() as db_session:
        user = User(
            id=uuid.uuid4(),
            email=f"fr15_api_{uuid.uuid4().hex[:6]}@example.com",
            hashed_password="pw",
            full_name="Student FR15 API",
            role="student",
        )
        subject = Subject(
            id=uuid.uuid4(),
            user_id=user.id,
            name="Vật lý đại cương",
            description="Môn học lý",
        )
        db_session.add(user)
        db_session.add(subject)
        await db_session.flush()

        today = date.today()
        # 1 day left: 120m available. Workload = 360m -> Behind schedule!
        target_date = today + timedelta(days=1)
        roadmap = Roadmap(
            id=uuid.uuid4(),
            user_id=user.id,
            subject_id=subject.id,
            title="Lộ trình test endpoint",
            target_date=target_date,
            available_hours_per_day=2.0,
            progress_percentage=0.0,
            status="behind_schedule",
        )
        db_session.add(roadmap)
        await db_session.flush()

        ch1 = RoadmapNode(
            id=uuid.uuid4(),
            roadmap_id=roadmap.id,
            parent_node_id=None,
            title="Chương 1",
            order_index=1,
            estimated_minutes=360,
            is_unlocked=True,
            is_completed=False,
        )
        db_session.add(ch1)
        await db_session.flush()

        for idx in range(2, 5):
            block = RoadmapNode(
                id=uuid.uuid4(),
                roadmap_id=roadmap.id,
                parent_node_id=ch1.id,
                title=f"Block {idx}",
                order_index=idx,
                estimated_minutes=120,
                is_unlocked=True,
                is_completed=False,
            )
            db_session.add(block)
        await db_session.commit()

        app.dependency_overrides[get_current_user] = lambda: user

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(f"/api/v1/roadmaps/{roadmap.id}/tree")
                assert response.status_code == 200
                data = response.json()

                assert data["was_adjusted"] is True
                assert data["days_extended"] == 2
                assert data["original_target_date"] == target_date.isoformat()
                assert data["roadmap"]["target_date"] == (today + timedelta(days=3)).isoformat()
                assert data["roadmap"]["status"] == "active"
                assert "gia hạn thêm 2 ngày" in (data["adjustment_message"] or "")

            # Verify persisted in database using fresh query
            from sqlalchemy import select

            query = select(Roadmap).where(Roadmap.id == roadmap.id).execution_options(populate_existing=True)
            result = await db_session.execute(query)
            reloaded = result.scalar_one_or_none()
            assert reloaded is not None
            assert reloaded.target_date == today + timedelta(days=3)
            assert reloaded.status == "active"
        finally:
            app.dependency_overrides.clear()
