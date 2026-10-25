import logging
import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.documents.dependencies import get_valid_user_document
from app.modules.documents.models import Document
from app.modules.documents.renderer import PDFPageRenderer
from app.modules.documents.schemas import (
    DocumentContentResponse,
    DocumentDeleteResponse,
    DocumentMetadata,
    DocumentRetryResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.modules.documents.service import ingestion_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get(
    "",
    response_model=list[DocumentStatusResponse],
    summary="List all uploaded documents for current user",
)
async def list_documents(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    try:
        stmt = (
            select(Document)
            .where(Document.user_id == current_user.id)
            .order_by(Document.created_at.desc())
        )
        db_docs = (await db.scalars(stmt)).all()
        if db_docs:
            items: list[DocumentStatusResponse] = []
            for d in db_docs:
                doc_str = str(d.id)
                meta = ingestion_service.load_metadata(doc_str)
                items.append(
                    DocumentStatusResponse(
                        document_id=doc_str,
                        user_id=str(d.user_id),
                        title=d.title,
                        status=d.status,
                        file_size_kb=d.file_size_kb,
                        total_pages=d.total_pages,
                        parsed_pages=len(meta.pages) if meta else 0,
                        error_message=d.error_message,
                        created_at=d.created_at.isoformat() if d.created_at else "",
                        updated_at=meta.updated_at if meta else "",
                    )
                )
            return items
    except Exception as exc:
        logger.debug(
            "Could not query documents from DB, falling back to filesystem metadata: %s",
            exc,
        )
    return ingestion_service.list_documents(user_id=str(current_user.id))


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
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported.",
        )

    document_id = str(uuid.uuid4())
    doc_title = title or Path(file.filename).stem

    user_prefix = str(current_user.id) if current_user else "shared"
    upload_dir = Path(settings.UPLOAD_DIR) / user_prefix
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
    file_size_bytes = destination.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
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

    # Save to PostgreSQL Document table if DB and current_user are present
    if db is not None and current_user is not None:
        try:
            doc_record = Document(
                id=uuid.UUID(document_id),
                user_id=current_user.id,
                title=doc_title,
                file_path=str(destination),
                file_type="pdf",
                file_size_kb=max(1, int(file_size_bytes / 1024)),
                total_pages=total_pages,
                status="uploading",
            )
            db.add(doc_record)
            await db.commit()
        except Exception as exc:
            logger.warning("Could not persist initial Document in DB: %s", exc)

    # Save initial metadata immediately so list/status queries see it right away
    initial_metadata = DocumentMetadata(
        document_id=document_id,
        user_id=str(current_user.id) if current_user else None,
        title=doc_title,
        file_path=str(destination),
        file_size_kb=max(1, int(file_size_bytes / 1024)),
        total_pages=total_pages,
        status="uploading",
    )
    ingestion_service.save_metadata(initial_metadata)

    # Dispatch ingestion worker task to background
    ingestion_service.mark_task_active(document_id)
    background_tasks.add_task(
        ingestion_service.run_ingestion_pipeline,
        document_id=document_id,
        pdf_path=destination,
        title=doc_title,
        user_id=str(current_user.id) if current_user else None,
    )

    return DocumentUploadResponse(
        document_id=document_id,
        user_id=str(current_user.id) if current_user else None,
        title=doc_title,
        status="uploading",
        total_pages=total_pages,
        message=f"Document uploaded successfully. Parsing {total_pages} pages in background.",
    )


@router.get(
    "/{document_id}/file",
    summary="Stream raw PDF file for inline viewing",
)
async def get_document_file(
    document_id: str,
    doc: Annotated[Document, Depends(get_valid_user_document)],
):
    pdf_path = ingestion_service.get_document_pdf_path(document_id)
    if not pdf_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PDF file for document '{document_id}' not found.",
        )
    filename = f"{doc.title or document_id}.pdf"
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get(
    "/{document_id}/status",
    response_model=DocumentStatusResponse,
    summary="Get document parsing status",
)
async def get_document_status(
    document_id: str,
    doc: Annotated[Document, Depends(get_valid_user_document)],
):
    res = ingestion_service.get_document_status(document_id)
    if not res:
        # Fallback response from DB Document model
        return DocumentStatusResponse(
            document_id=document_id,
            user_id=str(doc.user_id),
            title=doc.title,
            status=doc.status,
            file_size_kb=doc.file_size_kb,
            total_pages=doc.total_pages,
            parsed_pages=0,
            error_message=doc.error_message,
            created_at=doc.created_at.isoformat() if doc.created_at else "",
            updated_at="",
        )
    return res


@router.get(
    "/{document_id}/content",
    response_model=DocumentContentResponse,
    summary="Get parsed markdown content (full or per-page)",
)
async def get_document_content(
    document_id: str,
    doc: Annotated[Document, Depends(get_valid_user_document)],
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
async def delete_document(
    document_id: str,
    doc: Annotated[Document, Depends(get_valid_user_document)],
):
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
    doc: Annotated[Document, Depends(get_valid_user_document)],
    background_tasks: BackgroundTasks,
    force: bool = Query(
        False,
        description="If True, re-parses all pages from scratch instead of reusing cached markdowns.",
    ),
):
    metadata = ingestion_service.load_metadata(document_id)
    if not metadata:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found.",
        )

    if ingestion_service.is_task_active(document_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document '{document_id}' is currently being processed ({metadata.status}).",
        )

    pdf_path = Path(metadata.file_path)
    if not pdf_path.is_file():
        fallback_pdf = ingestion_service.get_document_pdf_path(document_id)
        if fallback_pdf and fallback_pdf.is_file():
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

    ingestion_service.mark_task_active(document_id)
    background_tasks.add_task(
        ingestion_service.run_ingestion_pipeline,
        document_id=document_id,
        pdf_path=pdf_path,
        title=metadata.title,
        force=force,
        user_id=str(doc.user_id),
    )

    return DocumentRetryResponse(
        document_id=document_id,
        title=metadata.title,
        status="parsing",
        total_pages=metadata.total_pages,
        message=f"Retry scheduled for document '{document_id}'.",
    )
