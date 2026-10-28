import json
import logging
import uuid
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.modules.documents.models import Document
from app.modules.roadmaps.ai_curriculum_extractor import (
    AICurriculumExtractor,
    SourceDocumentInput,
)
from app.modules.roadmaps.exceptions import (
    DocumentNotParsedException,
    RoadmapNotFoundException,
    SubjectNotFoundException,
)
from app.modules.roadmaps.models import RoadmapNode
from app.modules.roadmaps.repository import RoadmapRepository
from app.modules.roadmaps.roadmap_tree_builder import RoadmapTreeBuilder
from app.modules.roadmaps.schemas import (
    RoadmapGenerateRequest,
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
    """Application Service orchestrating initial Roadmap Tree generation (FR-12)."""

    def __init__(
        self,
        repository: RoadmapRepository,
        extractor: AICurriculumExtractor | None = None,
        calculator: StudyBlockPacingCalculator | None = None,
        builder: RoadmapTreeBuilder | None = None,
    ) -> None:
        self.repo = repository
        self.extractor = extractor or AICurriculumExtractor()
        self.calculator = calculator or StudyBlockPacingCalculator()
        self.builder = builder or RoadmapTreeBuilder()
        self._task_cache: dict[str, RoadmapTaskStatusResponse] = {}

    async def _resolve_subject_source_documents(
        self,
        user_id: uuid.UUID,
        subject_id: uuid.UUID,
        explicit_document_id: uuid.UUID | None,
        fallback_title: str,
    ) -> list[SourceDocumentInput]:
        """Resolves one or all parsed documents belonging to the subject."""
        if explicit_document_id is not None:
            document = await self.repo.get_document_by_id(explicit_document_id)
            doc_dir = Path(settings.PARSED_DIR) / str(explicit_document_id)
            meta_file = doc_dir / "metadata.json"

            if document is None:
                if not meta_file.is_file() and not (doc_dir / "pages").exists():
                    raise DocumentNotParsedException(explicit_document_id)

                total_pages = self._resolve_total_pages(doc_dir)
                file_path = str(
                    Path(settings.UPLOAD_DIR) / f"{explicit_document_id}.pdf"
                )
                document = Document(
                    id=explicit_document_id,
                    user_id=user_id,
                    subject_id=subject_id,
                    title=fallback_title,
                    file_path=file_path,
                    file_type="pdf",
                    file_size_kb=0,
                    total_pages=total_pages,
                    status="ready",
                )
                self.repo.session.add(document)
                await self.repo.session.flush()

            total_pages = self._resolve_total_pages(doc_dir)
            return [
                SourceDocumentInput(
                    document_id=str(explicit_document_id),
                    title=document.title,
                    total_pages=total_pages,
                    doc_dir=doc_dir,
                )
            ]

        # Multi-document Subject mode: gather all documents assigned to subject_id
        db_docs = await self.repo.get_documents_by_subject(
            subject_id, user_id=user_id
        )
        source_map: dict[str, SourceDocumentInput] = {}

        for d in db_docs:
            doc_str = str(d.id)
            doc_dir = Path(settings.PARSED_DIR) / doc_str
            if (doc_dir / "metadata.json").is_file() or (
                doc_dir / "pages"
            ).exists():
                source_map[doc_str] = SourceDocumentInput(
                    document_id=doc_str,
                    title=d.title,
                    total_pages=self._resolve_total_pages(doc_dir),
                    doc_dir=doc_dir,
                )

        # Also check disk metadata.json in case a document was assigned via metadata
        parsed_root = Path(settings.PARSED_DIR)
        if parsed_root.exists():
            for entry in parsed_root.iterdir():
                if not entry.is_dir() or entry.name in source_map:
                    continue
                meta_file = entry / "metadata.json"
                if not meta_file.is_file():
                    continue
                try:
                    with open(meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    if str(meta.get("subject_id") or "") != str(subject_id):
                        continue
                    if (
                        meta.get("user_id")
                        and str(meta.get("user_id")) != str(user_id)
                    ):
                        continue
                    doc_uuid = uuid.UUID(entry.name)
                    total_pages = self._resolve_total_pages(entry)
                    title = str(meta.get("title") or fallback_title)

                    existing_db = await self.repo.get_document_by_id(doc_uuid)
                    if existing_db is None:
                        file_path = str(
                            meta.get("file_path")
                            or (Path(settings.UPLOAD_DIR) / f"{entry.name}.pdf")
                        )
                        new_doc = Document(
                            id=doc_uuid,
                            user_id=user_id,
                            subject_id=subject_id,
                            title=title,
                            file_path=file_path,
                            file_type="pdf",
                            file_size_kb=int(meta.get("file_size_kb") or 0),
                            total_pages=total_pages,
                            status=str(meta.get("status") or "ready"),
                        )
                        self.repo.session.add(new_doc)
                        await self.repo.session.flush()

                    source_map[entry.name] = SourceDocumentInput(
                        document_id=entry.name,
                        title=title,
                        total_pages=total_pages,
                        doc_dir=entry,
                    )
                except Exception as err:
                    logger.debug(
                        "Skipping disk metadata entry %s: %s", entry.name, err
                    )

        sources = list(source_map.values())
        if not sources:
            raise DocumentNotParsedException(subject_id)

        return sources

    async def initiate_generation(
        self, user_id: uuid.UUID, req: RoadmapGenerateRequest
    ) -> RoadmapTaskStatusResponse:
        """Validates goal constraints, creates roadmap record, and initializes task state."""
        today = date.today()
        self.calculator.calculate_available_minutes(
            req.target_date, today, req.available_hours_per_day
        )

        # 1. Validate Subject existence and access control
        subject = await self.repo.get_subject_by_id(req.subject_id)
        if subject is None:
            raise SubjectNotFoundException(req.subject_id)
        if subject.user_id != user_id:
            raise SubjectNotFoundException(req.subject_id)

        # 2. Validate that at least 1 parsed document exists for this subject (or explicit document_id)
        sources = await self._resolve_subject_source_documents(
            user_id=user_id,
            subject_id=req.subject_id,
            explicit_document_id=req.document_id,
            fallback_title=req.title,
        )

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
            message=f"Đã khởi tạo tiến trình tổng hợp {len(sources)} tài liệu của môn học",
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
            roadmap = await self.repo.get_roadmap_by_id(roadmap_id)
            user_id = roadmap.user_id if roadmap else uuid.uuid4()

            sources = await self._resolve_subject_source_documents(
                user_id=user_id,
                subject_id=req.subject_id,
                explicit_document_id=req.document_id,
                fallback_title=req.title,
            )

            self._update_task(
                task_id,
                25,
                f"Đang trích xuất & hợp nhất nội dung từ {len(sources)} tài liệu...",
            )

            if len(sources) == 1 and req.document_id is not None:
                # Preserve exact call signature for unit tests mocking extract_outline
                curriculum = await self.extractor.extract_outline(
                    doc_dir=sources[0].doc_dir,
                    total_pages=sources[0].total_pages,
                    title=req.title,
                    study_goal=req.study_goal,
                )
            else:
                curriculum = await self.extractor.extract_multi_document_outline(
                    documents=sources,
                    roadmap_title=req.title,
                    study_goal=req.study_goal,
                )

            self._update_task(
                task_id, 60, "Đang tính toán phân bổ khối học Pomodoro..."
            )
            today = date.today()
            planned_chapters = self.calculator.allocate(
                curriculum=curriculum,
                target_date=req.target_date,
                today=today,
                hours_per_day=req.available_hours_per_day,
            )

            self._update_task(task_id, 80, "Đang dựng cấu trúc cây 3 tầng...")
            fallback_doc_uuid = (
                req.document_id
                if req.document_id is not None
                else uuid.UUID(sources[0].document_id)
            )
            unpersisted_nodes = self.builder.build_tree_nodes(
                planned_chapters=planned_chapters,
                document_id=fallback_doc_uuid,
            )

            await self.repo.persist_tree_nodes(roadmap_id, unpersisted_nodes)
            await self.repo.update_status(roadmap_id, "active")
            await self.repo.session.commit()

            self._update_task(
                task_id, 100, "Sinh lộ trình thành công", status="completed"
            )
        except Exception as exc:
            logger.error("Roadmap generation failed for task %s: %s", task_id, exc)
            try:
                await self.repo.session.rollback()
                await self.repo.update_status(roadmap_id, "failed")
                await self.repo.session.commit()
            except Exception as rollback_err:
                logger.error("Failed to update status to failed: %s", rollback_err)
            self._update_task(
                task_id,
                100,
                "Thất bại khi sinh lộ trình",
                status="failed",
                err=str(exc),
            )

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
        self,
        task_id: str,
        percent: int,
        msg: str,
        status: str = "processing",
        err: str | None = None,
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

    def _build_nested_tree(
        self, nodes: list[RoadmapNode]
    ) -> list[RoadmapNodeResponse]:
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
