import json
import logging
import uuid
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.modules.documents.models import Document
from app.modules.roadmaps.ai_curriculum_extractor import AICurriculumExtractor
from app.modules.roadmaps.domain.node_progression_calculator import (
    NodeProgressionCalculator,
)
from app.modules.roadmaps.exceptions import (
    DocumentNotParsedException,
    NodeNotFoundException,
    RoadmapAccessForbiddenException,
    RoadmapNotActiveException,
    RoadmapNotFoundException,
    SubjectNotFoundException,
)
from app.modules.roadmaps.models import RoadmapNode
from app.modules.roadmaps.repository import RoadmapRepository
from app.modules.roadmaps.roadmap_tree_builder import RoadmapTreeBuilder
from app.modules.roadmaps.schemas import (
    RoadmapGenerateRequest,
    RoadmapNodeCompletionResponse,
    RoadmapNodeResponse,
    RoadmapResponse,
    RoadmapTaskStatusResponse,
    RoadmapTreeResponse,
)
from app.modules.roadmaps.study_block_pacing_calculator import (
    StudyBlockPacingCalculator,
)

logger = logging.getLogger(__name__)


class RoadmapService:
    """Application Service orchestrating Roadmap Tree generation and Progression (FR-12, FR-13, FR-14)."""

    def __init__(
        self,
        repository: RoadmapRepository,
        extractor: AICurriculumExtractor | None = None,
        calculator: StudyBlockPacingCalculator | None = None,
        builder: RoadmapTreeBuilder | None = None,
        progression_calculator: NodeProgressionCalculator | None = None,
    ) -> None:
        self.repo = repository
        self.extractor = extractor or AICurriculumExtractor()
        self.calculator = calculator or StudyBlockPacingCalculator()
        self.builder = builder or RoadmapTreeBuilder()
        self.progression_calculator = progression_calculator or NodeProgressionCalculator()
        self._task_cache: dict[str, RoadmapTaskStatusResponse] = {}

    async def complete_study_block(
        self,
        node_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str = "user",
    ) -> RoadmapNodeCompletionResponse:
        """Completes a leaf study block, cascading completion and unlocking next block (FR-14)."""
        node = await self.repo.get_node_by_id(node_id)
        if not node:
            raise NodeNotFoundException(node_id)

        roadmap = await self.repo.get_roadmap_by_id(node.roadmap_id)
        if not roadmap:
            raise RoadmapNotFoundException(node.roadmap_id)

        if roadmap.status == "archived":
            raise RoadmapNotActiveException(roadmap.id, roadmap.status)

        if roadmap.user_id != user_id and user_role != "admin":
            raise RoadmapAccessForbiddenException(roadmap.id)

        all_nodes = (
            list(roadmap.nodes)
            if roadmap.nodes
            else await self.repo.get_nodes_by_roadmap_id(roadmap.id)
        )
        result = self.progression_calculator.calculate_completion(all_nodes, node_id)

        roadmap.progress_percentage = result.progress_percentage
        roadmap.status = result.roadmap_status
        await self.repo.session.flush()

        return RoadmapNodeCompletionResponse(
            completed_node_id=node_id,
            unlocked_node_ids=result.unlocked_node_ids,
            progress_percentage=result.progress_percentage,
            roadmap_status=result.roadmap_status,
        )

    async def initiate_generation(
        self, user_id: uuid.UUID, req: RoadmapGenerateRequest
    ) -> RoadmapTaskStatusResponse:
        """Validates goal constraints, creates roadmap record, and initializes task state."""
        today = date.today()
        self.calculator.calculate_available_minutes(
            req.target_date, today, req.available_hours_per_day
        )

        subject = await self.repo.get_subject_by_id(req.subject_id)
        if subject is None or subject.user_id != user_id:
            raise SubjectNotFoundException(req.subject_id)

        document = await self.repo.get_document_by_id(req.document_id)
        doc_dir = Path(settings.PARSED_DIR) / str(req.document_id)
        meta_file = doc_dir / "metadata.json"

        if document is None:
            if not meta_file.is_file() and not (doc_dir / "pages").exists():
                raise DocumentNotParsedException(req.document_id)

            total_pages = self._resolve_total_pages(doc_dir)
            file_path = str(Path(settings.UPLOAD_DIR) / f"{req.document_id}.pdf")
            document = Document(
                id=req.document_id,
                user_id=user_id,
                subject_id=req.subject_id,
                title=req.title,
                file_path=file_path,
                file_type="pdf",
                file_size_kb=0,
                total_pages=total_pages,
                status="ready",
            )
            self.repo.session.add(document)
            await self.repo.session.flush()

        roadmap = await self.repo.create_roadmap(
            user_id=user_id,
            subject_id=req.subject_id,
            title=req.title,
            target_date=req.target_date,
            available_hours_per_day=req.available_hours_per_day,
        )
        task_id = str(uuid.uuid4())
        status_response = RoadmapTaskStatusResponse(
            task_id=task_id,
            roadmap_id=roadmap.id,
            status="processing",
            progress_percent=10,
            message="Đã khởi tạo tiến trình sinh cây lộ trình",
        )
        self._task_cache[task_id] = status_response
        return status_response

    async def run_generation_pipeline(
        self,
        task_id: str,
        roadmap_id: uuid.UUID,
        req: RoadmapGenerateRequest,
    ) -> None:
        """Executes the complete AI extraction and pacing allocation pipeline."""
        try:
            self._update_task(task_id, 25, "Đang trích xuất nội dung giáo trình...")
            doc_dir = Path(settings.PARSED_DIR) / str(req.document_id)
            total_pages = self._resolve_total_pages(doc_dir)

            curriculum = await self.extractor.extract_outline(
                doc_dir=doc_dir,
                total_pages=total_pages,
                title=req.title,
                study_goal=req.study_goal,
            )

            self._update_task(task_id, 60, "Đang tính toán phân bổ khối học Pomodoro...")
            today = date.today()
            planned_chapters = self.calculator.allocate(
                curriculum=curriculum,
                target_date=req.target_date,
                today=today,
                hours_per_day=req.available_hours_per_day,
                session_mode=req.session_mode,
            )

            self._update_task(task_id, 80, "Đang dựng cấu trúc cây 3 tầng...")
            unpersisted_nodes = self.builder.build_tree_nodes(
                planned_chapters=planned_chapters, document_id=req.document_id
            )

            await self.repo.persist_tree_nodes(roadmap_id, unpersisted_nodes)
            await self.repo.update_status(roadmap_id, "active")
            await self.repo.session.commit()

            self._update_task(task_id, 100, "Sinh lộ trình thành công", status="completed")
        except Exception as exc:
            logger.error("Roadmap generation failed for task %s: %s", task_id, exc)
            try:
                await self.repo.session.rollback()
                await self.repo.update_status(roadmap_id, "failed")
                await self.repo.session.commit()
            except Exception as rollback_err:
                logger.error("Failed to update status to failed: %s", rollback_err)
            self._update_task(task_id, 100, "Thất bại khi sinh lộ trình", status="failed", err=str(exc))

    async def get_roadmap_tree(self, roadmap_id: uuid.UUID) -> RoadmapTreeResponse:
        """Retrieves and transforms flat nodes into a nested 3-tier hierarchical tree."""
        roadmap = await self.repo.get_roadmap_by_id(roadmap_id)
        if roadmap is None:
            raise RoadmapNotFoundException(roadmap_id)

        tree = self._build_nested_tree(roadmap.nodes)
        total_minutes = sum(n.estimated_minutes for n in roadmap.nodes)

        return RoadmapTreeResponse(
            roadmap=RoadmapResponse.model_validate(roadmap),
            tree=tree,
            total_nodes=len(roadmap.nodes),
            total_estimated_minutes=total_minutes,
        )

    def get_task_status(self, task_id: str) -> RoadmapTaskStatusResponse | None:
        """Gets current background generation progress."""
        return self._task_cache.get(task_id)

    def _update_task(
        self, task_id: str, percent: int, msg: str, status: str = "processing", err: str | None = None
    ) -> None:
        """Internal helper to update task progress."""
        current = self._task_cache.get(task_id)
        if not current:
            return
        current.progress_percent = percent
        current.message = msg
        current.status = status
        current.error = err

    def _resolve_total_pages(self, doc_dir: Path) -> int:
        """Resolves total page count from metadata.json or page markdown files."""
        meta_file = doc_dir / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    total = data.get("total_pages")
                    if isinstance(total, int) and total > 0:
                        return total
            except Exception as err:
                logger.warning("Failed reading metadata.json in %s: %s", doc_dir, err)

        pages_dir = doc_dir / "pages"
        if pages_dir.exists():
            md_pages = list(pages_dir.glob("page_*.md"))
            if md_pages:
                return len(md_pages)

        return 1

    def _build_nested_tree(self, nodes: list[RoadmapNode]) -> list[RoadmapNodeResponse]:
        """Builds 3-tier hierarchy: Level 1 (Chapters) -> Level 2 (Topics) -> Level 3 (Blocks)."""
        node_map: dict[uuid.UUID, RoadmapNodeResponse] = {}
        roots: list[RoadmapNodeResponse] = []

        sorted_nodes = sorted(nodes, key=lambda n: n.order_index)
        for n in sorted_nodes:
            resp = RoadmapNodeResponse.model_validate(n)
            node_map[n.id] = resp

        for n in sorted_nodes:
            current_resp = node_map[n.id]
            if n.parent_node_id is None:
                roots.append(current_resp)
                continue
            parent = node_map.get(n.parent_node_id)
            if parent:
                parent.children.append(current_resp)

        return roots
