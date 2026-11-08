import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal, get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.quizzes.exceptions import GeminiGenerationError, QuizNotFoundError
from app.modules.quizzes.schemas import QuizResponse
from app.modules.roadmaps.exceptions import (
    DocumentNotParsedException,
    InvalidStudyGoalException,
    NodeLockedException,
    NodeNotFoundException,
    NodeNotLeafException,
    PrerequisiteNotCompletedException,
    RoadmapAccessForbiddenException,
    RoadmapExamLockedException,
    RoadmapNotActiveException,
    RoadmapNotFoundException,
    RoadmapRemediationNotAllowedException,
    SubjectNotFoundException,
)
from app.modules.roadmaps.repository import RoadmapRepository
from app.modules.roadmaps.schemas import (
    RoadmapExamAttemptResponse,
    RoadmapExamStateResponse,
    RoadmapExamSubmitRequest,
    RoadmapGenerateRequest,
    RoadmapNodeCompletionResponse,
    RoadmapResponse,
    RoadmapTaskStatusResponse,
    RoadmapTreeResponse,
)
from app.modules.roadmaps.service import RoadmapService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/roadmaps", tags=["Roadmaps"])
_global_task_registry: dict[str, RoadmapTaskStatusResponse] = {}


async def _execute_roadmap_pipeline(
    task_id: str,
    roadmap_id: uuid.UUID,
    req: RoadmapGenerateRequest,
    weak_topics: list[str] | None = None,
    incorrect_questions_summary: list[str] | None = None,
    iteration: int = 1,
    is_remediation: bool = False,
) -> None:
    """Isolated background runner with dedicated async session."""
    async with AsyncSessionLocal() as session:
        repo = RoadmapRepository(session)
        service = RoadmapService(repo)
        service._task_cache = _global_task_registry
        if is_remediation:
            await service.run_generation_pipeline(
                task_id,
                roadmap_id,
                req,
                weak_topics=weak_topics,
                incorrect_questions_summary=incorrect_questions_summary,
                iteration=iteration,
                is_remediation=True,
            )
        else:
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


@router.get("/{roadmap_id}/exam", response_model=RoadmapExamStateResponse)
async def get_roadmap_exam_state(
    roadmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoadmapExamStateResponse:
    """Returns the Final Assessment state, active exam quiz, and latest attempt for a roadmap."""
    repo = RoadmapRepository(db)
    service = RoadmapService(repo)
    try:
        return await service.get_roadmap_exam_state(
            roadmap_id=roadmap_id,
            user_id=current_user.id,
            user_role=current_user.role,
        )
    except RoadmapNotFoundException as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.message
        ) from err
    except RoadmapAccessForbiddenException as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.message
        ) from err


@router.post(
    "/{roadmap_id}/exam/generate",
    response_model=QuizResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_roadmap_final_exam(
    roadmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QuizResponse:
    """Generates a multi-document Final Assessment across the subject once roadmap reaches 100%."""
    repo = RoadmapRepository(db)
    service = RoadmapService(repo)
    try:
        quiz_resp = await service.generate_roadmap_exam(
            roadmap_id=roadmap_id,
            user_id=current_user.id,
            user_role=current_user.role,
        )
        await db.commit()
        return quiz_resp
    except (RoadmapNotFoundException, DocumentNotParsedException) as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.message
        ) from err
    except RoadmapAccessForbiddenException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.message
        ) from err
    except RoadmapExamLockedException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=err.message
        ) from err
    except GeminiGenerationError as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err)
        ) from err
    except Exception as err:
        await db.rollback()
        logger.exception("Unexpected error generating roadmap exam for %s", roadmap_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate final assessment: {err}",
        ) from err


@router.post(
    "/{roadmap_id}/exam/submit",
    response_model=RoadmapExamAttemptResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_roadmap_final_exam(
    roadmap_id: uuid.UUID,
    req: RoadmapExamSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoadmapExamAttemptResponse:
    """Submits and grades a Roadmap Final Assessment (Pass >= 50%, Fail < 50%)."""
    repo = RoadmapRepository(db)
    service = RoadmapService(repo)
    try:
        attempt_resp = await service.submit_roadmap_exam(
            roadmap_id=roadmap_id,
            user_id=current_user.id,
            req=req,
            user_role=current_user.role,
        )
        await db.commit()
        return attempt_resp
    except (RoadmapNotFoundException, QuizNotFoundError) as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except RoadmapAccessForbiddenException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.message
        ) from err
    except RoadmapExamLockedException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=err.message
        ) from err
    except Exception as err:
        await db.rollback()
        logger.exception("Unexpected error submitting roadmap exam for %s", roadmap_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit final assessment: {err}",
        ) from err


@router.post(
    "/{roadmap_id}/remediate",
    response_model=RoadmapTaskStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def remediate_failed_roadmap(
    roadmap_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoadmapTaskStatusResponse:
    """Archives a failed roadmap and generates a longer, deeper Adaptive Remediation Roadmap."""
    repo = RoadmapRepository(db)
    service = RoadmapService(repo)
    service._task_cache = _global_task_registry

    try:
        (
            task_response,
            req,
            weak_topics,
            incorrect_questions_summary,
            new_iteration,
        ) = await service.initiate_remediation(
            roadmap_id=roadmap_id,
            user_id=current_user.id,
            user_role=current_user.role,
        )
        await db.commit()
    except (RoadmapNotFoundException, DocumentNotParsedException) as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.message
        ) from err
    except RoadmapAccessForbiddenException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.message
        ) from err
    except RoadmapRemediationNotAllowedException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=err.message
        ) from err
    except Exception as err:
        await db.rollback()
        logger.exception("Unexpected error initiating remediation for %s", roadmap_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate adaptive remediation: {err}",
        ) from err

    background_tasks.add_task(
        _execute_roadmap_pipeline,
        task_response.task_id,
        task_response.roadmap_id,
        req,
        weak_topics,
        incorrect_questions_summary,
        new_iteration,
        True,
    )
    return task_response


@router.get("", response_model=list[RoadmapResponse])
async def list_user_roadmaps(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RoadmapResponse]:
    """Lists all roadmaps belonging to the current user."""
    repo = RoadmapRepository(db)
    roadmaps = await repo.get_roadmaps_by_user(current_user.id)
    return [RoadmapResponse.model_validate(r) for r in roadmaps]


@router.delete("/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_roadmap(
    roadmap_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Deletes a roadmap belonging to the current user."""
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
    await repo.delete_roadmap(roadmap_id)
    await db.commit()


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


@router.post("/nodes/{node_id}/complete", response_model=RoadmapNodeCompletionResponse)
async def complete_roadmap_node(
    node_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoadmapNodeCompletionResponse:
    """Marks a leaf study block complete, unlocking next block and updating progress (FR-14)."""
    repo = RoadmapRepository(db)
    service = RoadmapService(repo)

    try:
        result = await service.complete_study_block(
            node_id=node_id,
            user_id=current_user.id,
            user_role=current_user.role,
        )
        await db.commit()
        return result
    except (NodeNotFoundException, RoadmapNotFoundException) as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=err.message
        ) from err
    except RoadmapAccessForbiddenException as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=err.message
        ) from err
    except (
        RoadmapNotActiveException,
        NodeNotLeafException,
        NodeLockedException,
        PrerequisiteNotCompletedException,
    ) as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=err.message
        ) from err
