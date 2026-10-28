import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.documents.models import Document, Subject
from app.modules.documents.service import ingestion_service

subjects_router = APIRouter(prefix="/subjects", tags=["Subjects"])


class SubjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=150, description="Tên môn học, ví dụ: Giải tích 1")
    code: str | None = Field(default=None, max_length=50, description="Mã môn học, ví dụ: MAT101")
    description: str | None = Field(default=None, description="Mô tả tóm tắt môn học")
    color_hex: str = Field(default="#4F46E5", max_length=10, description="Mã màu HEX hiển thị")


class SubjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    code: str | None = None
    description: str | None = None
    color_hex: str
    created_at: datetime


@subjects_router.post(
    "",
    response_model=SubjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Subject for current user",
)
async def create_subject(
    req: SubjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectResponse:
    subject = Subject(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=req.name,
        code=req.code,
        description=req.description,
        color_hex=req.color_hex,
    )
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return SubjectResponse.model_validate(subject)


@subjects_router.get(
    "",
    response_model=list[SubjectResponse],
    summary="List all subjects belonging to current user",
)
async def list_subjects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SubjectResponse]:
    query = (
        select(Subject)
        .where(Subject.user_id == current_user.id)
        .order_by(Subject.created_at.desc())
    )
    result = await db.execute(query)
    subjects = result.scalars().all()
    return [SubjectResponse.model_validate(s) for s in subjects]


@subjects_router.get(
    "/{subject_id}",
    response_model=SubjectResponse,
    summary="Get subject details",
)
async def get_subject(
    subject_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubjectResponse:
    query = select(Subject).where(Subject.id == subject_id)
    result = await db.execute(query)
    subject = result.scalar_one_or_none()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject '{subject_id}' not found.",
        )
    if subject.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this subject.",
        )
    return SubjectResponse.model_validate(subject)


@subjects_router.delete(
    "/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a subject and unassign its documents",
)
async def delete_subject(
    subject_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    query = select(Subject).where(Subject.id == subject_id)
    result = await db.execute(query)
    subject = result.scalar_one_or_none()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject '{subject_id}' not found.",
        )
    if subject.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this subject.",
        )

    # Unassign documents in DB
    docs_query = select(Document).where(Document.subject_id == subject_id)
    docs = (await db.scalars(docs_query)).all()
    for d in docs:
        d.subject_id = None
        meta = ingestion_service.load_metadata(str(d.id))
        if meta is not None and meta.subject_id == str(subject_id):
            meta.subject_id = None
            ingestion_service.save_metadata(meta)

    # Also scan disk metadata for any documents referencing this subject_id
    if ingestion_service.parsed_base_dir.exists():
        for entry in ingestion_service.parsed_base_dir.iterdir():
            if entry.is_dir():
                meta = ingestion_service.load_metadata(entry.name)
                if meta is not None and str(meta.subject_id or "") == str(subject_id):
                    meta.subject_id = None
                    ingestion_service.save_metadata(meta)

    await db.delete(subject)
    await db.commit()
