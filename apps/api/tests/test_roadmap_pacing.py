import uuid
from datetime import date, timedelta

import pytest

import app.core.models_registry  # noqa: F401
from app.modules.roadmaps.exceptions import InvalidStudyGoalException
from app.modules.roadmaps.roadmap_tree_builder import RoadmapTreeBuilder
from app.modules.roadmaps.schemas import (
    RawChapterOutline,
    RawCurriculumOutline,
    RawStudyTopic,
)
from app.modules.roadmaps.study_block_pacing_calculator import (
    StudyBlockPacingCalculator,
)


def _make_dummy_curriculum() -> RawCurriculumOutline:
    return RawCurriculumOutline(
        title="Giải tích 1",
        summary="Khóa học giải tích cơ bản",
        chapters=[
            RawChapterOutline(
                title="Chương 1: Giới hạn và Liên tục",
                target_page_start=1,
                target_page_end=20,
                topics=[
                    RawStudyTopic(
                        title="Định nghĩa giới hạn",
                        target_page_start=1,
                        target_page_end=5,
                        is_core=True,
                        complexity_level=1,
                    ),
                    RawStudyTopic(
                        title="Các dạng vô định",
                        target_page_start=6,
                        target_page_end=15,
                        is_core=True,
                        complexity_level=2,
                    ),
                    RawStudyTopic(
                        title="Mở rộng: Giới hạn suy rộng",
                        target_page_start=16,
                        target_page_end=20,
                        is_core=False,
                        complexity_level=3,
                    ),
                ],
            )
        ],
    )


def test_invalid_target_date_raises_exception():
    calc = StudyBlockPacingCalculator()
    today = date(2026, 10, 24)
    past_date = date(2026, 10, 20)

    with pytest.raises(InvalidStudyGoalException):
        calc.calculate_available_minutes(past_date, today, 2.0)


def test_sufficient_time_retains_all_topics():
    calc = StudyBlockPacingCalculator()
    today = date(2026, 10, 24)
    target_date = today + timedelta(days=14)  # 14 days * 2 hrs/day = 1680 mins
    curriculum = _make_dummy_curriculum()

    chapters = calc.allocate(curriculum, target_date, today, 2.0)
    assert len(chapters) == 1
    # 3 topics should all be retained because time is ample
    assert len(chapters[0].topics) == 3


def test_constrained_time_prunes_secondary_topics():
    calc = StudyBlockPacingCalculator()
    today = date(2026, 10, 24)
    # Extremely constrained: 1 day * 0.5 hour = 30 minutes
    # Curriculum requires: (5*5) + (10*7) + (5*10) = 25 + 70 + 50 = 145 mins
    target_date = today + timedelta(days=1)
    curriculum = _make_dummy_curriculum()

    chapters = calc.allocate(curriculum, target_date, today, 0.5)
    assert len(chapters) == 1
    # The non-core topic (is_core=False) should be pruned
    topic_titles = [t.title for t in chapters[0].topics]
    assert "Mở rộng: Giới hạn suy rộng" not in topic_titles
    assert len(chapters[0].topics) == 2


def test_roadmap_tree_builder_unlock_and_order():
    calc = StudyBlockPacingCalculator()
    builder = RoadmapTreeBuilder()
    today = date(2026, 10, 24)
    target_date = today + timedelta(days=7)
    curriculum = _make_dummy_curriculum()

    chapters = calc.allocate(curriculum, target_date, today, 2.0)
    doc_id = uuid.uuid4()
    nodes = builder.build_tree_nodes(chapters, document_id=doc_id)

    assert len(nodes) > 0
    # Check that orders are sequential
    orders = [n.order_index for n in nodes]
    assert orders == list(range(1, len(nodes) + 1))

    # Find leaf nodes (nodes with estimated_minutes > 0)
    leaf_nodes = [n for n in nodes if n.estimated_minutes > 0]
    assert len(leaf_nodes) > 0

    # Only the first leaf node must be unlocked
    assert leaf_nodes[0].is_unlocked is True
    for subsequent_leaf in leaf_nodes[1:]:
        assert subsequent_leaf.is_unlocked is False


def test_fallback_curriculum_extraction():
    from app.modules.roadmaps.ai_curriculum_extractor import AICurriculumExtractor

    extractor = AICurriculumExtractor()
    outline = extractor._generate_fallback_outline(title="Toán Rời Rạc", total_pages=100)

    assert outline.title == "Toán Rời Rạc"
    assert len(outline.chapters) == 2
    assert outline.chapters[0].target_page_start == 1
    assert outline.chapters[1].target_page_end == 100


