import logging
import shutil
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)

from app.core.config import settings
from app.modules.documents.renderer import PDFPageRenderer
from app.modules.documents.schemas import (
    DocumentContentResponse,
    DocumentDeleteResponse,
    DocumentRetryResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.modules.documents.service import ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload PDF and trigger background ingestion parsing",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF document file"),
    title: str | None = Form(None, description="Optional document display title"),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    document_id = str(uuid.uuid4())
    doc_title = title or Path(file.filename).stem

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    destination = upload_dir / f"{document_id}.pdf"

    try:
        with open(destination, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        logger.exception("Failed to write uploaded file to %s", destination)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not save uploaded file: {exc}",
        )
    finally:
        await file.close()

    # Validate file size
    file_size_mb = destination.stat().st_size / (1024 * 1024)
    if file_size_mb > settings.MAX_FILE_SIZE_MB:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB.",
        )

    # Validate PDF and get page count
    try:
        total_pages = PDFPageRenderer.get_page_count(destination)
    except Exception as exc:
        destination.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid or corrupted PDF file: {exc}",
        )

    # Dispatch ingestion worker task to background
    background_tasks.add_task(
        ingestion_service.run_ingestion_pipeline,
        document_id=document_id,
        pdf_path=destination,
        title=doc_title,
    )

    return DocumentUploadResponse(
        document_id=document_id,
        title=doc_title,
        status="uploading",
        total_pages=total_pages,
        message=f"Document uploaded successfully. Parsing {total_pages} pages in background.",
    )


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Get document parsing status",
)
async def get_document_status(document_id: str):
    res = ingestion_service.get_document_status(document_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return res


@router.get(
    "/{document_id}/content",
    response_model=DocumentContentResponse,
    summary="Get parsed markdown content (full or per-page)",
)
async def get_document_content(
    document_id: str,
    page: int | None = Query(
        None, description="1-indexed page number to retrieve", ge=1
    ),
):
    res = ingestion_service.get_document_content(document_id, page_number=page)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return res


@router.delete(
    "/{document_id}",
    response_model=DocumentDeleteResponse,
    summary="Delete a document and all associated files",
)
async def delete_document(document_id: str):
    success = ingestion_service.delete_document(document_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )
    return DocumentDeleteResponse(
        document_id=document_id,
        message=f"Document '{document_id}' and all associated files deleted successfully.",
    )


@router.post(
    "/{document_id}/retry",
    response_model=DocumentRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry parsing for a failed document",
)
async def retry_document(
    document_id: str,
    background_tasks: BackgroundTasks,
):
    metadata = ingestion_service.load_metadata(document_id)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    if metadata.status == "parsing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document '{document_id}' is currently being processed.",
        )

    pdf_path = Path(metadata.file_path)
    if not pdf_path.is_file():
        fallback_pdf = Path(settings.UPLOAD_DIR) / f"{document_id}.pdf"
        if fallback_pdf.is_file():
            pdf_path = fallback_pdf
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Original PDF file is missing on server. Please upload the file again.",
            )

    # Reset metadata state for retry
    metadata.status = "parsing"
    metadata.error_message = None
    ingestion_service.save_metadata(metadata)

    background_tasks.add_task(
        ingestion_service.run_ingestion_pipeline,
        document_id=document_id,
        pdf_path=pdf_path,
        title=metadata.title,
    )

    return DocumentRetryResponse(
        document_id=document_id,
        title=metadata.title,
        status="parsing",
        total_pages=metadata.total_pages,
        message=f"Retry scheduled for document '{document_id}'.",
    )
