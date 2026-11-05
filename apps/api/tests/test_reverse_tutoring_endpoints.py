import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.chat.router import (
    get_chat_llm_client,
    get_chat_rag_service,
    get_chat_repository,
)
from app.modules.chat.schemas import RetrievedChunkDTO

USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
DOC_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")

USER = User(
    id=USER_ID,
    email="feynman_student@example.com",
    hashed_password="x",
    role="student",
    is_active=True,
)


class FakeRepository:
    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, SimpleNamespace] = {}
        self.messages: list[SimpleNamespace] = []

    def add_session(self, user_id=USER_ID) -> SimpleNamespace:
        session = SimpleNamespace(
            id=uuid.uuid4(),
            user_id=user_id,
            document_id=DOC_ID,
            title="Phiên Đảo Vai",
            created_at=datetime.now(UTC),
        )
        self.sessions[session.id] = session
        return session

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def list_recent_messages(self, session_id, limit=20):
        return [m for m in self.messages if m.session_id == session_id][-limit:]

    async def add_message(
        self,
        session_id,
        sender,
        content,
        socratic_tier=0,
        citations=None,
        token_count=0,
        mode="standard",
        mode_metadata=None,
        **kwargs,
    ):
        msg = SimpleNamespace(
            id=uuid.uuid4(),
            session_id=session_id,
            sender=sender,
            content=content,
            mode=mode,
            mode_metadata=mode_metadata or {},
            socratic_tier=socratic_tier,
            citations=citations or [],
            token_count=token_count,
            created_at=datetime.now(UTC),
        )
        self.messages.append(msg)
        return msg


class FakeLLM:
    def __init__(self, output_chunks: list[str] | None = None) -> None:
        self.output_chunks = output_chunks or ["Phản hồi từ bạn học"]
        self.calls: list[dict] = []

    async def stream(self, system_prompt, history, user_message):
        self.calls.append(
            {"system_prompt": system_prompt, "history": list(history), "user_message": user_message}
        )
        for piece in self.output_chunks:
            yield piece


def _rag() -> AsyncMock:
    rag = AsyncMock()
    rag.retrieve_relevant_chunks.return_value = [
        RetrievedChunkDTO(
            chunk_id="chunk-1",
            page_number=14,
            chunk_index=0,
            score=0.9,
            content="Định luật Coulomb: $F = k \\frac{|q_1 q_2|}{r^2}$",
            has_formula=True,
            has_image=False,
            citation_tag="[[Trang 14]]",
        )
    ]
    return rag


def parse_sse(raw: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw.strip().split("\n\n"):
        if not block.strip():
            continue
        lines = block.split("\n")
        event = lines[0].removeprefix("event: ")
        data = json.loads(lines[1].removeprefix("data: "))
        events.append((event, data))
    return events


@pytest.fixture
def fake_repo():
    return FakeRepository()


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def client(fake_repo, fake_llm):
    app.dependency_overrides[get_current_active_user] = lambda: USER
    app.dependency_overrides[get_chat_repository] = lambda: fake_repo
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_llm
    app.dependency_overrides[get_chat_rag_service] = lambda: _rag()
    with TestClient(app) as c:
        yield c
    for dep in (get_current_active_user, get_chat_repository, get_chat_llm_client, get_chat_rag_service):
        app.dependency_overrides.pop(dep, None)


def test_reverse_tutoring_suggest_topics_stream(client, fake_repo):
    session = fake_repo.add_session()
    url = f"/api/v1/chat/sessions/{session.id}/messages/stream"

    resp = client.post(
        url,
        json={
            "content": "Gợi ý chủ đề cho mình",
            "mode": "reverse_tutoring",
            "reverse_action": "suggest_topics",
            "page_number": 14,
        },
    )
    assert resp.status_code == 200
    events = parse_sse(resp.text)
    event_names = [e for e, _ in events]
    assert event_names == ["meta", "citations", "token", "done"]

    meta = next(d for e, d in events if e == "meta")
    assert meta["mode"] == "reverse_tutoring"
    assert meta["reverse_phase"] == "suggest"

    done = next(d for e, d in events if e == "done")
    assert done["reverse_phase"] == "suggest"


def test_reverse_tutoring_roleplay_and_evaluation_flow(client, fake_repo, fake_llm):
    session = fake_repo.add_session()
    url = f"/api/v1/chat/sessions/{session.id}/messages/stream"

    # Turn 1: Start roleplay session
    resp1 = client.post(
        url,
        json={
            "content": "Để mình giảng cho bạn về Định luật Coulomb nhé: lực hút hoặc đẩy tỉ lệ nghịch với bình phương khoảng cách.",
            "mode": "reverse_tutoring",
            "reverse_action": "start_session",
            "target_concept": "Định luật Coulomb",
        },
    )
    assert resp1.status_code == 200
    events1 = parse_sse(resp1.text)
    meta1 = next(d for e, d in events1 if e == "meta")
    assert meta1["reverse_phase"] == "roleplay"
    assert meta1["turn_count"] == 1
    assert meta1["target_concept"] == "Định luật Coulomb"

    # Turn 2: Evaluate with Feynman rubric
    eval_output = """
### 🎓 Kết Quả Đánh Giá Giảng Bài (Feynman Rubric)

| Tiêu chí | Điểm | Nhận xét chi tiết |
| :--- | :---: | :--- |
| **1. Độ chính xác cốt lõi** | 9/10 | Nêu đúng tỉ lệ nghịch bình phương khoảng cách. |
| **2. Tính trực quan & Dễ hiểu** | 8/10 | Dùng từ ngữ rõ ràng. |
| **3. Khả năng bắt bẻ lỗi sai** | 9/10 | Gỡ rối tốt. |

**💡 Điểm sáng:** Nắm vững công thức.  
**🎯 Lỗ hổng cần khắc phục:** Cần bổ sung vai trò hằng số điện môi.  
**📖 Đề xuất ôn tập:** Xem lại [[Trang 14]].

```json:rubric_metadata
{
  "accuracy_score": 9,
  "simplicity_score": 8,
  "misconception_score": 9,
  "feedback_summary": "Giải thích xuất sắc định luật Coulomb."
}
```
"""
    fake_llm.output_chunks = [eval_output]

    resp2 = client.post(
        url,
        json={
            "content": "Mình giải thích xong rồi, chấm điểm giúp mình với!",
            "mode": "reverse_tutoring",
            "reverse_action": "evaluate",
            "target_concept": "Định luật Coulomb",
        },
    )
    assert resp2.status_code == 200
    events2 = parse_sse(resp2.text)
    done2 = next(d for e, d in events2 if e == "done")
    assert done2["reverse_phase"] == "evaluate"
    assert done2["rubric"] is not None
    assert done2["rubric"]["accuracy_score"] == 9
    assert done2["rubric"]["simplicity_score"] == 8
    assert done2["rubric"]["misconception_score"] == 9

    # Verify messages stored in repo
    list_resp = client.get(f"/api/v1/chat/sessions/{session.id}/messages")
    assert list_resp.status_code == 200
    stored_messages = list_resp.json()
    assert len(stored_messages) == 4  # 2 user + 2 assistant messages
    assistant_eval_msg = stored_messages[-1]
    assert assistant_eval_msg["mode"] == "reverse_tutoring"
    assert assistant_eval_msg["mode_metadata"]["reverse_phase"] == "evaluate"
    assert assistant_eval_msg["mode_metadata"]["rubric"]["accuracy_score"] == 9
