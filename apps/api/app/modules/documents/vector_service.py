from collections import deque
import logging
from pathlib import Path
import re
import threading
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
from app.modules.documents.splitter import MarkdownStructureSplitter, estimate_tokens

logger = logging.getLogger(__name__)

_HARD_QUOTA_KEYWORDS = (
    "per day",
    "per_day",
    "per-day",
    "daily limit",
    "billing account",
)

_PER_MINUTE_KEYWORDS = (
    "per minute",
    "per_minute",
    "per-minute",
    "tokens per minute",
    "requests per minute",
)

_RATE_LIMIT_KEYWORDS = (
    "429",
    "quota",
    "resource_exhausted",
    "too many requests",
    "rate limit",
)

_RETRY_DELAY_RE = re.compile(
    r"(?:retry(?:\s+in|\s+after|delay['\":\s]+))\s*(\d+(?:\.\d+)?)\s*s",
    re.IGNORECASE,
)


class _SlidingWindowRateLimiter:
    """Thread-safe 60-second sliding-window rate limiter for embedding TPM and RPM."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._events: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._events and self._events[0][0] <= cutoff:
            self._events.popleft()

    def acquire(self, tokens: int, tpm_limit: int, rpm_limit: int) -> float:
        """Waits if needed so adding `tokens` stays within TPM/RPM limits, then records usage."""
        if tpm_limit <= 0 and rpm_limit <= 0:
            return 0.0

        total_waited = 0.0
        while True:
            wait_seconds = 0.0
            with self._lock:
                now = time.monotonic()
                self._prune(now)

                used_tokens = sum(t for _, t in self._events)
                used_requests = len(self._events)

                rpm_exceeded = rpm_limit > 0 and used_requests + 1 > rpm_limit
                tpm_exceeded = (
                    tpm_limit > 0
                    and used_tokens > 0
                    and used_tokens + tokens > tpm_limit
                )

                if not rpm_exceeded and not tpm_exceeded:
                    self._events.append((now, tokens))
                    return total_waited

                # Compute minimum wait until enough older entries expire from the 60s window
                if self._events:
                    if rpm_exceeded and not tpm_exceeded:
                        target_ts = self._events[0][0]
                    else:
                        freed = 0
                        target_ts = self._events[0][0]
                        excess_tokens = (used_tokens + tokens) - tpm_limit
                        for ts, tok in self._events:
                            freed += tok
                            target_ts = ts
                            if freed >= excess_tokens and (
                                not rpm_exceeded or used_requests >= rpm_limit
                            ):
                                break
                    wait_seconds = max(0.5, (target_ts + self.window_seconds) - now + 0.5)

            if wait_seconds > 0:
                logger.info(
                    "Embedding rate limiter throttling for %.1fs to stay within TPM/RPM quota (batch=%d tokens)",
                    wait_seconds,
                    tokens,
                )
                time.sleep(wait_seconds)
                total_waited += wait_seconds


def _classify_embedding_error(exc: Exception) -> tuple[bool, bool, float | None]:
    """Classifies an embedding exception as (is_rate_limit, is_hard_daily_quota, retry_after_seconds)."""
    while hasattr(exc, "exceptions") and exc.exceptions:
        exc = exc.exceptions[0]

    err_msg = str(exc)
    err_lower = err_msg.lower()

    match = _RETRY_DELAY_RE.search(err_msg)
    retry_after = float(match.group(1)) if match else None

    is_per_minute = any(k in err_lower for k in _PER_MINUTE_KEYWORDS)
    is_hard_daily = (
        not is_per_minute
        and retry_after is None
        and any(k in err_lower for k in _HARD_QUOTA_KEYWORDS)
    )
    if is_hard_daily:
        return True, True, None

    if is_per_minute or retry_after is not None or any(
        k in err_lower for k in _RATE_LIMIT_KEYWORDS
    ):
        return True, False, retry_after

    return False, False, None


def _estimate_embedding_tokens(text: str) -> int:
    """Conservative token estimate for multilingual Vietnamese + LaTeX embedding payloads."""
    return max(estimate_tokens(text), max(1, int(len(text) / 2.0)))


def _build_token_aware_batches(
    nodes: list[TextNode],
    max_batch_size: int,
    max_tokens_per_batch: int,
) -> list[tuple[list[TextNode], int]]:
    """Groups nodes into batches bounded by both node count and estimated token budget."""
    batches: list[tuple[list[TextNode], int]] = []
    current_batch: list[TextNode] = []
    current_tokens = 0

    for node in nodes:
        node_tokens = _estimate_embedding_tokens(node.get_content())
        would_exceed_count = len(current_batch) >= max_batch_size
        would_exceed_tokens = (
            max_tokens_per_batch > 0
            and current_batch
            and current_tokens + node_tokens > max_tokens_per_batch
        )
        if current_batch and (would_exceed_count or would_exceed_tokens):
            batches.append((current_batch, current_tokens))
            current_batch = []
            current_tokens = 0

        current_batch.append(node)
        current_tokens += node_tokens

    if current_batch:
        batches.append((current_batch, current_tokens))

    return batches


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
        self._rate_limiter = _SlidingWindowRateLimiter()

    def get_client(self) -> QdrantClient:
        """Returns or lazily creates a QdrantClient with timeout."""
        if self._client is None:
            self._client = QdrantClient(url=settings.QDRANT_URL, timeout=30.0)
        return self._client

    def get_embed_model(self) -> BaseEmbedding:
        """Returns or lazily initializes the embedding model."""
        if self._embed_model is None:
            model_name = settings.EMBEDDING_MODEL
            batch_size = max(1, getattr(settings, "EMBEDDING_BATCH_SIZE", 15))
            # Disable internal LlamaIndex retries so DocumentVectorService manages
            # TPM/RPM throttling, daily quota detection, and 60s window backoff uniformly.
            self._embed_model = GoogleGenAIEmbedding(
                model_name=model_name,
                api_key=settings.GEMINI_API_KEY,
                embed_batch_size=batch_size,
                retries=0,
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

    def _get_existing_point_hashes(self, document_id: str) -> dict[str, str | None]:
        """Returns {point_id: content_hash} for all vectors currently stored for document_id."""
        client = self.get_client()
        existing: dict[str, str | None] = {}
        try:
            if not client.collection_exists(self.collection_name):
                return existing

            offset = None
            doc_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=document_id),
                    )
                ]
            )
            while True:
                points, offset = client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=doc_filter,
                    limit=256,
                    offset=offset,
                    with_payload=["content_hash"],
                    with_vectors=False,
                )
                for pt in points:
                    payload = pt.payload or {}
                    existing[str(pt.id)] = payload.get("content_hash")
                if offset is None:
                    break
        except Exception as exc:
            logger.warning(
                "Could not inspect existing vectors for doc_id=%s (falling back to full re-index): %s",
                document_id,
                exc,
            )
            return {}
        return existing

    def _delete_point_ids(self, point_ids: list[str]) -> None:
        """Deletes specific stale vector point IDs from the collection."""
        if not point_ids:
            return
        client = self.get_client()
        try:
            client.delete(
                collection_name=self.collection_name,
                points_selector=models.PointIdsList(points=point_ids),
            )
        except Exception as exc:
            logger.warning("Failed to delete %d stale points: %s", len(point_ids), exc)

    def index_document_pages(
        self,
        document_id: str,
        pages_meta: list[ParsedPageMetadata],
        user_id: str | None = None,
        doc_title: str | None = None,
    ) -> int:
        """Chunks each page markdown file and indexes into Qdrant with metadata.

        Supports incremental/resumable indexing via content hashes and enforces
        token-aware batching + sliding-window TPM/RPM rate limiting.
        Returns total number of chunks in the document.
        """
        self.ensure_collection_ready()

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
            self.delete_document_vectors(document_id)
            logger.info("No text content found to index for doc_id=%s", document_id)
            return 0

        # Resume-safe idempotency: keep already-indexed chunks with matching content_hash
        existing_hashes = self._get_existing_point_hashes(document_id)
        target_ids = {node.id_ for node in all_nodes}
        stale_ids = [pid for pid in existing_hashes if pid not in target_ids]
        if stale_ids:
            self._delete_point_ids(stale_ids)

        nodes_to_index = [
            node
            for node in all_nodes
            if node.id_ not in existing_hashes
            or existing_hashes[node.id_] != node.metadata.get("content_hash")
        ]

        if not nodes_to_index:
            logger.info(
                "All %d chunks for doc_id=%s are already indexed and up-to-date.",
                len(all_nodes),
                document_id,
            )
            return len(all_nodes)

        if existing_hashes:
            logger.info(
                "Resuming indexing for doc_id=%s: %d/%d chunks remaining",
                document_id,
                len(nodes_to_index),
                len(all_nodes),
            )
        else:
            logger.info(
                "Indexing %d chunks for doc_id=%s into '%s'",
                len(nodes_to_index),
                document_id,
                self.collection_name,
            )

        vector_store = self.get_vector_store()
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store,
            embed_model=self.get_embed_model(),
        )

        # Token-aware batching + sliding-window TPM/RPM rate limiting + 429 backoff
        batch_size = max(1, getattr(settings, "EMBEDDING_BATCH_SIZE", 15))
        max_tokens_per_batch = max(
            0, getattr(settings, "EMBEDDING_MAX_TOKENS_PER_BATCH", 8000)
        )
        tpm_limit = max(0, getattr(settings, "EMBEDDING_TPM_LIMIT", 24000))
        rpm_limit = max(0, getattr(settings, "EMBEDDING_RPM_LIMIT", 80))
        throttle_seconds = max(
            0.0, getattr(settings, "EMBEDDING_BATCH_DELAY_SECONDS", 1.0)
        )
        max_retries = max(1, getattr(settings, "EMBEDDING_MAX_RETRIES", 6))

        batches = _build_token_aware_batches(
            nodes_to_index,
            max_batch_size=batch_size,
            max_tokens_per_batch=max_tokens_per_batch,
        )
        total_batches = len(batches)

        for batch_idx, (batch_nodes, batch_tokens) in enumerate(batches, start=1):
            attempt = 0
            while True:
                self._rate_limiter.acquire(
                    tokens=batch_tokens,
                    tpm_limit=tpm_limit,
                    rpm_limit=rpm_limit,
                )
                try:
                    logger.info(
                        "Indexing batch %d/%d (%d nodes, ~%d tokens) for doc_id=%s (attempt %d)",
                        batch_idx,
                        total_batches,
                        len(batch_nodes),
                        batch_tokens,
                        document_id,
                        attempt + 1,
                    )
                    index.insert_nodes(batch_nodes)
                    break
                except Exception as exc:
                    attempt += 1
                    is_rate_limit, is_hard_daily, retry_after = _classify_embedding_error(
                        exc
                    )
                    if is_hard_daily:
                        logger.error(
                            "Hard daily/billing embedding quota exhausted on batch %d/%d for doc_id=%s: %s",
                            batch_idx,
                            total_batches,
                            document_id,
                            exc,
                        )
                        raise

                    if attempt < max_retries and is_rate_limit:
                        # Exponential backoff capped at 65s so a 60s TPM window can fully reset
                        default_backoff = min(65.0, (2 ** attempt) * 5.0)
                        backoff = max(
                            default_backoff,
                            (retry_after + 1.0) if retry_after is not None else 0.0,
                        )
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

            # Throttle between batches to avoid burst spikes
            if batch_idx < total_batches and throttle_seconds > 0:
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
