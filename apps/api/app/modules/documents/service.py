"""Document Ingestion Service orchestrating PDF preprocessing, OCR, and vector indexing."""

import asyncio
import logging
from pathlib import Path
import re
import uuid

import pymupdf
from sqlalchemy import delete

from app.core.config import settings
from app.core.database import async_session_maker
from app.modules.documents.errors import format_user_friendly_error
from app.modules.documents.hybrid_router import (
    HybridPageRouter,
    PageRoute,
)
from app.modules.documents.models import Document
from app.modules.documents.renderer import PDFPageRenderer
from app.modules.documents.schemas import (
    DocumentContentResponse,
    DocumentMetadata,
    DocumentStatusResponse,
    ParsedPageMetadata,
)
from app.modules.documents.storage import DocumentStorage, document_storage
from app.modules.documents.vector_service import (
    DocumentVectorService,
    document_vector_service,
)
from app.modules.documents.vision_parser import (
    GeminiVisionParser,
    is_retryable_exception,
)

logger = logging.getLogger(__name__)


async def _update_db_document_status(
    document_id: str, status: str, error_message: str | None = None
) -> None:
    """Updates Document status in Postgres asynchronously with an independent session."""
    try:
        doc_uuid = uuid.UUID(document_id)
        from sqlalchemy import update

        async with async_session_maker() as session:
            stmt = (
                update(Document)
                .where(Document.id == doc_uuid)
                .values(status=status, error_message=error_message)
            )
            await session.execute(stmt)
            await session.commit()
    except Exception as exc:
        logger.debug("DB status update skipped or failed for %s: %s", document_id, exc)


