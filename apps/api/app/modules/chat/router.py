import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.chat.llm_client import ChatLLMClient, gemini_chat_client
from app.modules.chat.models import ChatSession
from app.modules.chat.repository import ChatRepository, chat_repository
from app.modules.chat.schemas import (
    ChatMessageResponse,
    ChatRequest,
    ChatSessionCreateRequest,
    ChatSessionResponse,
    RAGChunkSearchRequest,
    RAGChunkSearchResponse,
)
from app.modules.chat.service import (
    ChatRAGService,
    SocraticChatService,
    chat_rag_service,
)
from app.modules.documents.models import Document
from app.modules.documents.service import ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat RAG"])


def get_chat_rag_service() -> ChatRAGService:
    return chat_rag_service


def get_chat_repository() -> ChatRepository:
    return chat_repository


def get_chat_llm_client() -> ChatLLMClient:
    return gemini_chat_client


def get_socratic_chat_service(
    rag_service: Annotated[ChatRAGService, Depends(get_chat_rag_service)],
    llm_client: Annotated[ChatLLMClient, Depends(get_chat_llm_client)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> SocraticChatService:
    return SocraticChatService(
        rag_service=rag_service, llm_client=llm_client, repository=repository
    )


@router.post(
    "/documents/{document_id}/retrieval",
    response_model=RAGChunkSearchResponse,
    summary="Retrieve relevant chunks for a document",
)
async def retrieve_document_chunks(
    document_id: str,
    payload: RAGChunkSearchRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    rag_service: Annotated[ChatRAGService, Depends(get_chat_rag_service)] = None,
) -> RAGChunkSearchResponse:
    """Truy xuất các đoạn văn bản (chunks) liên quan nhất từ Vector Database Qdrant

    theo ngữ nghĩa câu hỏi và bộ lọc metadata.
    """
    # 1. Tra cứu document từ PostgreSQL nếu có DB session
    doc: Document | None = None
    if db is not None:
        try:
            doc_uuid = uuid.UUID(document_id)
            stmt = select(Document).where(Document.id == doc_uuid)
            doc = await db.scalar(stmt)
        except (ValueError, TypeError):
            pass
        except Exception as exc:
            logger.debug(
                "Database lookup for document %s failed, falling back to metadata storage: %s",
                document_id,
                exc,
            )

    # 2. Tra cứu metadata lưu trữ trên filesystem
    metadata = ingestion_service.load_metadata(document_id)

    # Nếu không tìm thấy ở cả PostgreSQL và Metadata file
    if doc is None and metadata is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    # 3. Kiểm tra phân quyền truy cập (Auth & Ownership)
    has_permission = False

    if doc is not None:
        if str(doc.user_id) == str(current_user.id) or bool(getattr(doc, "is_public", False)):
            has_permission = True
    elif metadata is not None and (
        metadata.user_id is None or str(metadata.user_id) == str(current_user.id)
    ):
        has_permission = True

    if not has_permission:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this document.",
        )

    # 4. Kiểm tra trạng thái tài liệu: phải ở trạng thái "ready"
    effective_status = metadata.status if metadata else doc.status
    if effective_status != "ready":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is not ready for retrieval (status: {effective_status}).",
        )

    # 5. Thực hiện truy xuất ngữ nghĩa từ Qdrant qua LlamaIndex
    active_service = rag_service or chat_rag_service
    try:
        chunks = await active_service.retrieve_relevant_chunks(
            document_id=document_id,
            query=payload.query,
            page_number=payload.page_number,
            similarity_top_k=payload.similarity_top_k,
            score_threshold=payload.score_threshold,
        )
    except Exception as exc:
        logger.exception(
            "Vector retrieval failed for document_id=%s, query='%s'",
            document_id,
            payload.query,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dịch vụ vector search tạm thời gián đoạn.",
        ) from exc

    return RAGChunkSearchResponse(
        document_id=document_id,
        query=payload.query,
        total_retrieved=len(chunks),
        chunks=chunks,
    )


# ============================================================================
# Chat sessions & Socratic SSE streaming
# ============================================================================


async def _get_owned_session(
    session_id: uuid.UUID, current_user: User, repository: ChatRepository
) -> ChatSession:
    session = await repository.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat session '{session_id}' not found.",
        )
    if str(session.user_id) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this chat session.",
        )
    return session


@router.get(
    "/sessions",
    response_model=list[ChatSessionResponse],
    summary="List chat sessions for the current user (optionally filtered by document)",
)
async def list_chat_sessions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
    document_id: Annotated[uuid.UUID | None, Query(description="Filter by document UUID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ChatSessionResponse]:
    sessions = await repository.list_sessions(
        user_id=current_user.id, document_id=document_id, limit=limit
    )
    return [ChatSessionResponse.model_validate(s) for s in sessions]


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a chat session bound to a document",
)
async def create_chat_session(
    payload: ChatSessionCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> ChatSessionResponse:
    doc = await repository.get_document(payload.document_id)
    if doc is None:
        meta = ingestion_service.load_metadata(str(payload.document_id))
        if (
            meta is not None
            and hasattr(repository, "ensure_document_from_metadata")
            and (meta.user_id is None or str(meta.user_id) == str(current_user.id))
        ):
            doc = await repository.ensure_document_from_metadata(
                document_id=payload.document_id,
                user_id=current_user.id,
                meta=meta,
            )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{payload.document_id}' not found.",
        )
    if str(doc.user_id) != str(current_user.id) and not bool(
        getattr(doc, "is_public", False)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this document.",
        )

    session = await repository.create_session(
        user_id=current_user.id, document_id=payload.document_id, title=payload.title
    )
    return ChatSessionResponse.model_validate(session)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a chat session and all its messages",
)
async def delete_chat_session(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
) -> None:
    await _get_owned_session(session_id, current_user, repository)
    await repository.delete_session(session_id)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
    summary="List recent messages of a chat session",
)
async def list_chat_messages(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ChatMessageResponse]:
    await _get_owned_session(session_id, current_user, repository)
    messages = await repository.list_recent_messages(session_id, limit=limit)
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.post(
    "/sessions/{session_id}/messages/stream",
    summary="Send a message and stream the AI tutor reply (SSE)",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {}},
            "description": "SSE events: meta, citations, token, done, error",
        }
    },
)
async def stream_chat_message(
    session_id: uuid.UUID,
    payload: ChatRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    repository: Annotated[ChatRepository, Depends(get_chat_repository)],
    chat_service: Annotated[SocraticChatService, Depends(get_socratic_chat_service)],
) -> StreamingResponse:
    session = await _get_owned_session(session_id, current_user, repository)

    return StreamingResponse(
        chat_service.stream_reply(session, payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
