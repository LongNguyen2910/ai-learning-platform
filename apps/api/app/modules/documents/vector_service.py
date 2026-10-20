import logging
from pathlib import Path
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

logger = logging.getLogger(__name__)


class DocumentVectorService:
    """Manages Qdrant vector store indexing and retrieval for document pages."""

    def __init__(
        self,
        qdrant_client: QdrantClient | None = None,
        embed_model: BaseEmbedding | None = None,
        collection_name: str | None = None,
        vector_size: int = 3072,
        chunk_size: int = 768,
        chunk_overlap: int = 100,
    ) -> None:
        self._client = qdrant_client
        self._embed_model = embed_model
        self.collection_name = collection_name or settings.QDRANT_COLLECTION_NAME
        self.vector_size = vector_size
        self.splitter = SentenceSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    def get_client(self) -> QdrantClient:
        """Returns or lazily creates a QdrantClient."""
        if self._client is None:
            self._client = QdrantClient(url=settings.QDRANT_URL)
        return self._client

    def get_embed_model(self) -> BaseEmbedding:
        """Returns or lazily initializes the embedding model."""
        if self._embed_model is None:
            model_name = settings.EMBEDDING_MODEL
            self._embed_model = GoogleGenAIEmbedding(
                model_name=model_name,
                api_key=settings.GEMINI_API_KEY,
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
        need_create = True

        if client.collection_exists(self.collection_name):
            try:
                info = client.get_collection(self.collection_name)
                vectors_config = info.config.params.vectors
                current_size = None
                if isinstance(vectors_config, models.VectorParams):
                    current_size = vectors_config.size
                elif isinstance(vectors_config, dict) and "" in vectors_config:
                    current_size = vectors_config[""].size

                if current_size == self.vector_size:
                    need_create = False
                else:
                    logger.warning(
                        "Collection '%s' vector dimension mismatch (current: %s, target: %d). Recreating...",
                        self.collection_name,
                        current_size,
                        self.vector_size,
                    )
                    client.delete_collection(self.collection_name)
            except Exception as exc:
                logger.warning(
                    "Could not inspect existing collection '%s': %s",
                    self.collection_name,
                    exc,
                )

        if need_create:
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

        # Ensure payload indexes on doc_id and page_number for fast filtering
        self._create_payload_index_safe(
            field_name="doc_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        self._create_payload_index_safe(
            field_name="page_number",
            field_schema=models.PayloadSchemaType.INTEGER,
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
            if not content or content.startswith("<!-- Trang") and "để trống" in content:
                continue

            doc = Document(
                text=content,
                doc_id=document_id,
                metadata={
                    "page_number": page_meta.page_number,
                    "has_formula": page_meta.has_formula,
                    "has_image": page_meta.has_image,
                },
            )

            page_nodes = self.splitter.get_nodes_from_documents([doc])
            for node in page_nodes:
                node.metadata["doc_id"] = document_id
                node.metadata["chunk_index"] = global_chunk_idx
                # Maintain source relationship
                node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(
                    node_id=document_id
                )
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
        index.insert_nodes(all_nodes)

        logger.info(
            "Successfully indexed %d chunks for doc_id=%s",
            len(all_nodes),
            document_id,
        )
        return len(all_nodes)

    def get_retriever(
        self,
        document_id: str,
        page_number: int | None = None,
        similarity_top_k: int = 5,
        **kwargs: Any,
    ) -> VectorIndexRetriever:
        """Constructs a LlamaIndex VectorIndexRetriever filtered by doc_id and optional page_number."""
        filters_list = [MetadataFilter(key="doc_id", value=document_id)]
        if page_number is not None:
            filters_list.append(MetadataFilter(key="page_number", value=page_number))

        vector_store = self.get_vector_store()
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=self.get_embed_model(),
        )

        return index.as_retriever(
            similarity_top_k=similarity_top_k,
            filters=MetadataFilters(filters=filters_list),
            **kwargs,
        )


document_vector_service = DocumentVectorService()
