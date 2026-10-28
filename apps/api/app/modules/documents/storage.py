"""Document file storage & metadata management.

Handles file paths, saving and loading of JSON metadata, individual page markdown files,
full documents, and cleanup of physical assets on disk.
"""

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import shutil

from app.core.config import settings
from app.modules.documents.schemas import (
    DocumentContentResponse,
    DocumentMetadata,
    DocumentStatusResponse,
)

logger = logging.getLogger(__name__)


class DocumentStorage:
    """Encapsulates all disk-based persistence for uploaded PDFs and parsed Markdown."""

    def __init__(
        self,
        parsed_base_dir: str | Path | None = None,
        upload_base_dir: str | Path | None = None,
    ) -> None:
        self._parsed_base_dir = (
            Path(parsed_base_dir) if parsed_base_dir is not None else None
        )
        self._upload_base_dir = (
            Path(upload_base_dir) if upload_base_dir is not None else None
        )

    @property
    def parsed_base_dir(self) -> Path:
        base = (
            self._parsed_base_dir
            if self._parsed_base_dir is not None
            else Path(settings.PARSED_DIR)
        )
        base.mkdir(parents=True, exist_ok=True)
        return base

    @property
    def upload_base_dir(self) -> Path:
        base = (
            self._upload_base_dir
            if self._upload_base_dir is not None
            else Path(settings.UPLOAD_DIR)
        )
        base.mkdir(parents=True, exist_ok=True)
        return base

    def get_document_dir(self, document_id: str, create: bool = False) -> Path:
        """Returns the directory containing parsed pages and metadata for a document."""
        doc_dir = self.parsed_base_dir / document_id
        if create:
            doc_dir.mkdir(parents=True, exist_ok=True)
            (doc_dir / "pages").mkdir(parents=True, exist_ok=True)
        return doc_dir

    def get_metadata_path(self, document_id: str) -> Path:
        """Returns the path to metadata.json for a document."""
        return self.get_document_dir(document_id, create=False) / "metadata.json"

    def get_full_doc_path(self, document_id: str) -> Path:
        """Returns the path to full_document.md for a document."""
        return self.get_document_dir(document_id, create=False) / "full_document.md"

    def save_metadata(self, metadata: DocumentMetadata) -> None:
        """Persists DocumentMetadata to metadata.json atomically."""
        self.get_document_dir(metadata.document_id, create=True)
        path = self.get_metadata_path(metadata.document_id)
        metadata.updated_at = datetime.now(UTC).isoformat()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata.model_dump(), f, ensure_ascii=False, indent=2)

    def load_metadata(self, document_id: str) -> DocumentMetadata | None:
        """Loads and parses metadata.json into DocumentMetadata if it exists."""
        path = self.get_metadata_path(document_id)
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return DocumentMetadata.model_validate(data)
        except Exception as exc:
            logger.warning("Failed to load metadata for %s: %s", document_id, exc)
            return None

    def count_parsed_pages(
        self, document_id: str, metadata: DocumentMetadata | None = None
    ) -> int:
        """Counts how many pages have been parsed so far (including in-progress batches)."""
        if metadata and metadata.status == "ready" and metadata.pages:
            return len(metadata.pages)
        pages_dir = self.get_document_dir(document_id) / "pages"
        if pages_dir.is_dir():
            return sum(
                1
                for p in pages_dir.glob("page_*.md")
                if p.is_file() and p.stat().st_size > 0
            )
        if metadata and metadata.pages:
            return len(metadata.pages)
        return 0

    def get_document_pdf_path(self, document_id: str) -> Path | None:
        """Locates the original uploaded PDF file for a document."""
        metadata = self.load_metadata(document_id)
        if metadata and metadata.file_path:
            candidate = Path(metadata.file_path)
            if candidate.is_file():
                return candidate
        if metadata and metadata.user_id:
            user_candidate = self.upload_base_dir / str(metadata.user_id) / f"{document_id}.pdf"
            if user_candidate.is_file():
                return user_candidate
        fallback = self.upload_base_dir / f"{document_id}.pdf"
        if fallback.is_file():
            return fallback
        return None

    def get_document_status(self, document_id: str) -> DocumentStatusResponse | None:
        """Constructs DocumentStatusResponse from stored metadata and page files."""
        metadata = self.load_metadata(document_id)
        if not metadata:
            return None
        return DocumentStatusResponse(
            document_id=metadata.document_id,
            user_id=metadata.user_id,
            subject_id=metadata.subject_id,
            title=metadata.title,
            status=metadata.status,
            file_size_kb=metadata.file_size_kb,
            total_pages=metadata.total_pages,
            parsed_pages=self.count_parsed_pages(document_id, metadata),
            error_message=metadata.error_message,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
        )

    def get_document_content(
        self, document_id: str, page_number: int | None = None
    ) -> DocumentContentResponse | None:
        """Retrieves parsed markdown content (single page or full document)."""
        metadata = self.load_metadata(document_id)
        if not metadata:
            return None

        if page_number is not None:
            page_file = self.get_document_dir(document_id) / "pages" / f"page_{page_number}.md"
            content = page_file.read_text(encoding="utf-8") if page_file.is_file() else None
        else:
            full_file = self.get_full_doc_path(document_id)
            content = full_file.read_text(encoding="utf-8") if full_file.is_file() else None

        if content:
            from app.modules.documents.vision_parser import normalize_katex_syntax

            content = normalize_katex_syntax(content)

        return DocumentContentResponse(
            document_id=metadata.document_id,
            user_id=metadata.user_id,
            title=metadata.title,
            status=metadata.status,
            total_pages=metadata.total_pages,
            full_content=content,
            pages=metadata.pages,
        )

    def delete_document_files(self, document_id: str) -> bool:
        """Deletes all physical files (uploaded PDF and parsed directory) for a document."""
        doc_dir = self.parsed_base_dir / document_id
        metadata = self.load_metadata(document_id)
        pdf_path = self.get_document_pdf_path(document_id)

        exists = (pdf_path is not None and pdf_path.exists()) or doc_dir.exists()
        if not exists:
            return False

        if pdf_path and pdf_path.exists():
            try:
                pdf_path.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to delete PDF file %s: %s", pdf_path, e)

        if metadata and metadata.user_id:
            user_pdf = self.upload_base_dir / str(metadata.user_id) / f"{document_id}.pdf"
            if user_pdf.exists():
                try:
                    user_pdf.unlink(missing_ok=True)
                except Exception as e:
                    logger.warning("Failed to delete user PDF %s: %s", user_pdf, e)

        default_pdf = self.upload_base_dir / f"{document_id}.pdf"
        if default_pdf.exists():
            try:
                default_pdf.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to delete default PDF file %s: %s", default_pdf, e)

        if doc_dir.exists():
            shutil.rmtree(doc_dir, ignore_errors=True)

        return True

    def list_documents(self, user_id: str | None = None) -> list[DocumentStatusResponse]:
        """Lists all stored documents on disk, optionally filtering by user_id."""
        if not self.parsed_base_dir.exists():
            return []
        items: list[DocumentStatusResponse] = []
        for entry in self.parsed_base_dir.iterdir():
            if entry.is_dir():
                status_res = self.get_document_status(entry.name)
                if status_res is not None:
                    if (
                        user_id is not None
                        and status_res.user_id is not None
                        and str(status_res.user_id) != str(user_id)
                    ):
                        continue
                    items.append(status_res)
        items.sort(key=lambda x: x.created_at, reverse=True)
        return items


document_storage = DocumentStorage()
