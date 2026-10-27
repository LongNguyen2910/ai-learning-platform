import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.modules.chat.guardrails import (
    HOMEWORK_REFUSAL_MESSAGE,
    JAILBREAK_REFUSAL_MESSAGE,
    GuardrailResult,
    analyze_query,
)
from app.modules.chat.llm_client import ChatLLMClient, ChatTurn, gemini_chat_client
from app.modules.chat.models import ChatMessage, ChatSession
from app.modules.chat.prompt_composer import (
    compose_system_prompt,
    has_stuck_signal,
    resolve_socratic_tier,
)
from app.modules.chat.repository import (
    SENDER_ASSISTANT,
    SENDER_USER,
    ChatRepository,
    chat_repository,
)
from app.modules.chat.schemas import (
    ChatMode,
    ChatRequest,
    RetrievedChunkDTO,
    SSEStreamEvent,
)
from app.modules.chat.socratic_tiers import SOLVED_MARKER
from app.modules.documents.vector_service import (
    DocumentVectorService,
    document_vector_service,
)

logger = logging.getLogger(__name__)


class ChatRAGService:
    """Manages LlamaIndex and Qdrant retrieval pipeline for RAG chat and tutors."""

    def __init__(self, vector_service: DocumentVectorService | None = None) -> None:
        self.vector_service = vector_service or document_vector_service

    async def retrieve_relevant_chunks(
        self,
        document_id: str,
        query: str,
        page_number: int | None = None,
        similarity_top_k: int = 5,
        score_threshold: float = 0.5,
    ) -> list[RetrievedChunkDTO]:
        """Thực thi truy vấn tìm kiếm chunks liên quan từ Qdrant qua LlamaIndex."""
        retriever = self.vector_service.get_retriever(
            document_id=document_id,
            page_number=page_number,
            similarity_top_k=similarity_top_k,
        )

        try:
            nodes_with_score = await retriever.aretrieve(query)
        except (ValueError, NotImplementedError) as exc:
            # Fallback to running synchronous retrieval in worker thread if async client is not configured
            if "Async client is not initialized" in str(exc):
                nodes_with_score = await asyncio.to_thread(retriever.retrieve, query)
            else:
                raise

        results: list[RetrievedChunkDTO] = []
        for item in nodes_with_score:
            score = float(item.score if item.score is not None else 0.0)
            if score < score_threshold:
                continue

            meta = item.node.metadata or {}
            page_num = int(meta.get("page_number", 1))
            chunk_idx = int(meta.get("chunk_index", 0))
            has_formula = bool(meta.get("has_formula", False))
            has_image = bool(meta.get("has_image", False))

            results.append(
                RetrievedChunkDTO(
                    chunk_id=item.node.node_id,
                    page_number=page_num,
                    chunk_index=chunk_idx,
                    score=round(score, 4),
                    content=item.node.get_content(),
                    has_formula=has_formula,
                    has_image=has_image,
                    citation_tag=f"[[Trang {page_num}]]",
                )
            )

        return results


chat_rag_service = ChatRAGService()


# ============================================================================
# Socratic Chat orchestration: Guardrail -> RAG Query -> Prompt Composer -> Gemini
# ============================================================================

HISTORY_LIMIT = 10
SHORT_QUERY_CHARS = 40
MAX_RETRIEVAL_QUERY_CHARS = 1000


class MarkerStreamFilter:
    """Lọc một marker ẩn khỏi luồng token, kể cả khi marker bị cắt ngang giữa 2 chunk.

    Giữ lại (holdback) phần đuôi của buffer có thể là tiền tố của marker cho tới khi chắc chắn.
    """

    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.found = False
        self._buffer = ""

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        if self.marker in self._buffer:
            self.found = True
            self._buffer = self._buffer.replace(self.marker, "")

        holdback = 0
        for size in range(min(len(self.marker) - 1, len(self._buffer)), 0, -1):
            if self.marker.startswith(self._buffer[-size:]):
                holdback = size
                break

        emit_upto = len(self._buffer) - holdback
        emitted, self._buffer = self._buffer[:emit_upto], self._buffer[emit_upto:]
        return emitted

    def flush(self) -> str:
        remaining, self._buffer = self._buffer, ""
        return remaining


