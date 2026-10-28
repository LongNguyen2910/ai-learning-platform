import uuid
from datetime import UTC, datetime

import pytest

import app.core.models_registry  # noqa: F401
from app.modules.roadmaps.domain.node_progression_calculator import (
    NodeProgressionCalculator,
)
from app.modules.roadmaps.exceptions import (
    NodeLockedException,
    NodeNotFoundException,
    NodeNotLeafException,
)
from app.modules.roadmaps.models import RoadmapNode


def create_sample_tree() -> tuple[list[RoadmapNode], uuid.UUID, uuid.UUID, uuid.UUID]:
    """Helper creating a 3-tier tree: 1 Chapter -> 1 Topic -> 2 Study Blocks."""
    roadmap_id = uuid.uuid4()
    chapter_id = uuid.uuid4()
    topic_id = uuid.uuid4()
    block1_id = uuid.uuid4()
    block2_id = uuid.uuid4()

    chapter = RoadmapNode(
        id=chapter_id,
        roadmap_id=roadmap_id,
        parent_node_id=None,
        title="Chương 1",
        order_index=1,
        estimated_minutes=0,
        is_unlocked=True,
        is_completed=False,
    )
    topic = RoadmapNode(
        id=topic_id,
        roadmap_id=roadmap_id,
        parent_node_id=chapter_id,
        title="Chủ đề 1.1",
        order_index=2,
        estimated_minutes=0,
        is_unlocked=True,
        is_completed=False,
    )
    block1 = RoadmapNode(
        id=block1_id,
        roadmap_id=roadmap_id,
        parent_node_id=topic_id,
        title="Khối học 1",
        order_index=3,
        estimated_minutes=30,
        is_unlocked=True,
        is_completed=False,
    )
    block2 = RoadmapNode(
        id=block2_id,
        roadmap_id=roadmap_id,
        parent_node_id=topic_id,
        title="Khối học 2",
        order_index=4,
        estimated_minutes=60,
        is_unlocked=False,
        is_completed=False,
    )

    nodes = [chapter, topic, block1, block2]
    return nodes, chapter_id, block1_id, block2_id


def test_complete_first_block_unlocks_next_and_calculates_progress():
    nodes, _chapter_id, block1_id, block2_id = create_sample_tree()
    calculator = NodeProgressionCalculator()
    now = datetime.now(UTC)

    result = calculator.calculate_completion(nodes, block1_id, now)

    assert block1_id in result.completed_node_ids
    assert block2_id in result.unlocked_node_ids
    assert nodes[2].is_completed is True
    assert nodes[3].is_unlocked is True
    # 30 / 90 = 33.33%
    assert result.progress_percentage == 33.33
    assert result.roadmap_status == "active"
    # Topic and chapter not yet completed because block2 is not completed
    assert nodes[0].is_completed is False
    assert nodes[1].is_completed is False


def test_complete_all_blocks_cascades_topic_chapter_and_completes_roadmap():
    nodes, chapter_id, block1_id, block2_id = create_sample_tree()
    calculator = NodeProgressionCalculator()
    now = datetime.now(UTC)

    # Complete first block
    calculator.calculate_completion(nodes, block1_id, now)
    # Complete second block
    result = calculator.calculate_completion(nodes, block2_id, now)

    assert block2_id in result.completed_node_ids
    assert nodes[1].id in result.completed_node_ids  # topic
    assert chapter_id in result.completed_node_ids  # chapter
    assert nodes[0].is_completed is True
    assert nodes[1].is_completed is True
    assert result.progress_percentage == 100.0
    assert result.roadmap_status == "completed"


def test_complete_locked_node_raises_exception():
    nodes, _, _, block2_id = create_sample_tree()
    calculator = NodeProgressionCalculator()

    with pytest.raises(NodeLockedException):
        calculator.calculate_completion(nodes, block2_id)


def test_complete_parent_node_raises_exception():
    nodes, chapter_id, _, _ = create_sample_tree()
    calculator = NodeProgressionCalculator()

    with pytest.raises(NodeNotLeafException):
        calculator.calculate_completion(nodes, chapter_id)


def test_complete_nonexistent_node_raises_exception():
    nodes, _, _, _ = create_sample_tree()
    calculator = NodeProgressionCalculator()

    with pytest.raises(NodeNotFoundException):
        calculator.calculate_completion(nodes, uuid.uuid4())