def test_nested_tree_reconstruction():
    from app.modules.roadmaps.models import RoadmapNode
    from app.modules.roadmaps.service import RoadmapService

    service = RoadmapService(repository=None)  # type: ignore[arg-type]

    c_id = uuid.uuid4()
    t_id = uuid.uuid4()
    b_id = uuid.uuid4()
    rm_id = uuid.uuid4()

    chapter = RoadmapNode(
        id=c_id,
        roadmap_id=rm_id,
        parent_node_id=None,
        title="Chương 1",
        order_index=1,
        estimated_minutes=0,
        is_unlocked=True,
        is_completed=False,
    )
    topic = RoadmapNode(
        id=t_id,
        roadmap_id=rm_id,
        parent_node_id=c_id,
        title="Chủ đề 1.1",
        order_index=2,
        estimated_minutes=0,
        is_unlocked=True,
        is_completed=False,
    )
    block = RoadmapNode(
        id=b_id,
        roadmap_id=rm_id,
        parent_node_id=t_id,
        title="Khối 1",
        order_index=3,
        estimated_minutes=25,
        is_unlocked=True,
        is_completed=False,
    )

    nested_tree = service._build_nested_tree([topic, block, chapter])

    assert len(nested_tree) == 1
    assert nested_tree[0].id == c_id
    assert len(nested_tree[0].children) == 1
    assert nested_tree[0].children[0].id == t_id
    assert len(nested_tree[0].children[0].children) == 1
    assert nested_tree[0].children[0].children[0].id == b_id


def test_slice_study_blocks_edge_cases():
    calc = StudyBlockPacingCalculator()

    # Case 1: 5 pages, complexity 3 (10m/page) -> 50m -> 2 blocks
    topic1 = RawStudyTopic(
        title="Lý thuyết Galois",
        target_page_start=1,
        target_page_end=5,
        complexity_level=3,
        is_core=True,
    )
    blocks1 = calc._slice_into_study_blocks(topic1)
    assert len(blocks1) == 2
    assert blocks1[0].title == "Lý thuyết Galois (Phần 1/2)"
    assert blocks1[1].title == "Lý thuyết Galois (Phần 2/2)"
    assert blocks1[0].target_page_start == 1
    assert blocks1[1].target_page_end == 5

    # Case 2: Inverted page bounds (start > end)
    topic2 = RawStudyTopic(
        title="Inverted Topic",
        target_page_start=10,
        target_page_end=5,
        complexity_level=2,
        is_core=True,
    )
    blocks2 = calc._slice_into_study_blocks(topic2)
    assert len(blocks2) >= 1
    assert blocks2[0].target_page_start <= blocks2[0].target_page_end

    # Case 3: 1 single page with high complexity (complexity 3, 10m/page)
    topic3 = RawStudyTopic(
        title="Định lý Fermat",
        target_page_start=7,
        target_page_end=7,
        complexity_level=3,
        is_core=True,
    )
    blocks3 = calc._slice_into_study_blocks(topic3)
    assert len(blocks3) == 1
    assert blocks3[0].target_page_start == 7
    assert blocks3[0].target_page_end == 7


def test_resolve_total_pages_reads_metadata(tmp_path):
    import json

    from app.modules.roadmaps.service import RoadmapService

    doc_dir = tmp_path / "doc_123"
    doc_dir.mkdir()
    meta_path = doc_dir / "metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({"total_pages": 42}, f)

    service = RoadmapService(repository=None)  # type: ignore[arg-type]
    pages = service._resolve_total_pages(doc_dir)
    assert pages == 42


def test_resolve_total_pages_reads_markdown_pages(tmp_path):
    from app.modules.roadmaps.service import RoadmapService

    doc_dir = tmp_path / "doc_456"
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "page_1.md").write_text("page 1")
    (pages_dir / "page_2.md").write_text("page 2")
    (pages_dir / "page_3.md").write_text("page 3")

    service = RoadmapService(repository=None)  # type: ignore[arg-type]
    pages = service._resolve_total_pages(doc_dir)
    assert pages == 3


def test_roadmap_generate_request_validates_future_date():
    from pydantic import ValidationError

    from app.modules.roadmaps.schemas import RoadmapGenerateRequest

    with pytest.raises(ValidationError):
        RoadmapGenerateRequest(
            subject_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            title="Lộ trình",
            target_date=date.today() - timedelta(days=1),
            available_hours_per_day=2.0,
        )

