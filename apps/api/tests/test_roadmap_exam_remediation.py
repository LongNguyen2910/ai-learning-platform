import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import app.core.models_registry  # noqa: F401
from app.core.database import get_db
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.documents.models import Document
from app.modules.quizzes.models import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from app.modules.roadmaps.ai_curriculum_extractor import (
    AICurriculumExtractor,
    SourceDocumentInput,
)
from app.modules.roadmaps.domain.study_block_pacing_calculator import (
    StudyBlockPacingCalculator,
)
from app.modules.roadmaps.models import Roadmap, RoadmapNode
from app.modules.roadmaps.roadmap_tree_builder import RoadmapTreeBuilder
from app.modules.roadmaps.service import SourceDocumentInput as ServiceSourceDoc


@pytest.fixture
def mock_user() -> User:
    return User(
        id=uuid.uuid4(),
        email="student@example.com",
        hashed_password="hashed_pwd",
        full_name="Test Student",
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


def test_generate_roadmap_exam_blocked_when_incomplete(
    client: TestClient, mock_user: User
):
    """Exam generation must return 400 when roadmap progress < 100%."""
    roadmap_id = uuid.uuid4()
    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Incomplete Roadmap",
        target_date=date.today() + timedelta(days=14),
        available_hours_per_day=2.0,
        progress_percentage=65.0,
        status="active",
        exam_status="locked",
        iteration=1,
        created_at=datetime.now(UTC),
    )
    fake_roadmap.nodes = []

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)

        res = client.post(f"/api/v1/roadmaps/{roadmap_id}/exam/generate")
        assert res.status_code == 400
        assert "locked" in res.json()["detail"].lower()


