import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.roadmaps.exceptions import (
    DocumentNotParsedException,
    InvalidStudyGoalException,
    RoadmapNotFoundException,
    SubjectNotFoundException,
)
from app.modules.roadmaps.repository import RoadmapRepository
from app.modules.roadmaps.schemas import (
    RoadmapGenerateRequest,
    RoadmapResponse,
    RoadmapTaskStatusResponse,
    RoadmapTreeResponse,
)
from app.modules.roadmaps.service import RoadmapService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roadmaps", tags=["Roadmaps"])
_global_task_registry: dict[str, RoadmapTaskStatusResponse] = {}


async def _execute_roadmap_pipeline(
    task_id: str, roadmap_id: uuid.UUID, req: RoadmapGenerateRequest
) -> None:
    """Isolated background runner with dedicated async session."""
    async with AsyncSessionLocal() as session:
        repo = RoadmapRepository(session)
        service = RoadmapService(repo)
        service._task_cache = _global_task_registry
        await service.run_generation_pipeline(task_id, roadmap_id, req)


@router.post(
    "/generate",
    response_model=RoadmapTaskStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_initial_roadmap(
    req: RoadmapGenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> RoadmapTaskStatusResponse:
    """Initiates asynchronous generation of the 3-tier Roadmap Tree (FR-12)."""
    repo = RoadmapRepository(db)
    service = RoadmapService(repo)
    service._task_cache = _global_task_registry

    try:
        task_response = await service.initiate_generation(current_user.id, req)
        await db.commit()
    except SubjectNotFoundException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.message
        ) from err
    except DocumentNotParsedException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.message
        ) from err
    except InvalidStudyGoalException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=err.message
        ) from err
    except IntegrityError as err:
        await db.rollback()
        logger.error("Database integrity error during roadmap generation: %s", err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database foreign key constraint violation. Ensure subject and document exist.",
        ) from err

    background_tasks.add_task(
        _execute_roadmap_pipeline,
        task_response.task_id,
        task_response.roadmap_id,
        req,
    )
    return task_response


@router.get("/tasks/{task_id}", response_model=RoadmapTaskStatusResponse)
async def get_roadmap_task_status(task_id: str) -> RoadmapTaskStatusResponse:
    """Polls progress percentage and lifecycle state of the background roadmap generation."""
    status_item = _global_task_registry.get(task_id)
    if not status_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' was not found.",
        )
    return status_item


@router.get("/{roadmap_id}/tree", response_model=RoadmapTreeResponse)
async def get_roadmap_tree_structure(
    roadmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoadmapTreeResponse:
    """Returns the full 3-tier hierarchical tree (Chapters -> Topics -> Study Blocks)."""
    repo = RoadmapRepository(db)
    service = RoadmapService(repo)

    roadmap = await repo.get_roadmap_by_id(roadmap_id)
    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Roadmap with id '{roadmap_id}' was not found.",
        )
    if roadmap.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this roadmap.",
        )

    try:
        return await service.get_roadmap_tree(roadmap_id)
    except RoadmapNotFoundException as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=exc.message
        ) from exc


@router.get("/subject/{subject_id}", response_model=list[RoadmapResponse])
async def list_subject_roadmaps(
    subject_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RoadmapResponse]:
    """Lists all roadmaps created for a specific subject belonging to the current user."""
    repo = RoadmapRepository(db)
    subject = await repo.get_subject_by_id(subject_id)
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subject with id '{subject_id}' was not found.",
        )
    if subject.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this subject.",
        )
    roadmaps = await repo.get_roadmaps_by_subject(subject_id, user_id=current_user.id)
    return [RoadmapResponse.model_validate(r) for r in roadmaps]


@router.get("/{roadmap_id}", response_model=RoadmapResponse)
async def get_roadmap_details(
    roadmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoadmapResponse:
    """Gets summary details of a roadmap with authorization check."""
    repo = RoadmapRepository(db)
    roadmap = await repo.get_roadmap_by_id(roadmap_id)
    if not roadmap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Roadmap '{roadmap_id}' was not found.",
        )
    if roadmap.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this roadmap.",
        )
    return RoadmapResponse.model_validate(roadmap)