class IngestionService:
    """Orchestrates PDF Ingestion Worker pipeline: Preprocessing, Vision OCR, and Qdrant Indexing."""

    def __init__(
        self,
        renderer: PDFPageRenderer | None = None,
        vision_parser: GeminiVisionParser | None = None,
        vector_service: DocumentVectorService | None = None,
        parsed_base_dir: str | Path | None = None,
        router: HybridPageRouter | None = None,
        storage: DocumentStorage | None = None,
    ):
        self.renderer = renderer or PDFPageRenderer()
        self.vision_parser = vision_parser or GeminiVisionParser()
        self.vector_service = vector_service or document_vector_service
        self.router = router or HybridPageRouter()
        self.storage = storage or (
            DocumentStorage(parsed_base_dir=parsed_base_dir)
            if parsed_base_dir
            else document_storage
        )
        self._active_tasks: set[str] = set()

    # --- In-memory Task Tracking ---

    def mark_task_active(self, document_id: str) -> None:
        """Marks a document as currently being processed in memory."""
        self._active_tasks.add(document_id)

    def mark_task_inactive(self, document_id: str) -> None:
        """Removes a document from active in-memory processing tracking."""
        self._active_tasks.discard(document_id)

    def is_task_active(self, document_id: str) -> bool:
        """Checks if a document task is actively running in the current server process."""
        return document_id in self._active_tasks

    # --- Storage Delegation (Maintains 100% Backward Compatibility) ---

    @property
    def parsed_base_dir(self) -> Path:
        return self.storage.parsed_base_dir

    def get_document_dir(self, document_id: str, create: bool = False) -> Path:
        return self.storage.get_document_dir(document_id, create=create)

    def get_metadata_path(self, document_id: str) -> Path:
        return self.storage.get_metadata_path(document_id)

    def get_full_doc_path(self, document_id: str) -> Path:
        return self.storage.get_full_doc_path(document_id)

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        self.storage.save_metadata(metadata)

    def load_metadata(self, document_id: str) -> DocumentMetadata | None:
        return self.storage.load_metadata(document_id)

    def count_parsed_pages(
        self, document_id: str, metadata: DocumentMetadata | None = None
    ) -> int:
        return self.storage.count_parsed_pages(document_id, metadata=metadata)

    def get_document_status(self, document_id: str) -> DocumentStatusResponse | None:
        return self.storage.get_document_status(document_id)

    def get_document_content(
        self, document_id: str, page_number: int | None = None
    ) -> DocumentContentResponse | None:
        return self.storage.get_document_content(document_id, page_number=page_number)

    def get_document_pdf_path(self, document_id: str) -> Path | None:
        return self.storage.get_document_pdf_path(document_id)

    def list_documents(
        self, user_id: str | None = None
    ) -> list[DocumentStatusResponse]:
        return self.storage.list_documents(user_id=user_id)

    # --- Page & Batch Processing ---

    async def _process_single_page(
        self,
        pdf_path: Path,
        page_num: int,
        doc_pages_dir: Path,
        force: bool = False,
    ) -> tuple[int, str, ParsedPageMetadata]:
        """Renders and parses a single page, saving its markdown file."""
        page_file = doc_pages_dir / f"page_{page_num}.md"

        if not force and page_file.is_file():
            content = page_file.read_text(encoding="utf-8")
            if content.strip():
                logger.info("Page %d already parsed, reusing cached markdown", page_num)
                has_formula = "$$" in content or bool(re.search(r"(?<!\\)\$[^$]+\$", content))
                has_image = "[Hình vẽ trang" in content or "![" in content
                meta = ParsedPageMetadata(
                    page_number=page_num,
                    has_formula=has_formula,
                    has_image=has_image,
                    char_count=len(content),
                    file_path=str(page_file),
                )
                return page_num, content, meta
            else:
                page_file.unlink(missing_ok=True)

        # Fast-path: Check if page is empty
        if self.renderer.is_page_empty(pdf_path, page_num):
            logger.info("Page %d is empty, skipping Gemini call", page_num)
            content = f"<!-- Trang {page_num} để trống -->"
            with open(page_file, "w", encoding="utf-8") as f:
                f.write(content)
            meta = ParsedPageMetadata(
                page_number=page_num,
                has_formula=False,
                has_image=False,
                char_count=0,
                file_path=str(page_file),
            )
            return page_num, content, meta

        # Render page to PNG in RAM and parse with Gemini Vision
        png_bytes = self.renderer.render_page_to_png_bytes(pdf_path, page_num)
        content, meta = await self.vision_parser.parse_page_image(png_bytes, page_num)

        with open(page_file, "w", encoding="utf-8") as f:
            f.write(content)

        meta.file_path = str(page_file)
        return page_num, content, meta

    async def _process_page_batch(
        self,
        pdf_path: Path,
        batch_page_nums: list[int],
        doc_pages_dir: Path,
    ) -> list[tuple[int, str, ParsedPageMetadata]]:
        """Renders and parses a batch of pages together using Gemini Vision batching."""
        pages_to_parse = [
            (page_num, self.renderer.render_page_to_png_bytes(pdf_path, page_num))
            for page_num in batch_page_nums
        ]

        batch_results: list[tuple[int, str, ParsedPageMetadata]] = []

        if hasattr(self.vision_parser, "parse_page_images_batch") and callable(
            self.vision_parser.parse_page_images_batch
        ):
            try:
                coro = self.vision_parser.parse_page_images_batch(pages_to_parse)
                if asyncio.iscoroutine(coro):
                    parsed_dict = await coro
                    if isinstance(parsed_dict, dict) and all(
                        p in parsed_dict for p in batch_page_nums
                    ):
                        for page_num in batch_page_nums:
                            content, meta = parsed_dict[page_num]
                            page_file = doc_pages_dir / f"page_{page_num}.md"
                            with open(page_file, "w", encoding="utf-8") as f:
                                f.write(content)
                            meta.file_path = str(page_file)
                            batch_results.append((page_num, content, meta))
                        return batch_results
            except Exception as e:
                err_s = str(e).lower()
                if not is_retryable_exception(e) or any(k in err_s for k in ("quota", "429")):
                    raise
                logger.warning(
                    "Batch parser encountered error: %s. Falling back to single page parsing...",
                    e,
                )

        # Fallback to single page processing
        for page_num in batch_page_nums:
            res = await self._process_single_page(pdf_path, page_num, doc_pages_dir)
            batch_results.append(res)

        return batch_results

    # --- Main Pipeline Orchestrator ---

    async def run_ingestion_pipeline(
        self,
        document_id: str,
        pdf_path: str | Path,
        title: str,
        force: bool = False,
        user_id: str | None = None,
    ) -> DocumentMetadata:
        """Main Ingestion Worker execution method."""
        file_path = Path(pdf_path)
        doc_dir = self.get_document_dir(document_id, create=True)
        pages_dir = doc_dir / "pages"

        file_size_kb = int(file_path.stat().st_size / 1024) if file_path.exists() else 0
        total_pages = self.renderer.get_page_count(file_path)

        existing_meta = self.load_metadata(document_id)
        if existing_meta:
            metadata = existing_meta
            metadata.title = title
            metadata.file_path = str(file_path)
            metadata.file_size_kb = file_size_kb
            metadata.total_pages = total_pages
            metadata.status = "parsing"
            metadata.error_message = None
            if user_id:
                metadata.user_id = str(user_id)
        else:
            metadata = DocumentMetadata(
                document_id=document_id,
                user_id=str(user_id) if user_id else None,
                title=title,
                file_path=str(file_path),
                file_size_kb=file_size_kb,
                total_pages=total_pages,
                status="parsing",
            )
        self.save_metadata(metadata)
        await _update_db_document_status(document_id, "parsing")
        logger.info(
            "Starting ingestion for document '%s' (ID: %s, User: %s, Pages: %d)",
            title,
            document_id,
            user_id,
            total_pages,
        )

        self.mark_task_active(document_id)
        try:
            # Stage 1: parse content using AI & Smart Hybrid Routing
            results: list[tuple[int, str, ParsedPageMetadata]] = []
            pages_to_batch: list[int] = []

            if force and pages_dir.is_dir():
                for old_p in pages_dir.glob("page_*.md"):
                    old_p.unlink(missing_ok=True)

            pdf_doc = None
            try:
                pdf_doc = pymupdf.open(str(file_path))
            except Exception as e:
                logger.debug("Could not open %s with pymupdf directly: %s", file_path, e)

            try:
                for page_num in range(1, total_pages + 1):
                    page_file = pages_dir / f"page_{page_num}.md"
                    if not force and page_file.is_file():
                        content = page_file.read_text(encoding="utf-8")
                        if content.strip():
                            logger.info("Page %d already parsed, reusing cached markdown", page_num)
                            has_formula = "$$" in content or bool(re.search(r"(?<!\\)\$[^$]+\$", content))
                            has_image = "[Hình vẽ trang" in content or "![" in content
                            meta = ParsedPageMetadata(
                                page_number=page_num,
                                has_formula=has_formula,
                                has_image=has_image,
                                char_count=len(content),
                                file_path=str(page_file),
                            )
                            results.append((page_num, content, meta))
                            continue
                        else:
                            page_file.unlink(missing_ok=True)

                    # Smart Hybrid Routing: Text-First, Vision-Fallback
                    if getattr(settings, "HYBRID_ROUTING_ENABLED", True):
                        classification = self.router.classify_page(
                            file_path, page_num, pdf_doc=pdf_doc
                        )
                        if classification.route == PageRoute.EMPTY:
                            logger.info("Page %d is empty, skipping Vision API", page_num)
                            content = f"<!-- Trang {page_num} để trống -->"
                            with open(page_file, "w", encoding="utf-8") as f:
                                f.write(content)
                            meta = ParsedPageMetadata(
                                page_number=page_num,
                                has_formula=False,
                                has_image=False,
                                char_count=0,
                                file_path=str(page_file),
                            )
                            results.append((page_num, content, meta))
                            continue
                        elif (
                            classification.route == PageRoute.LOCAL_TEXT
                            and classification.extracted_markdown
                        ):
                            logger.info(
                                "Page %d routed to Local CPU text extraction (0 tokens, reason: %s)",
                                page_num,
                                classification.reason,
                            )
                            content = classification.extracted_markdown
                            with open(page_file, "w", encoding="utf-8") as f:
                                f.write(content)
                            has_formula = "$$" in content or bool(re.search(r"(?<!\\)\$[^$]+\$", content))
                            has_image = "[Hình vẽ trang" in content or "![" in content
                            meta = ParsedPageMetadata(
                                page_number=page_num,
                                has_formula=has_formula,
                                has_image=has_image,
                                char_count=len(content),
                                file_path=str(page_file),
                            )
                            results.append((page_num, content, meta))
                            continue
                        else:
                            logger.info(
                                "Page %d requires Gemini Vision OCR (reason: %s)",
                                page_num,
                                classification.reason,
                            )
                            pages_to_batch.append(page_num)
                    else:
                        if self.renderer.is_page_empty(file_path, page_num):
                            logger.info("Page %d is empty, skipping Gemini call", page_num)
                            content = f"<!-- Trang {page_num} để trống -->"
                            with open(page_file, "w", encoding="utf-8") as f:
                                f.write(content)
                            meta = ParsedPageMetadata(
                                page_number=page_num,
                                has_formula=False,
                                has_image=False,
                                char_count=0,
                                file_path=str(page_file),
                            )
                            results.append((page_num, content, meta))
                            continue

                        pages_to_batch.append(page_num)
            finally:
                if pdf_doc is not None:
                    try:
                        pdf_doc.close()
                    except Exception:
                        pass

            # Dynamic Vision Batching (5 pages/request)
            batch_size = max(1, getattr(settings, "INGESTION_BATCH_SIZE", 5))
            batches = [
                pages_to_batch[i : i + batch_size]
                for i in range(0, len(pages_to_batch), batch_size)
            ]

            if batches:
                try:
                    async with asyncio.TaskGroup() as tg:
                        batch_tasks = [
                            tg.create_task(
                                self._process_page_batch(file_path, batch, pages_dir)
                            )
                            for batch in batches
                        ]
                    for t in batch_tasks:
                        results.extend(t.result())
                except* Exception as eg:
                    first_exc = eg.exceptions[0]
                    while hasattr(first_exc, "exceptions") and first_exc.exceptions:
                        first_exc = first_exc.exceptions[0]
                    raise first_exc

            # Sort results by page_number deterministically
            results.sort(key=lambda r: r[0])

            parsed_pages_meta: list[ParsedPageMetadata] = []
            combined_blocks: list[str] = []

            for page_num, content, page_meta in results:
                parsed_pages_meta.append(page_meta)
                combined_blocks.append(
                    f"<!-- PAGE_BREAK: {page_num} -->\n\n{content}\n"
                )

            # Stage 2: Store markdown content
            full_markdown = "\n".join(combined_blocks)
            full_doc_path = self.get_full_doc_path(document_id)
            with open(full_doc_path, "w", encoding="utf-8") as f:
                f.write(full_markdown)

            # Stage 3: Index Vector into Qdrant
            metadata.status = "indexing"
            metadata.pages = parsed_pages_meta
            metadata.error_message = None
            self.save_metadata(metadata)
            await _update_db_document_status(document_id, "indexing")
            logger.info("Starting vector indexing for document ID: %s", document_id)

            self.vector_service.index_document_pages(
                document_id,
                parsed_pages_meta,
                user_id=user_id or metadata.user_id,
                doc_title=title or metadata.title,
            )

            metadata.status = "ready"
            self.save_metadata(metadata)
            await _update_db_document_status(document_id, "ready")
            logger.info("Ingestion & indexing completed for document ID: %s", document_id)
            return metadata

        except Exception as exc:
            logger.exception(
                "Ingestion failed for document ID: %s",
                document_id,
            )
            metadata.status = "failed"
            metadata.error_message = format_user_friendly_error(exc)
            self.save_metadata(metadata)
            await _update_db_document_status(document_id, "failed", metadata.error_message)
            raise
        finally:
            self.mark_task_inactive(document_id)

    async def recover_interrupted_documents(self) -> list[str]:
        """Scans for documents interrupted during uploading/parsing/indexing and recovers them."""
        if not getattr(settings, "AUTO_RESUME_INGESTION_ON_STARTUP", True):
            return []

        if not self.parsed_base_dir.exists():
            return []

        recovered_ids: list[str] = []
        for entry in self.parsed_base_dir.iterdir():
            if not entry.is_dir():
                continue
            document_id = entry.name
            try:
                metadata = self.load_metadata(document_id)
            except Exception as e:
                logger.warning("Could not load metadata for %s: %s", document_id, e)
                continue

            if not metadata:
                continue

            if metadata.status in ("parsing", "indexing", "uploading"):
                if self.is_task_active(document_id):
                    continue

                pdf_path = self.get_document_pdf_path(document_id)
                if not pdf_path or not pdf_path.is_file():
                    logger.error(
                        "Cannot recover %s: original PDF file missing at %s",
                        document_id,
                        pdf_path,
                    )
                    metadata.status = "failed"
                    metadata.error_message = (
                        "Không thể khôi phục tài liệu: không tìm thấy file PDF gốc trên hệ thống."
                    )
                    self.save_metadata(metadata)
                    await _update_db_document_status(document_id, "failed", metadata.error_message)
                    continue

                logger.info(
                    "Auto-recovering interrupted document %s (status: %s, file: %s)",
                    document_id,
                    metadata.status,
                    pdf_path,
                )
                recovered_ids.append(document_id)
                self.mark_task_active(document_id)
                try:
                    asyncio.create_task(
                        self.run_ingestion_pipeline(
                            document_id=document_id,
                            pdf_path=pdf_path,
                            title=metadata.title,
                            force=False,
                            user_id=metadata.user_id,
                        )
                    )
                except Exception as exc:
                    logger.error("Failed to spawn recovery task for %s: %s", document_id, exc)
                    metadata.status = "failed"
                    metadata.error_message = f"Lỗi khôi phục tự động: {exc}"
                    self.save_metadata(metadata)

        return recovered_ids

    def delete_document(self, document_id: str) -> bool:
        """Deletes all data associated with a document (files, DB record and vectors)."""
        self.mark_task_inactive(document_id)

        # 1. Delete physical files from disk
        deleted_files = self.storage.delete_document_files(document_id)
        if not deleted_files:
            return False

        # 2. Delete vectors from Qdrant
        try:
            self.vector_service.delete_document_vectors(document_id)
        except Exception as e:
            logger.warning("Failed to delete vectors for document %s: %s", document_id, e)

        # 3. Asynchronously clean up PostgreSQL record if present
        try:
            doc_uuid = uuid.UUID(document_id)

            async def _cleanup_db():
                async with async_session_maker() as session:
                    await session.execute(
                        delete(Document).where(Document.id == doc_uuid)
                    )
                    await session.commit()

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_cleanup_db())
            except RuntimeError:
                asyncio.run(_cleanup_db())
        except Exception as exc:
            logger.debug("Failed to trigger DB cleanup for document %s: %s", document_id, exc)

        logger.info("Deleted document %s and its associated files and vectors", document_id)
        return True


ingestion_service = IngestionService()