def test_generate_roadmap_exam_success_across_multiple_subject_documents(
    client: TestClient, mock_user: User, tmp_path: Path, monkeypatch
):
    """When roadmap is 100% completed, generates a multi-document Final Assessment across the subject."""
    monkeypatch.setattr("app.core.config.settings.GEMINI_API_KEY", "")
    roadmap_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    doc1_id = uuid.uuid4()
    doc2_id = uuid.uuid4()

    doc1_dir = tmp_path / str(doc1_id)
    doc2_dir = tmp_path / str(doc2_id)
    (doc1_dir / "pages").mkdir(parents=True)
    (doc2_dir / "pages").mkdir(parents=True)
    (doc1_dir / "pages" / "page_1.md").write_text(
        "# Ma trận và Định thức\nNội dung đại số tuyến tính.", encoding="utf-8"
    )
    (doc2_dir / "pages" / "page_1.md").write_text(
        "# Không gian Vector và Giá trị riêng\nNội dung không gian vector.",
        encoding="utf-8",
    )

    ch_id = uuid.uuid4()
    tp1_id = uuid.uuid4()
    tp2_id = uuid.uuid4()

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=subject_id,
        title="Linear Algebra Complete",
        target_date=date.today() + timedelta(days=14),
        available_hours_per_day=2.0,
        progress_percentage=100.0,
        status="completed",
        exam_status="ready",
        iteration=1,
        created_at=datetime.now(UTC),
    )
    fake_roadmap.nodes = [
        RoadmapNode(
            id=ch_id,
            roadmap_id=roadmap_id,
            parent_node_id=None,
            document_id=doc1_id,
            title="Chapter 1",
            order_index=0,
            estimated_minutes=60,
            is_unlocked=True,
            is_completed=True,
        ),
        RoadmapNode(
            id=tp1_id,
            roadmap_id=roadmap_id,
            parent_node_id=ch_id,
            document_id=doc1_id,
            title="Matrices & Determinants",
            target_page_start=1,
            target_page_end=5,
            order_index=1,
            estimated_minutes=30,
            is_unlocked=True,
            is_completed=True,
        ),
        RoadmapNode(
            id=tp2_id,
            roadmap_id=roadmap_id,
            parent_node_id=ch_id,
            document_id=doc2_id,
            title="Eigenvalues & Eigenvectors",
            target_page_start=1,
            target_page_end=6,
            order_index=2,
            estimated_minutes=30,
            is_unlocked=True,
            is_completed=True,
        ),
    ]

    with (
        patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls,
        patch.object(
            app.dependency_overrides[get_db](), "add"
        ),
        patch(
            "app.modules.roadmaps.service.RoadmapService._resolve_subject_source_documents",
            new_callable=AsyncMock,
        ) as mock_resolve_docs,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.session = app.dependency_overrides[get_db]()
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_latest_exam_quiz = AsyncMock(return_value=None)
        mock_resolve_docs.return_value = [
            ServiceSourceDoc(
                document_id=str(doc1_id),
                title="Linear Algebra Part 1.pdf",
                total_pages=5,
                doc_dir=doc1_dir,
            ),
            ServiceSourceDoc(
                document_id=str(doc2_id),
                title="Linear Algebra Part 2.pdf",
                total_pages=6,
                doc_dir=doc2_dir,
            ),
        ]

        res = client.post(f"/api/v1/roadmaps/{roadmap_id}/exam/generate")
        assert res.status_code == 201
        data = res.json()
        assert data["roadmap_id"] == str(roadmap_id)
        assert data["total_questions"] >= 10
        source_doc_ids = {q["source_document_id"] for q in data["questions"]}
        assert str(doc1_id) in source_doc_ids
        assert str(doc2_id) in source_doc_ids


def test_submit_roadmap_exam_pass_at_or_above_50_percent(
    client: TestClient, mock_user: User
):
    """Submitting an exam with >= 50% correct answers marks exam_status as 'passed'."""
    roadmap_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    q1 = QuizQuestion(
        id=uuid.uuid4(),
        quiz_id=quiz_id,
        question_text="Q1",
        bloom_level="remember",
        options=[{"key": "A", "text": "Opt A"}, {"key": "B", "text": "Opt B"}],
        correct_option="A",
        explanation="Exp 1",
        target_page=2,
        topic_tag="Matrices",
        source_document_id=doc_id,
        source_document_title="Algebra.pdf",
    )
    q2 = QuizQuestion(
        id=uuid.uuid4(),
        quiz_id=quiz_id,
        question_text="Q2",
        bloom_level="understand",
        options=[{"key": "A", "text": "Opt A"}, {"key": "B", "text": "Opt B"}],
        correct_option="B",
        explanation="Exp 2",
        target_page=4,
        topic_tag="Eigenvalues",
        source_document_id=doc_id,
        source_document_title="Algebra.pdf",
    )

    fake_quiz = Quiz(
        id=quiz_id,
        user_id=mock_user.id,
        document_id=doc_id,
        roadmap_id=roadmap_id,
        title="Final Assessment",
        total_questions=2,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    fake_quiz.questions = [q1, q2]
    fake_quiz.attempts = []

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=uuid.uuid4(),
        title="Algebra Roadmap",
        target_date=date.today() + timedelta(days=10),
        available_hours_per_day=2.0,
        progress_percentage=100.0,
        status="completed",
        exam_status="ready",
        iteration=1,
        created_at=datetime.now(UTC),
    )
    fake_roadmap.nodes = []

    with patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.session = app.dependency_overrides[get_db]()
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_latest_exam_quiz = AsyncMock(return_value=fake_quiz)

        # Answer 1 out of 2 correctly -> 50.0% -> PASS
        res = client.post(
            f"/api/v1/roadmaps/{roadmap_id}/exam/submit",
            json={
                "answers": [
                    {"question_id": str(q1.id), "selected_option": "A"},
                    {"question_id": str(q2.id), "selected_option": "A"},
                ]
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["score"] == 50.0
        assert data["passed"] is True
        assert data["exam_status"] == "passed"
        assert fake_roadmap.exam_status == "passed"


def test_submit_roadmap_exam_fail_below_50_percent_and_remediate(
    client: TestClient, mock_user: User
):
    """Scoring < 50% marks exam_status='failed', records weak topics, and allows remediation into Iteration #2."""
    roadmap_id = uuid.uuid4()
    new_roadmap_id = uuid.uuid4()
    subject_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    q1 = QuizQuestion(
        id=uuid.uuid4(),
        quiz_id=quiz_id,
        question_text="Q1 on Limits",
        bloom_level="remember",
        options=[{"key": "A", "text": "Opt A"}, {"key": "B", "text": "Opt B"}],
        correct_option="A",
        explanation="Exp 1",
        target_page=2,
        topic_tag="Limits & Continuity",
        source_document_id=doc_id,
        source_document_title="Calculus.pdf",
    )
    q2 = QuizQuestion(
        id=uuid.uuid4(),
        quiz_id=quiz_id,
        question_text="Q2 on Derivatives",
        bloom_level="apply",
        options=[{"key": "A", "text": "Opt A"}, {"key": "B", "text": "Opt B"}],
        correct_option="B",
        explanation="Exp 2",
        target_page=8,
        topic_tag="Chain Rule Derivatives",
        source_document_id=doc_id,
        source_document_title="Calculus.pdf",
    )

    fake_quiz = Quiz(
        id=quiz_id,
        user_id=mock_user.id,
        document_id=doc_id,
        roadmap_id=roadmap_id,
        title="Final Assessment",
        total_questions=2,
        time_limit_minutes=15,
        created_at=datetime.now(UTC),
    )
    fake_quiz.questions = [q1, q2]
    fake_quiz.attempts = []

    fake_roadmap = Roadmap(
        id=roadmap_id,
        user_id=mock_user.id,
        subject_id=subject_id,
        title="Calculus 1",
        target_date=date.today() + timedelta(days=10),
        available_hours_per_day=2.0,
        progress_percentage=100.0,
        status="completed",
        exam_status="ready",
        iteration=1,
        created_at=datetime.now(UTC),
    )
    fake_roadmap.nodes = []

    with (
        patch("app.modules.roadmaps.router.RoadmapRepository") as mock_repo_cls,
        patch("app.modules.roadmaps.router._execute_roadmap_pipeline") as mock_pipeline,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.session = app.dependency_overrides[get_db]()
        mock_repo.get_roadmap_by_id = AsyncMock(return_value=fake_roadmap)
        mock_repo.get_latest_exam_quiz = AsyncMock(return_value=fake_quiz)

        # 1. Submit all wrong -> 0.0% (< 50%) -> FAIL
        submit_res = client.post(
            f"/api/v1/roadmaps/{roadmap_id}/exam/submit",
            json={
                "answers": [
                    {"question_id": str(q1.id), "selected_option": "B"},
                    {"question_id": str(q2.id), "selected_option": "A"},
                ]
            },
        )
        assert submit_res.status_code == 200
        sub_data = submit_res.json()
        assert sub_data["score"] == 0.0
        assert sub_data["passed"] is False
        assert sub_data["exam_status"] == "failed"
        assert "Limits & Continuity" in sub_data["weak_topics"]
        assert "Chain Rule Derivatives" in sub_data["weak_topics"]
        assert fake_roadmap.exam_status == "failed"

        # 2. Trigger remediation -> archives old roadmap and creates Iteration #2
        new_roadmap = Roadmap(
            id=new_roadmap_id,
            user_id=mock_user.id,
            subject_id=subject_id,
            title="Calculus 1 (Adaptive Iteration #2)",
            target_date=date.today() + timedelta(days=15),
            available_hours_per_day=2.0,
            progress_percentage=0.0,
            status="generating",
            exam_status="locked",
            iteration=2,
            parent_roadmap_id=roadmap_id,
            weak_topics=sub_data["weak_topics"],
            created_at=datetime.now(UTC),
        )
        mock_repo.create_roadmap = AsyncMock(return_value=new_roadmap)

        rem_res = client.post(f"/api/v1/roadmaps/{roadmap_id}/remediate")
        assert rem_res.status_code == 202
        rem_data = rem_res.json()
        assert rem_data["roadmap_id"] == str(new_roadmap_id)
        assert fake_roadmap.status == "archived"
        mock_repo.create_roadmap.assert_awaited_once()
        mock_pipeline.assert_called_once()


def test_remediated_roadmap_is_longer_and_more_detailed():
    """Verifies that Iteration #2 with weak_topics produces more chapters, topics, and study blocks than Iteration #1."""
    extractor = AICurriculumExtractor()
    calculator = StudyBlockPacingCalculator()
    builder = RoadmapTreeBuilder()
    doc_uuid = uuid.uuid4()
    today = date.today()

    # Iteration 1 (Initial Roadmap)
    outline_v1 = extractor._generate_fallback_outline(
        title="Calculus",
        total_pages=20,
        document_id=str(doc_uuid),
        weak_topics=None,
        iteration=1,
    )
    planned_v1 = calculator.allocate(
        curriculum=outline_v1,
        target_date=today + timedelta(days=14),
        today=today,
        hours_per_day=2.0,
    )
    nodes_v1 = builder.build_tree_nodes(planned_v1, document_id=doc_uuid)

    # Iteration 2 (Adaptive Remediation after failing Limits & Derivatives)
    outline_v2 = extractor._generate_fallback_outline(
        title="Calculus (Adaptive Iteration #2)",
        total_pages=20,
        document_id=str(doc_uuid),
        weak_topics=["Limits & Continuity", "Chain Rule Derivatives"],
        iteration=2,
    )
    planned_v2 = calculator.allocate(
        curriculum=outline_v2,
        target_date=today + timedelta(days=21),
        today=today,
        hours_per_day=2.0,
        force_allow_secondary=True,
        remediation_multiplier=1.5,
    )
    nodes_v2 = builder.build_tree_nodes(planned_v2, document_id=doc_uuid)

    total_mins_v1 = sum(n.estimated_minutes for n in nodes_v1)
    total_mins_v2 = sum(n.estimated_minutes for n in nodes_v2)

    assert len(outline_v2.chapters) > len(outline_v1.chapters)
    assert len(nodes_v2) > len(nodes_v1)
    assert total_mins_v2 > total_mins_v1
