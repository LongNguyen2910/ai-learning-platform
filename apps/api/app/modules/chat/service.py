import asyncio
import logging

from app.modules.chat.schemas import RetrievedChunkDTO
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
