import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.chat.schemas import (
    RAGChunkSearchRequest,
    RAGChunkSearchResponse,
)
from app.modules.chat.service import ChatRAGService, chat_rag_service
from app.modules.documents.models import Document
from app.modules.documents.service import ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat RAG"])


def get_chat_rag_service() -> ChatRAGService:
    return chat_rag_service


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
