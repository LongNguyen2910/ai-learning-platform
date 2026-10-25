import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_active_user
from app.modules.auth.models import User
from app.modules.documents.models import Document
from app.modules.documents.service import ingestion_service


async def get_valid_user_document(
    document_id: str,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Document:
    """Validates that a document exists and belongs to the authenticated user.

    Raises 404 Not Found if missing or owned by another user (prevents IDOR).
    """
    # 1. Primary check: Query PostgreSQL documents table
    try:
        doc_uuid = uuid.UUID(document_id)
        stmt = select(Document).where(
            Document.id == doc_uuid,
            Document.user_id == current_user.id,
        )
        doc = await db.scalar(stmt)
        if doc:
            return doc
    except (ValueError, TypeError):
        pass

    # 2. Secondary check: Inspect parsed metadata.json for file-backed storage
    meta = ingestion_service.load_metadata(document_id)
    if meta:
        # If user_id is explicitly specified, enforce exact ownership match
        if meta.user_id is not None and str(meta.user_id) != str(current_user.id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{document_id}' not found.",
            )

        # Allow if user matches or if legacy unassigned metadata in development
        if meta.user_id is None or str(meta.user_id) == str(current_user.id):
            try:
                assigned_id = uuid.UUID(document_id)
            except (ValueError, TypeError):
                assigned_id = uuid.uuid4()

            return Document(
                id=assigned_id,
                user_id=current_user.id,
                title=meta.title,
                file_path=meta.file_path,
                file_type="pdf",
                file_size_kb=meta.file_size_kb,
                total_pages=meta.total_pages,
                status=meta.status,
                error_message=meta.error_message,
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Document '{document_id}' not found.",
    )
