import json
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.core.models_registry  # noqa: F401
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.main import app
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.documents.models import Document, Subject
from app.modules.roadmaps.router import _execute_roadmap_pipeline
from app.modules.roadmaps.schemas import RoadmapGenerateRequest


@pytest_asyncio.fixture(autouse=True)
async def cleanup_db_connections():
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def integration_user() -> User:
    async with AsyncSessionLocal() as session:
        unique_email = f"int_user_{uuid.uuid4().hex[:8]}@example.com"
        user = User(
            id=uuid.uuid4(),
            email=unique_email,
            hashed_password="hashed_password",
            full_name="Integration Test Student",
            role="user",
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def async_client(integration_user: User):
    app.dependency_overrides[get_current_user] = lambda: integration_user
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generate_roadmap_with_nonexistent_subject_returns_404_no_500(
    async_client: AsyncClient,
):
    """Verifies that non-existent subject_id returns 404 instead of raw 500 DB FK error."""
    payload = {
        "subject_id": "11111111-1111-1111-1111-111111111111",
        "document_id": "22222222-2222-2222-2222-222222222222",
        "title": "Lộ trình Giải tích trong 4 tuần",
        "target_date": (date.today() + timedelta(days=28)).isoformat(),
        "available_hours_per_day": 2.0,
        "study_goal": "Đạt điểm A môn Giải tích 1",
    }

    response = await async_client.post("/api/v1/roadmaps/generate", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "11111111-1111-1111-1111-111111111111" in data["detail"]
    assert "not found" in data["detail"]


@pytest.mark.asyncio
async def test_generate_roadmap_with_nonexistent_document_returns_404(
    async_client: AsyncClient,
    integration_user: User,
):
    """Verifies that non-existent document_id returns 404 when subject exists."""
    async with AsyncSessionLocal() as session:
        subject = Subject(
            id=uuid.uuid4(),
            user_id=integration_user.id,
            name="Giải tích 1",
            code="CALC1",
        )
        session.add(subject)
        await session.commit()

    random_doc_id = str(uuid.uuid4())
    payload = {
        "subject_id": str(subject.id),
        "document_id": random_doc_id,
        "title": "Lộ trình Giải tích trong 4 tuần",
        "target_date": (date.today() + timedelta(days=28)).isoformat(),
        "available_hours_per_day": 2.0,
        "study_goal": "Đạt điểm A môn Giải tích 1",
    }

    response = await async_client.post("/api/v1/roadmaps/generate", json=payload)
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert random_doc_id in data["detail"]
    assert "not parsed" in data["detail"]


@pytest.mark.asyncio
async def test_subject_endpoints_and_full_roadmap_generation_flow(
    async_client: AsyncClient,
    integration_user: User,
    tmp_path: Path,
    monkeypatch,
):
    """Full end-to-end integration test creating subject, document, generating roadmap and tree."""
    monkeypatch.setattr(settings, "PARSED_DIR", str(tmp_path / "parsed"))
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))

    # 1. Create Subject via API
    sub_payload = {
        "name": "Giải tích 1",
        "code": "MAT101",
        "description": "Toán cao cấp",
        "color_hex": "#4F46E5",
    }
    sub_res = await async_client.post("/api/v1/subjects", json=sub_payload)
    assert sub_res.status_code == 201
    subject_id = uuid.UUID(sub_res.json()["id"])

    # Verify listing subjects
    list_res = await async_client.get("/api/v1/subjects")
    assert list_res.status_code == 200
    assert any(s["id"] == str(subject_id) for s in list_res.json())

    # 2. Prepare mock parsed document on disk
    doc_id = uuid.uuid4()
    doc_dir = tmp_path / "parsed" / str(doc_id)
    doc_dir.mkdir(parents=True)
    pages_dir = doc_dir / "pages"
    pages_dir.mkdir(parents=True)

    # Write dummy document pages with explicit utf-8 encoding
    (pages_dir / "page_1.md").write_text("# Chương 1: Giới hạn hàm số\nNội dung giới hạn.", encoding="utf-8")
    (pages_dir / "page_2.md").write_text("# Chương 2: Đạo hàm và vi phân\nNội dung đạo hàm.", encoding="utf-8")
    (pages_dir / "page_3.md").write_text("# Chương 3: Phép tính tích phân\nNội dung tích phân.", encoding="utf-8")
    full_doc = "# Mục lục\n- Chương 1: Giới hạn\n- Chương 2: Đạo hàm\n- Chương 3: Tích phân\n"
    (doc_dir / "full_document.md").write_text(full_doc, encoding="utf-8")

    meta_content = {
        "document_id": str(doc_id),
        "title": "Giáo trình Giải tích 1",
        "file_path": str(tmp_path / "uploads" / f"{doc_id}.pdf"),
        "file_size_kb": 100,
        "total_pages": 3,
        "status": "ready",
        "pages": [],
    }
    with open(doc_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta_content, f)

    # 3. Call generate roadmap endpoint
    future_date = date.today() + timedelta(days=21)
    gen_payload = {
        "subject_id": str(subject_id),
        "document_id": str(doc_id),
        "title": "Lộ trình Giải tích trong 3 tuần",
        "target_date": future_date.isoformat(),
        "available_hours_per_day": 2.0,
        "study_goal": "Đạt điểm A môn Giải tích 1",
    }

    gen_res = await async_client.post("/api/v1/roadmaps/generate", json=gen_payload)
    assert gen_res.status_code == 202
    gen_data = gen_res.json()
    task_id = gen_data["task_id"]
    roadmap_id = uuid.UUID(gen_data["roadmap_id"])

    # 4. Run background pipeline directly
    req_dto = RoadmapGenerateRequest(
        subject_id=subject_id,
        document_id=doc_id,
        title=gen_payload["title"],
        target_date=future_date,
        available_hours_per_day=2.0,
        study_goal=gen_payload["study_goal"],
    )
    await _execute_roadmap_pipeline(task_id, roadmap_id, req_dto)

    # 5. Check task status via API
    task_res = await async_client.get(f"/api/v1/roadmaps/tasks/{task_id}")
    assert task_res.status_code == 200
    assert task_res.json()["status"] == "completed"
    assert task_res.json()["progress_percent"] == 100

    # 6. Check Roadmap tree via API
    tree_res = await async_client.get(f"/api/v1/roadmaps/{roadmap_id}/tree")
    assert tree_res.status_code == 200
    tree_data = tree_res.json()
    assert tree_data["roadmap"]["id"] == str(roadmap_id)
    assert tree_data["total_nodes"] > 0
    assert tree_data["total_estimated_minutes"] > 0

    tree = tree_data["tree"]
    assert len(tree) > 0
    # First chapter should have unlocked child nodes
    first_chapter = tree[0]
    assert first_chapter["is_unlocked"] is True
    assert len(first_chapter["children"]) > 0

    # 7. Test FR-14 Complete Node Endpoint with Real DB Persistence
    first_leaf = first_chapter["children"][0]["children"][0]
    first_leaf_id = uuid.UUID(str(first_leaf["id"]))
    assert first_leaf["is_unlocked"] is True
    assert first_leaf["is_completed"] is False

    complete_res = await async_client.post(
        f"/api/v1/roadmaps/nodes/{first_leaf_id}/complete"
    )
    assert complete_res.status_code == 200
    complete_data = complete_res.json()
    assert complete_data["completed_node_id"] == str(first_leaf_id)
    assert complete_data["progress_percentage"] > 0
    assert complete_data["roadmap_status"] == "active"

    # 8. Verify state persistence via Tree endpoint
    tree_res_updated = await async_client.get(f"/api/v1/roadmaps/{roadmap_id}/tree")
    assert tree_res_updated.status_code == 200
    updated_tree = tree_res_updated.json()["tree"]

    all_blocks = [
        b
        for ch in updated_tree
        for top in ch["children"]
        for b in top["children"]
    ]
    completed_leaf = next(b for b in all_blocks if b["id"] == str(first_leaf_id))
    assert completed_leaf["is_completed"] is True
    assert completed_leaf["completed_at"] is not None

    if complete_data["unlocked_node_ids"]:
        unlocked_id = complete_data["unlocked_node_ids"][0]
        unlocked_block = next(b for b in all_blocks if b["id"] == unlocked_id)
        assert unlocked_block["is_unlocked"] is True

    # 9. Test GET /api/v1/roadmaps/subject/{subject_id} has roadmap_id field
    list_sub_res = await async_client.get(f"/api/v1/roadmaps/subject/{subject_id}")
    assert list_sub_res.status_code == 200
    sub_roadmaps = list_sub_res.json()
    assert any(r["roadmap_id"] == str(roadmap_id) for r in sub_roadmaps)



