import asyncio
import json
import logging
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.modules.documents.renderer import PDFPageRenderer
from app.modules.documents.schemas import (
    DocumentContentResponse,
    DocumentMetadata,
    DocumentStatusResponse,
    ParsedPageMetadata,
)
from app.modules.documents.vector_service import (
    DocumentVectorService,
    document_vector_service,
)
from app.modules.documents.vision_parser import GeminiVisionParser

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrates PDF Ingestion Worker pipeline."""

    def __init__(
        self,
        renderer: PDFPageRenderer | None = None,
        vision_parser: GeminiVisionParser | None = None,
        vector_service: DocumentVectorService | None = None,
        parsed_base_dir: str | None = None,
    ):
        self.renderer = renderer or PDFPageRenderer()
        self.vision_parser = vision_parser or GeminiVisionParser()
        self.vector_service = vector_service or document_vector_service
        self._parsed_base_dir = parsed_base_dir

    @property
    def parsed_base_dir(self) -> Path:
        base = Path(self._parsed_base_dir or settings.PARSED_DIR)
        base.mkdir(parents=True, exist_ok=True)
        return base

    def get_document_dir(self, document_id: str, create: bool = False) -> Path:
        doc_dir = self.parsed_base_dir / document_id
        if create:
            doc_dir.mkdir(parents=True, exist_ok=True)
            (doc_dir / "pages").mkdir(parents=True, exist_ok=True)
        return doc_dir

    def get_metadata_path(self, document_id: str) -> Path:
        return self.get_document_dir(document_id, create=False) / "metadata.json"

    def get_full_doc_path(self, document_id: str) -> Path:
        return self.get_document_dir(document_id, create=False) / "full_document.md"

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        self.get_document_dir(metadata.document_id, create=True)
        path = self.get_metadata_path(metadata.document_id)
        metadata.updated_at = datetime.now(UTC).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata.model_dump(), f, ensure_ascii=False, indent=2)

    def load_metadata(self, document_id: str) -> DocumentMetadata | None:
        path = self.get_metadata_path(document_id)
        if not path.is_file():
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return DocumentMetadata.model_validate(data)

    async def _process_single_page(
        self,
        pdf_path: Path,
        page_num: int,
        doc_pages_dir: Path,
        force: bool = False,
    ) -> tuple[int, str, ParsedPageMetadata]:
        """Renders and parses a single page, saving its markdown file."""
        page_file = doc_pages_dir / f"page_{page_num}.md"

        # Smart caching: check if page markdown is already parsed and non-empty
        if not force and page_file.is_file():
            content = page_file.read_text(encoding="utf-8")
            if content.strip():
                logger.info(
                    "Page %d already parsed, reusing cached markdown",
                    page_num,
                )
                has_formula = "$$" in content or bool(
                    re.search(r"(?<!\\)\$[^$]+\$", content)
                )
                has_image = "[Hình vẽ trang" in content or "![" in content
                meta = ParsedPageMetadata(
                    page_number=page_num,
                    has_formula=has_formula,
                    has_image=has_image,
                    char_count=len(content),
                    file_path=str(page_file),
                )
                return page_num, content, meta

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

        # Render page to PNG in RAM
        png_bytes = self.renderer.render_page_to_png_bytes(pdf_path, page_num)

        # Call Gemini Vision parser
        content, meta = await self.vision_parser.parse_page_image(png_bytes, page_num)

        # Save individual page markdown
        with open(page_file, "w", encoding="utf-8") as f:
            f.write(content)

        meta.file_path = str(page_file)
        return page_num, content, meta

    async def run_ingestion_pipeline(
        self,
        document_id: str,
        pdf_path: str | Path,
        title: str,
        force: bool = False,
    ) -> DocumentMetadata:
        """Main Ingestion Worker execution method."""
        file_path = Path(pdf_path)
        doc_dir = self.get_document_dir(document_id)
        pages_dir = doc_dir / "pages"

        file_size_kb = int(file_path.stat().st_size / 1024) if file_path.exists() else 0
        total_pages = self.renderer.get_page_count(file_path)

        metadata = DocumentMetadata(
            document_id=document_id,
            title=title,
            file_path=str(file_path),
            file_size_kb=file_size_kb,
            total_pages=total_pages,
            status="parsing",
        )
        self.save_metadata(metadata)
        logger.info(
            "Starting ingestion for document '%s' (ID: %s, Pages: %d)",
            title,
            document_id,
            total_pages,
        )

        try:
            # Dispatch concurrent parsing tasks
            tasks = [
                self._process_single_page(
                    file_path, page_num, pages_dir, force=force
                )
                for page_num in range(1, total_pages + 1)
            ]
            results = await asyncio.gather(*tasks)

            # Sort results by page_number
            results.sort(key=lambda r: r[0])

            parsed_pages_meta: list[ParsedPageMetadata] = []
            combined_blocks: list[str] = []

            for page_num, content, page_meta in results:
                parsed_pages_meta.append(page_meta)
                combined_blocks.append(
                    f"<!-- PAGE_BREAK: {page_num} -->\n\n{content}\n"
                )

            # Save full document markdown
            full_markdown = "\n".join(combined_blocks)
            full_doc_path = self.get_full_doc_path(document_id)
            with open(full_doc_path, "w", encoding="utf-8") as f:
                f.write(full_markdown)

            # Mark document as indexing
            metadata.status = "indexing"
            metadata.pages = parsed_pages_meta
            metadata.error_message = None
            self.save_metadata(metadata)
            logger.info("Starting vector indexing for document ID: %s", document_id)

            # Execute Qdrant vector indexing
            self.vector_service.index_document_pages(document_id, parsed_pages_meta)

            # Mark document as ready
            metadata.status = "ready"
            self.save_metadata(metadata)
            logger.info(
                "Ingestion & indexing completed successfully for document ID: %s",
                document_id,
            )
            return metadata

        except Exception as exc:
            logger.exception("Ingestion failed for document ID: %s", document_id)
            metadata.status = "failed"
            metadata.error_message = str(exc)
            self.save_metadata(metadata)
            raise

    def get_document_status(self, document_id: str) -> DocumentStatusResponse | None:
        metadata = self.load_metadata(document_id)
        if not metadata:
            return None
        return DocumentStatusResponse(
            document_id=metadata.document_id,
            title=metadata.title,
            status=metadata.status,
            total_pages=metadata.total_pages,
            parsed_pages=len(metadata.pages),
            error_message=metadata.error_message,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
        )

    def get_document_content(
        self, document_id: str, page_number: int | None = None
    ) -> DocumentContentResponse | None:
        metadata = self.load_metadata(document_id)
        if not metadata:
            return None

        if page_number is not None:
            page_file = (
                self.get_document_dir(document_id) / "pages" / f"page_{page_number}.md"
            )
            content = (
                page_file.read_text(encoding="utf-8") if page_file.is_file() else None
            )
        else:
            full_file = self.get_full_doc_path(document_id)
            content = (
                full_file.read_text(encoding="utf-8") if full_file.is_file() else None
            )

        return DocumentContentResponse(
            document_id=metadata.document_id,
            title=metadata.title,
            status=metadata.status,
            total_pages=metadata.total_pages,
            full_content=content,
            pages=metadata.pages,
        )

    def delete_document(self, document_id: str) -> bool:
        """Deletes all data associated with a document (uploaded file and parsed directory)."""
        doc_dir = self.parsed_base_dir / document_id
        metadata = self.load_metadata(document_id)

        pdf_path = None
        if metadata and metadata.file_path:
            pdf_path = Path(metadata.file_path)
        else:
            default_pdf = Path(settings.UPLOAD_DIR) / f"{document_id}.pdf"
            if default_pdf.exists():
                pdf_path = default_pdf

        exists = (pdf_path is not None and pdf_path.exists()) or doc_dir.exists()
        if not exists:
            return False

        if pdf_path and pdf_path.exists():
            try:
                pdf_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to delete PDF file %s: %s", pdf_path, e)

        default_pdf = Path(settings.UPLOAD_DIR) / f"{document_id}.pdf"
        if default_pdf.exists():
            try:
                default_pdf.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(
                    "Failed to delete default PDF file %s: %s", default_pdf, e
                )

        if doc_dir.exists():
            shutil.rmtree(doc_dir, ignore_errors=True)

        # Delete vectors from Qdrant
        try:
            self.vector_service.delete_document_vectors(document_id)
        except Exception as e:
            logger.warning("Failed to delete vectors for document %s: %s", document_id, e)

        logger.info("Deleted document %s and its associated files and vectors", document_id)
        return True


ingestion_service = IngestionService()
