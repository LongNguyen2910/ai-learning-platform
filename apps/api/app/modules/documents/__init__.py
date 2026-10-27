"""Documents module public API."""

from app.modules.documents.hybrid_router import (
    HybridPageRouter,
    PageClassifier,
    PageRoute,
)
from app.modules.documents.models import Document, Subject
from app.modules.documents.renderer import PDFPageRenderer
from app.modules.documents.router import router as documents_router
from app.modules.documents.service import IngestionService, ingestion_service
from app.modules.documents.splitter import MarkdownStructureSplitter
from app.modules.documents.storage import DocumentStorage, document_storage
from app.modules.documents.subjects_router import subjects_router
from app.modules.documents.vector_service import (
    DocumentVectorService,
    document_vector_service,
)
from app.modules.documents.vision_parser import GeminiVisionParser

__all__ = [
    "Document",
    "DocumentStorage",
    "DocumentVectorService",
    "GeminiVisionParser",
    "HybridPageRouter",
    "IngestionService",
    "MarkdownStructureSplitter",
    "PDFPageRenderer",
    "PageClassifier",
    "PageRoute",
    "Subject",
    "document_storage",
    "document_vector_service",
    "documents_router",
    "ingestion_service",
    "subjects_router",
]