def _sse(event: str, data: dict[str, Any]) -> str:
    return SSEStreamEvent(event=event, data=data).encode()


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0


class SocraticChatService:
    """Điều phối luồng chat Socratic 3 tầng và stream kết quả dưới dạng SSE."""

    def __init__(
        self,
        rag_service: ChatRAGService,
        llm_client: ChatLLMClient,
        repository: ChatRepository,
        score_threshold: float = 0.5,
        similarity_top_k: int = 5,
    ) -> None:
        self.rag_service = rag_service
        self.llm_client = llm_client
        self.repository = repository
        self.score_threshold = score_threshold
        self.similarity_top_k = similarity_top_k

    # ---------------------------------------------------------------- decisions

    @staticmethod
    def previous_tier(history: list[ChatMessage]) -> int:
        for message in reversed(history):
            if message.sender == SENDER_ASSISTANT:
                return int(message.socratic_tier or 0)
        return 0

    @staticmethod
    def decide_tier(
        request: ChatRequest, guard: GuardrailResult, prev_tier: int
    ) -> tuple[int, bool]:
        """Trả về (tier, is_new_question) cho lượt Socratic hiện tại."""
        if guard.is_jailbreak and request.requested_tier is None:
            # Fail-closed: nỗ lực injection không được phép "leo tầng" để moi đáp án.
            return max(prev_tier, 1), False

        is_new_question = request.new_question or (
            prev_tier > 0
            and (guard.is_homework or guard.is_exam_structure)
            and not has_stuck_signal(request.content)
        )
        tier = resolve_socratic_tier(
            user_query=request.content,
            prev_tier=prev_tier,
            is_new_question=is_new_question,
            requested_tier=request.requested_tier,
        )
        return tier, is_new_question

    @staticmethod
    def build_retrieval_query(
        query: str, history: list[ChatMessage], include_previous: bool
    ) -> str:
        """Follow-up kiểu "mình chưa hiểu" không mang ngữ nghĩa bài toán -> ghép đề bài trước đó
        vào truy vấn để retrieval vẫn trúng đúng định lý/công thức."""
        if not include_previous and len(query) >= SHORT_QUERY_CHARS:
            return query[:MAX_RETRIEVAL_QUERY_CHARS]

        previous_user = [m.content for m in history if m.sender == SENDER_USER][-2:]
        combined = "\n".join([query, *reversed(previous_user)])
        return combined[:MAX_RETRIEVAL_QUERY_CHARS]

    @staticmethod
    def to_chat_turns(history: list[ChatMessage]) -> list[ChatTurn]:
        return [
            ChatTurn(role="user" if m.sender == SENDER_USER else "model", text=m.content)
            for m in history
        ]

    async def _retrieve(
        self, document_id: str, query: str, page_number: int | None
    ) -> list[RetrievedChunkDTO]:
        try:
            return await self.rag_service.retrieve_relevant_chunks(
                document_id=document_id,
                query=query,
                page_number=page_number,
                similarity_top_k=self.similarity_top_k,
                score_threshold=self.score_threshold,
            )
        except Exception:
            # Degrade gracefully: vẫn trả lời theo kiến thức chung, không bịa số trang.
            logger.exception("RAG retrieval failed for document_id=%s", document_id)
            return []

    # ------------------------------------------------------------------- stream

    async def stream_reply(
        self, session: ChatSession, request: ChatRequest
    ) -> AsyncIterator[str]:
        guard = analyze_query(request.content)
        history = await self.repository.list_recent_messages(
            session.id, limit=HISTORY_LIMIT
        )
        prev_tier = self.previous_tier(history)

        await self.repository.add_message(
            session_id=session.id,
            sender=SENDER_USER,
            content=request.content,
            socratic_tier=0,
            token_count=_estimate_tokens(request.content),
        )

        guardrail_meta = {
            "homework_detected": guard.is_homework or guard.is_exam_structure,
            "jailbreak_detected": guard.is_jailbreak,
        }

        # --- Toggle OFF + homework/jailbreak: từ chối tức thì, 0 LLM token -------
        if not request.socratic_enabled and guard.should_block_direct_answer:
            refusal = (
                JAILBREAK_REFUSAL_MESSAGE
                if guard.is_jailbreak and not guard.is_homework
                else HOMEWORK_REFUSAL_MESSAGE
            )
            yield _sse(
                "meta",
                {
                    "session_id": str(session.id),
                    "mode": "refusal",
                    "socratic_tier": 0,
                    "previous_tier": prev_tier,
                    **guardrail_meta,
                },
            )
            yield _sse("token", {"text": refusal})
            saved = await self.repository.add_message(
                session_id=session.id,
                sender=SENDER_ASSISTANT,
                content=refusal,
                socratic_tier=0,
                token_count=0,
            )
            yield _sse(
                "done",
                {"message_id": str(saved.id), "socratic_tier": 0, "solved": False},
            )
            return

        # --- Xác định chế độ & tầng ----------------------------------------------
        if request.socratic_enabled:
            mode: ChatMode = "socratic"
            tier, is_new_question = self.decide_tier(request, guard, prev_tier)
        else:
            mode = "normal"
            tier, is_new_question = 0, False

        retrieval_query = self.build_retrieval_query(
            request.content,
            history,
            include_previous=(mode == "socratic" and not is_new_question),
        )
        chunks = await self._retrieve(
            str(session.document_id), retrieval_query, request.page_number
        )

        system_prompt = compose_system_prompt(
            socratic_tier=tier,
            chunks=chunks,
            jailbreak_detected=guard.is_jailbreak,
        )

        yield _sse(
            "meta",
            {
                "session_id": str(session.id),
                "mode": mode,
                "socratic_tier": tier,
                "previous_tier": prev_tier,
                "is_new_question": is_new_question,
                **guardrail_meta,
            },
        )
        yield _sse(
            "citations",
            {
                "chunks": [
                    {
                        "chunk_id": c.chunk_id,
                        "page_number": c.page_number,
                        "score": c.score,
                        "citation_tag": c.citation_tag,
                    }
                    for c in chunks
                ]
            },
        )

        # --- Gemini streaming ------------------------------------------------------
        marker_filter = MarkerStreamFilter(SOLVED_MARKER)
        parts: list[str] = []
        try:
            async for piece in self.llm_client.stream(
                system_prompt=system_prompt,
                history=self.to_chat_turns(history),
                user_message=request.content,
            ):
                emitted = marker_filter.feed(piece)
                if emitted:
                    parts.append(emitted)
                    yield _sse("token", {"text": emitted})
            tail = marker_filter.flush()
            if tail:
                parts.append(tail)
                yield _sse("token", {"text": tail})
        except Exception:
            logger.exception("LLM streaming failed for session_id=%s", session.id)
            yield _sse(
                "error",
                {
                    "message": "Gia sư AI đang tạm thời gián đoạn kết nối. "
                    "Bạn vui lòng gửi lại câu hỏi sau ít giây nhé!"
                },
            )
            return

        answer = "".join(parts).strip()
        solved = mode == "socratic" and marker_filter.found
        next_tier = 0 if solved else tier
        cited = [
            {
                "chunk_id": c.chunk_id,
                "page_number": c.page_number,
                "score": c.score,
                "citation_tag": c.citation_tag,
            }
            for c in chunks
            if c.citation_tag in answer
        ]

        saved = await self.repository.add_message(
            session_id=session.id,
            sender=SENDER_ASSISTANT,
            content=answer,
            socratic_tier=next_tier,
            citations=cited,
            token_count=_estimate_tokens(answer),
        )
        yield _sse(
            "done",
            {
                "message_id": str(saved.id),
                "socratic_tier": next_tier,
                "solved": solved,
                "citations": cited,
            },
        )


socratic_chat_service = SocraticChatService(
    rag_service=chat_rag_service,
    llm_client=gemini_chat_client,
    repository=chat_repository,
)
