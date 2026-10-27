import logging
from pathlib import Path
import time
from typing import Any

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.indices.vector_store import VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import (
    Document,
    NodeRelationship,
    RelatedNodeInfo,
    TextNode,
)
from llama_index.core.vector_stores.types import MetadataFilter, MetadataFilters
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from app.core.config import settings
from app.modules.documents.schemas import ParsedPageMetadata
from app.modules.documents.splitter import MarkdownStructureSplitter

logger = logging.getLogger(__name__)


class DocumentVectorService:
    """Manages Qdrant vector store indexing and retrieval for document pages."""

    def __init__(
        self,
        qdrant_client: QdrantClient | None = None,
        embed_model: BaseEmbedding | None = None,
        collection_name: str | None = None,
        vector_size: int | None = None,
        chunk_size: int = 768,
        chunk_overlap: int = 100,
    ) -> None:
        self._client = qdrant_client
        self._embed_model = embed_model
        self.collection_name = collection_name or settings.QDRANT_COLLECTION_NAME
        self.vector_size = vector_size or getattr(settings, "EMBEDDING_DIMENSION", 3072)
        self.structure_splitter = MarkdownStructureSplitter(
            target_chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.splitter = SentenceSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    def get_client(self) -> QdrantClient:
        """Returns or lazily creates a QdrantClient with timeout."""
        if self._client is None:
            self._client = QdrantClient(url=settings.QDRANT_URL, timeout=30.0)
        return self._client

    def get_embed_model(self) -> BaseEmbedding:
        """Returns or lazily initializes the embedding model."""
        if self._embed_model is None:
            model_name = settings.EMBEDDING_MODEL
            batch_size = max(1, getattr(settings, "EMBEDDING_BATCH_SIZE", 50))
            self._embed_model = GoogleGenAIEmbedding(
                model_name=model_name,
                api_key=settings.GEMINI_API_KEY,
                embed_batch_size=batch_size,
                retries=getattr(settings, "EMBEDDING_MAX_RETRIES", 4),
                retry_min_seconds=2.0,
                retry_max_seconds=30.0,
                retry_exponential_base=2.0,
            )
        return self._embed_model

    def get_vector_store(self) -> QdrantVectorStore:
        """Returns a QdrantVectorStore attached to the current client and collection."""
        return QdrantVectorStore(
            client=self.get_client(),
            collection_name=self.collection_name,
        )

    def ensure_collection_ready(self) -> None:
        """Ensures the Qdrant collection exists with proper vector size and payload indexes."""
        client = self.get_client()

        if client.collection_exists(self.collection_name):
            try:
                info = client.get_collection(self.collection_name)
                vectors_config = info.config.params.vectors
                current_size = None
                if isinstance(vectors_config, models.VectorParams):
                    current_size = vectors_config.size
                elif isinstance(vectors_config, dict) and "" in vectors_config:
                    current_size = vectors_config[""].size

                if current_size != self.vector_size:
                    raise ValueError(
                        f"Collection '{self.collection_name}' dimension mismatch: "
                        f"existing={current_size}, target={self.vector_size}. "
                        "Manual migration or distinct collection name required to prevent data loss."
                    )
            except Exception as exc:
                if isinstance(exc, ValueError):
                    raise
                logger.warning(
                    "Could not inspect existing collection '%s': %s",
                    self.collection_name,
                    exc,
                )
        else:
            logger.info(
                "Creating Qdrant collection '%s' (%d-dim, Cosine)",
                self.collection_name,
                self.vector_size,
            )
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

        # Ensure payload indexes on user_id, doc_id and page_number for fast filtering
        self._create_payload_index_safe(
            field_name="user_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self._create_payload_index_safe(
            field_name="doc_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self._create_payload_index_safe(
            field_name="page_number",
            field_schema=models.PayloadSchemaType.INTEGER,
        )
        self._create_payload_index_safe(
            field_name="section_heading",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    def _create_payload_index_safe(
        self, field_name: str, field_schema: models.PayloadSchemaType
    ) -> None:
        """Safely creates a payload index, ignoring existing index errors."""
        client = self.get_client()
        try:
            client.create_payload_index(
                collection_name=self.collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )
        except Exception as exc:
            logger.debug(
                "Payload index on '%s' may already exist or cannot be indexed: %s",
                field_name,
                exc,
            )

    def delete_document_vectors(self, document_id: str) -> None:
        """Deletes all vector points associated with a document_id from the collection."""
        client = self.get_client()
        try:
            if not client.collection_exists(self.collection_name):
                return

            client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="doc_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
            )
            logger.info(
                "Deleted all vectors for doc_id=%s from collection '%s'",
                document_id,
                self.collection_name,
            )
        except Exception as exc:
            logger.warning(
                "Failed to delete vectors for doc_id=%s: %s", document_id, exc
            )

    def index_document_pages(
        self,
        document_id: str,
        pages_meta: list[ParsedPageMetadata],
        user_id: str | None = None,
        doc_title: str | None = None,
    ) -> int:
        """Chunks each page markdown file and indexes into Qdrant with metadata.

        Returns total number of chunks indexed.
        """
        self.ensure_collection_ready()
        # Ensure idempotency: remove previous points if re-indexing
        self.delete_document_vectors(document_id)

        all_nodes: list[TextNode] = []
        global_chunk_idx = 0

        for page_meta in pages_meta:
            page_path = Path(page_meta.file_path)
            if not page_path.is_file():
                continue

            content = page_path.read_text(encoding="utf-8").strip()
            # Skip empty pages or placeholder marker
            if not content or (
                content.startswith("<!-- Trang") and "để trống" in content
            ):
                continue

            page_nodes = self.structure_splitter.split_page_to_nodes(
                content=content,
                page_number=page_meta.page_number,
                doc_id=document_id,
                user_id=user_id,
                doc_title=doc_title,
                start_chunk_idx=global_chunk_idx,
            )
            for node in page_nodes:
                all_nodes.append(node)
                global_chunk_idx += 1

        if not all_nodes:
            logger.info("No text content found to index for doc_id=%s", document_id)
            return 0

        logger.info(
            "Indexing %d chunks for doc_id=%s into '%s'",
            len(all_nodes),
            document_id,
            self.collection_name,
        )

        vector_store = self.get_vector_store()
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=self.get_embed_model(),
        )

        # Batch indexing with adaptive rate-limiting and 429 backoff
        batch_size = max(1, getattr(settings, "EMBEDDING_BATCH_SIZE", 50))
        throttle_seconds = getattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 1.0)
        max_retries = getattr(settings, "EMBEDDING_MAX_RETRIES", 4)
        total_batches = (len(all_nodes) + batch_size - 1) // batch_size

        for i in range(0, len(all_nodes), batch_size):
            batch_nodes = all_nodes[i : i + batch_size]
            batch_idx = (i // batch_size) + 1

            attempt = 0
            while True:
                try:
                    logger.info(
                        "Indexing batch %d/%d (%d nodes) for doc_id=%s (attempt %d)",
                        batch_idx,
                        total_batches,
                        len(batch_nodes),
                        document_id,
                        attempt + 1,
                    )
                    index.insert_nodes(batch_nodes)
                    break
                except Exception as exc:
                    attempt += 1
                    err_msg = str(exc).lower()
                    is_rate_limit = any(
                        k in err_msg
                        for k in ("429", "quota", "resource_exhausted", "too many requests")
                    )
                    if attempt < max_retries and is_rate_limit:
                        backoff = (2 ** attempt) * 2.0  # 4s, 8s, 16s...
                        logger.warning(
                            "Embedding rate limit (429) hit on batch %d/%d for doc_id=%s. Backing off for %.1fs (attempt %d/%d)...",
                            batch_idx,
                            total_batches,
                            document_id,
                            backoff,
                            attempt,
                            max_retries,
                        )
                        time.sleep(backoff)
                    else:
                        logger.exception(
                            "Failed to index batch %d/%d for doc_id=%s: %s",
                            batch_idx,
                            total_batches,
                            document_id,
                            exc,
                        )
                        raise

            # Throttle between batches to stay safely within RPM limits
            if i + batch_size < len(all_nodes) and throttle_seconds > 0:
                time.sleep(throttle_seconds)

        logger.info(
            "Successfully indexed %d chunks for doc_id=%s",
            len(all_nodes),
            document_id,
        )
        return len(all_nodes)

    def get_retriever(
        self,
        document_id: str | None = None,
        user_id: str | None = None,
        page_number: int | None = None,
        similarity_top_k: int = 5,
        **kwargs: Any,
    ) -> VectorIndexRetriever:
        """Constructs a LlamaIndex VectorIndexRetriever filtered by user_id, doc_id and optional page_number."""
        filters_list: list[MetadataFilter] = []
        if user_id is not None:
            filters_list.append(MetadataFilter(key="user_id", value=str(user_id)))
        if document_id is not None:
            filters_list.append(MetadataFilter(key="doc_id", value=str(document_id)))
        if page_number is not None:
            filters_list.append(MetadataFilter(key="page_number", value=page_number))

        vector_store = self.get_vector_store()
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=self.get_embed_model(),
        )

        filters = MetadataFilters(filters=filters_list) if filters_list else None
        return index.as_retriever(
            similarity_top_k=similarity_top_k,
            filters=filters,
            **kwargs,
        )


document_vector_service = DocumentVectorService()