def test_idempotent_completion_on_already_completed_node():
    nodes, _, block1_id, _ = create_sample_tree()
    calculator = NodeProgressionCalculator()
    now = datetime.now(UTC)

    # Complete first time
    calculator.calculate_completion(nodes, block1_id, now)

    # Complete second time
    result = calculator.calculate_completion(nodes, block1_id, now)
    assert result.completed_node_ids == [block1_id]
    assert result.unlocked_node_ids == []
    assert result.progress_percentage == 33.33


def test_multi_chapter_progression_cascade_and_unlock():
    """Tests sequential progression across multiple chapters (FR-14).
    Chapter 1: Topic 1.1 -> Block 1 (30m, unlocked), Block 2 (30m, locked)
    Chapter 2: Topic 2.1 -> Block 3 (40m, locked)
    Total minutes = 30 + 30 + 40 = 100m.
    """
    roadmap_id = uuid.uuid4()
    ch1_id = uuid.uuid4()
    top1_id = uuid.uuid4()
    b1_id = uuid.uuid4()
    b2_id = uuid.uuid4()

    ch2_id = uuid.uuid4()
    top2_id = uuid.uuid4()
    b3_id = uuid.uuid4()

    nodes = [
        RoadmapNode(
            id=ch1_id,
            roadmap_id=roadmap_id,
            parent_node_id=None,
            title="Chương 1: Giới hạn",
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
            title="Khối 2: Giới hạn hàm số",
            order_index=4,
            estimated_minutes=30,
            is_unlocked=False,
            is_completed=False,
        ),
        RoadmapNode(
            id=ch2_id,
            roadmap_id=roadmap_id,
            parent_node_id=None,
            title="Chương 2: Đạo hàm",
            order_index=5,
            estimated_minutes=0,
            is_unlocked=True,
            is_completed=False,
        ),
        RoadmapNode(
            id=top2_id,
            roadmap_id=roadmap_id,
            parent_node_id=ch2_id,
            title="Chủ đề 2.1: Quy tắc tính đạo hàm",
            order_index=6,
            estimated_minutes=0,
            is_unlocked=True,
            is_completed=False,
        ),
        RoadmapNode(
            id=b3_id,
            roadmap_id=roadmap_id,
            parent_node_id=top2_id,
            title="Khối 3: Đạo hàm cơ bản",
            order_index=7,
            estimated_minutes=40,
            is_unlocked=False,
            is_completed=False,
        ),
    ]

    calculator = NodeProgressionCalculator()
    now = datetime.now(UTC)

    # Step 1: Complete Block 1 (30m / 100m = 30%) -> Unlocks Block 2 in Chapter 1
    res1 = calculator.calculate_completion(nodes, b1_id, now)
    assert b1_id in res1.completed_node_ids
    assert res1.unlocked_node_ids == [b2_id]
    assert nodes[2].is_completed is True
    assert nodes[3].is_unlocked is True
    assert res1.progress_percentage == 30.0
    assert res1.roadmap_status == "active"
    assert nodes[0].is_completed is False  # Chapter 1 not yet completed
    assert nodes[1].is_completed is False  # Topic 1.1 not yet completed
    assert nodes[6].is_unlocked is False  # Block 3 in Chapter 2 still locked

    # Step 2: Complete Block 2 -> Unlocks Block 3 in Chapter 2!
    # Cascades completion upward to Topic 1.1 and Chapter 1!
    res2 = calculator.calculate_completion(nodes, b2_id, now)
    assert b2_id in res2.completed_node_ids
    assert top1_id in res2.completed_node_ids
    assert ch1_id in res2.completed_node_ids
    assert res2.unlocked_node_ids == [b3_id]
    assert nodes[0].is_completed is True  # Chapter 1 cascaded to completed
    assert nodes[1].is_completed is True  # Topic 1.1 cascaded to completed
    assert nodes[4].is_completed is False  # Chapter 2 still active
    assert nodes[6].is_unlocked is True  # Block 3 in Chapter 2 is unlocked
    assert res2.progress_percentage == 60.0  # (30 + 30) / 100 = 60%
    assert res2.roadmap_status == "active"

    # Step 3: Complete Block 3 (final block) -> Cascades Chapter 2 and marks Roadmap completed
    res3 = calculator.calculate_completion(nodes, b3_id, now)
    assert b3_id in res3.completed_node_ids
    assert top2_id in res3.completed_node_ids
    assert ch2_id in res3.completed_node_ids
    assert res3.unlocked_node_ids == []
    assert nodes[4].is_completed is True  # Chapter 2 completed
    assert nodes[5].is_completed is True  # Topic 2.1 completed
    assert res3.progress_percentage == 100.0
    assert res3.roadmap_status == "completed"

