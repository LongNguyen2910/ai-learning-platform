import json
import logging
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from google import genai
from google.genai import types

from app.core.config import settings
from app.modules.documents.models import Document
from app.modules.quizzes.exceptions import GeminiGenerationError, QuizNotFoundError
from app.modules.quizzes.models import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion
from app.modules.quizzes.prompt import (
    QUIZ_GENERATOR_SYSTEM_PROMPT,
    compute_bloom_distribution,
)
from app.modules.quizzes.schemas import (
    BloomLevel,
    GeneratedQuestionItem,
    GeneratedQuizPayload,
    QuizOptionItem,
    QuizQuestionResponse,
    QuizResponse,
)
from app.modules.roadmaps.ai_curriculum_extractor import (
    AICurriculumExtractor,
    SourceDocumentInput,
)
from app.modules.roadmaps.domain.node_progression_calculator import (
    NodeProgressionCalculator,
)
from app.modules.roadmaps.exceptions import (
    DocumentNotParsedException,
    NodeNotFoundException,
    RoadmapAccessForbiddenException,
    RoadmapExamLockedException,
    RoadmapNotActiveException,
    RoadmapNotFoundException,
    RoadmapRemediationNotAllowedException,
    SubjectNotFoundException,
)
from app.modules.roadmaps.models import Roadmap, RoadmapNode
from app.modules.roadmaps.repository import RoadmapRepository
from app.modules.roadmaps.roadmap_tree_builder import RoadmapTreeBuilder
from app.modules.roadmaps.schemas import (
    RoadmapExamAttemptResponse,
    RoadmapExamQuestionResult,
    RoadmapExamStateResponse,
    RoadmapExamSubmitRequest,
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
    """Application Service orchestrating Roadmap Tree generation, Final Assessment, and Adaptive Remediation."""

    PASS_THRESHOLD_PERCENT: float = 50.0

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
        self.progression_calculator = (
            progression_calculator or NodeProgressionCalculator()
        )
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
        current_exam_status = getattr(roadmap, "exam_status", None) or "locked"
        if (
            result.progress_percentage >= 100.0 or result.roadmap_status == "completed"
        ) and current_exam_status == "locked":
            current_exam_status = "ready"
            roadmap.exam_status = "ready"

        await self.repo.session.flush()

        return RoadmapNodeCompletionResponse(
            completed_node_id=node_id,
            unlocked_node_ids=result.unlocked_node_ids,
            progress_percentage=result.progress_percentage,
            roadmap_status=result.roadmap_status,
            exam_status=current_exam_status,
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

        # Validate that at least 1 parsed document exists for this subject (or explicit document_id)
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
        weak_topics: list[str] | None = None,
        incorrect_questions_summary: list[str] | None = None,
        iteration: int = 1,
        is_remediation: bool = False,
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

            if not is_remediation and len(sources) == 1 and req.document_id is not None:
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
                    weak_topics=weak_topics,
                    incorrect_questions_summary=incorrect_questions_summary,
                    iteration=iteration,
                )

            self._update_task(
                task_id, 60, "Đang tính toán phân bổ khối học Pomodoro..."
            )
            today = date.today()
            if is_remediation:
                planned_chapters = self.calculator.allocate(
                    curriculum=curriculum,
                    target_date=req.target_date,
                    today=today,
                    hours_per_day=req.available_hours_per_day,
                    session_mode=req.session_mode,
                    force_allow_secondary=True,
                    remediation_multiplier=1.5,
                )
            else:
                planned_chapters = self.calculator.allocate(
                    curriculum=curriculum,
                    target_date=req.target_date,
                    today=today,
                    hours_per_day=req.available_hours_per_day,
                    session_mode=req.session_mode,
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

    def _effective_exam_status(self, roadmap: Roadmap) -> str:
        raw_status = getattr(roadmap, "exam_status", None) or "locked"
        if raw_status == "locked" and (
            roadmap.progress_percentage >= 100.0 or roadmap.status == "completed"
        ):
            return "ready"
        return raw_status

    def _build_attempt_response(
        self,
        roadmap: Roadmap,
        quiz: Quiz,
        attempt: QuizAttempt,
        answers_override: list[QuizAttemptAnswer] | None = None,
    ) -> RoadmapExamAttemptResponse:
        question_map = {q.id: q for q in (quiz.questions or [])}
        answers_list = (
            answers_override
            if answers_override is not None
            else list(attempt.answers or [])
        )
        answer_map = {a.question_id: a for a in answers_list}

        results: list[RoadmapExamQuestionResult] = []
        weak_topics_list: list[str] = []

        for q in quiz.questions or []:
            ans = answer_map.get(q.id)
            selected = ans.selected_option if ans else None
            is_correct = bool(ans.is_correct) if ans else False
            if not is_correct and q.topic_tag and q.topic_tag not in weak_topics_list:
                weak_topics_list.append(q.topic_tag)

            results.append(
                RoadmapExamQuestionResult(
                    question_id=q.id,
                    selected_option=selected,
                    correct_option=q.correct_option,
                    is_correct=is_correct,
                    explanation=q.explanation,
                    topic_tag=q.topic_tag,
                    target_page=q.target_page,
                    source_document_id=getattr(q, "source_document_id", None)
                    or quiz.document_id,
                    source_document_title=getattr(q, "source_document_title", None),
                )
            )

        passed = attempt.score >= self.PASS_THRESHOLD_PERCENT
        exam_status = "passed" if passed else "failed"
        stored_weak = getattr(roadmap, "weak_topics", None) or weak_topics_list

        return RoadmapExamAttemptResponse(
            attempt_id=attempt.id,
            quiz_id=quiz.id,
            roadmap_id=roadmap.id,
            score=round(attempt.score, 1),
            passed=passed,
            pass_threshold=self.PASS_THRESHOLD_PERCENT,
            total_questions=len(quiz.questions or []),
            total_correct=attempt.total_correct,
            total_incorrect=attempt.total_incorrect,
            exam_status=exam_status,
            weak_topics=list(stored_weak),
            results=results,
            completed_at=attempt.completed_at or datetime.now(UTC),
        )

    async def get_roadmap_exam_state(
        self,
        roadmap_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str = "user",
    ) -> RoadmapExamStateResponse:
        """Returns the current Final Assessment state, active exam quiz, and latest attempt."""
        roadmap = await self.repo.get_roadmap_by_id(roadmap_id)
        if not roadmap:
            raise RoadmapNotFoundException(roadmap_id)
        if roadmap.user_id != user_id and user_role != "admin":
            raise RoadmapAccessForbiddenException(roadmap_id)

        exam_status = self._effective_exam_status(roadmap)
        quiz = await self.repo.get_latest_exam_quiz(roadmap_id)

        quiz_resp: QuizResponse | None = None
        latest_attempt_resp: RoadmapExamAttemptResponse | None = None

        if quiz is not None:
            quiz_resp = QuizResponse.model_validate(quiz)
            if quiz.attempts:
                sorted_attempts = sorted(
                    quiz.attempts,
                    key=lambda a: a.completed_at or datetime.min.replace(tzinfo=UTC),
                    reverse=True,
                )
                latest_attempt_resp = self._build_attempt_response(
                    roadmap, quiz, sorted_attempts[0]
                )

        return RoadmapExamStateResponse(
            roadmap_id=roadmap.id,
            exam_status=exam_status,
            latest_exam_score=getattr(roadmap, "latest_exam_score", None),
            weak_topics=list(getattr(roadmap, "weak_topics", None) or []),
            quiz=quiz_resp,
            latest_attempt=latest_attempt_resp,
        )

    async def generate_roadmap_exam(
        self,
        roadmap_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str = "user",
    ) -> QuizResponse:
        """Synthesizes a comprehensive Final Assessment across all documents of the roadmap's subject."""
        roadmap = await self.repo.get_roadmap_by_id(roadmap_id)
        if not roadmap:
            raise RoadmapNotFoundException(roadmap_id)
        if roadmap.user_id != user_id and user_role != "admin":
            raise RoadmapAccessForbiddenException(roadmap_id)

        if roadmap.progress_percentage < 100.0 and roadmap.status != "completed":
            raise RoadmapExamLockedException(roadmap.id, roadmap.progress_percentage)

        # If an unattempted exam already exists for this roadmap, return it directly
        existing_quiz = await self.repo.get_latest_exam_quiz(roadmap_id)
        if existing_quiz is not None and not existing_quiz.attempts:
            if getattr(roadmap, "exam_status", "locked") == "locked":
                roadmap.exam_status = "ready"
                await self.repo.session.flush()
            return QuizResponse.model_validate(existing_quiz)

        sources = await self._resolve_subject_source_documents(
            user_id=roadmap.user_id,
            subject_id=roadmap.subject_id,
            explicit_document_id=None,
            fallback_title=roadmap.title,
        )
        doc_title_by_id = {s.document_id: s.title for s in sources}
        default_source = sources[0]

        # Count topics in the roadmap to size the exam between 10 and 20 questions
        all_nodes = list(roadmap.nodes or [])
        root_ids = {n.id for n in all_nodes if n.parent_node_id is None}
        topic_nodes = [n for n in all_nodes if n.parent_node_id in root_ids]
        topic_count = max(1, len(topic_nodes) or len(root_ids) or 5)
        num_questions = min(20, max(10, topic_count * 2))
        time_limit_minutes = max(12, int(round(num_questions * 1.2)))

        # Build multi-document context blocks across all subject documents
        context_blocks: list[str] = []
        max_chars_per_doc = max(3000, 15000 // max(1, len(sources)))

        for src in sources:
            pages_dir = src.doc_dir / "pages"
            doc_chars = 0
            if pages_dir.is_dir():
                for p in range(1, src.total_pages + 1):
                    if doc_chars >= max_chars_per_doc:
                        break
                    page_file = pages_dir / f"page_{p}.md"
                    if not page_file.is_file():
                        continue
                    try:
                        txt = page_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        txt = ""
                    if txt:
                        snippet = txt[:1500]
                        doc_chars += len(snippet)
                        context_blocks.append(
                            f"=== TÀI LIỆU: {src.title} | DOCUMENT_ID: {src.document_id} | TRANG {p} ===\n"
                            f"{snippet}\n"
                            f"=== KẾT THÚC TRANG {p} (DOCUMENT_ID: {src.document_id}) ==="
                        )
            elif (src.doc_dir / "full_document.md").is_file():
                try:
                    full_txt = (
                        (src.doc_dir / "full_document.md")
                        .read_text(encoding="utf-8")[:max_chars_per_doc]
                        .strip()
                    )
                    if full_txt:
                        context_blocks.append(
                            f"=== TÀI LIỆU: {src.title} | DOCUMENT_ID: {src.document_id} | TRANG 1 ===\n"
                            f"{full_txt}\n"
                            f"=== KẾT THÚC TRANG 1 (DOCUMENT_ID: {src.document_id}) ==="
                        )
                except Exception:
                    pass

        joined_context = "\n\n".join(context_blocks) or (
            f"=== TÀI LIỆU: {default_source.title} | DOCUMENT_ID: {default_source.document_id} | TRANG 1 ===\n"
            f"Nội dung tổng hợp lộ trình {roadmap.title}\n"
            f"=== KẾT THÚC TRANG 1 ==="
        )

        weak_topics = list(getattr(roadmap, "weak_topics", None) or [])
        iteration = getattr(roadmap, "iteration", 1) or 1
        dist = compute_bloom_distribution(num_questions)

        remediation_focus_prompt = ""
        if iteration > 1 and weak_topics:
            remediation_focus_prompt = (
                f"\nLƯU Ý ĐẶC BIỆT (LỘ TRÌNH HỌC LẠI LẦN #{iteration}):\n"
                f"- Hãy phân bổ khoảng 60%-70% số câu hỏi tập trung kiểm tra sâu vào các chủ đề từng bị trượt: {', '.join(weak_topics)}.\n"
                f"- 30%-40% số câu hỏi còn lại kiểm tra tổng hợp các chương khác của môn học.\n"
            )

        doc_Catalog = "\n".join(
            f"- document_id: {s.document_id} | title: {s.title} ({s.total_pages} trang)"
            for s in sources
        )

        user_prompt = (
            f"Hãy tạo đề kiểm tra tổng kết môn học (Final Assessment) gồm chính xác {num_questions} câu hỏi trắc nghiệm "
            f"tổng hợp từ TOÀN BỘ {len(sources)} tài liệu thuộc lộ trình '{roadmap.title}'.\n\n"
            f"Danh sách tài liệu của môn học:\n{doc_Catalog}\n\n"
            f"Phân bổ cấp độ nhận thức Bloom:\n"
            f"- Remember: {dist['remember']} câu\n"
            f"- Understand: {dist['understand']} câu\n"
            f"- Apply: {dist['apply']} câu\n"
            f"{remediation_focus_prompt}"
            f"YÊU CẦU BẮT BUỘC VỀ TRÍCH DẪN ĐA TÀI LIỆU:\n"
            f"- Với mỗi câu hỏi, BẮT BUỘC điền đúng `source_document_id` (UUID của tài liệu nguồn), "
            f"`source_document_title` (tên tài liệu nguồn), và `target_page` (số trang chính xác nơi chứa kiến thức đó).\n\n"
            f"--- NỘI DUNG TÀI LIỆU MÔN HỌC ---\n"
            f"{joined_context}\n"
            f"--- HẾT NỘI DUNG TÀI LIỆU ---"
        )

        parsed_payload: GeneratedQuizPayload | None = None

        if settings.GEMINI_API_KEY:
            candidate_models = [
                settings.GEMINI_MODEL,
                "gemini-3.1-flash-lite",
                "gemini-3-flash-preview",
            ]
            unique_models = list(dict.fromkeys([m for m in candidate_models if m]))
            client = self.extractor.client
            last_error: Exception | None = None

            for model_name in unique_models:
                try:
                    response = await client.aio.models.generate_content(
                        model=model_name,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=QUIZ_GENERATOR_SYSTEM_PROMPT,
                            response_mime_type="application/json",
                            response_schema=GeneratedQuizPayload,
                            temperature=0.3,
                        ),
                    )
                    if response:
                        candidate = getattr(response, "parsed", None)
                        if not isinstance(candidate, GeneratedQuizPayload):
                            raw_text = getattr(response, "text", None) or ""
                            candidate = GeneratedQuizPayload.model_validate_json(
                                raw_text
                            )
                        parsed_payload = candidate
                        break
                except Exception as exc:
                    last_error = exc
                    if "503" in str(exc) or "UNAVAILABLE" in str(exc):
                        continue
                    logger.warning("Gemini exam generation error on %s: %s", model_name, exc)
                    break

            if parsed_payload is None and last_error is not None:
                logger.warning(
                    "Falling back to deterministic multi-document exam generator after error: %s",
                    last_error,
                )

        if parsed_payload is None or not parsed_payload.questions:
            parsed_payload = self._build_fallback_exam_payload(
                roadmap=roadmap,
                sources=sources,
                topic_nodes=topic_nodes,
                num_questions=num_questions,
            )

        quiz = Quiz(
            id=uuid.uuid4(),
            user_id=roadmap.user_id,
            document_id=uuid.UUID(default_source.document_id),
            subject_id=roadmap.subject_id,
            roadmap_id=roadmap.id,
            title=f"Final Assessment: {roadmap.title}",
            is_interleaved=True,
            total_questions=len(parsed_payload.questions),
            time_limit_minutes=time_limit_minutes,
            created_at=datetime.now(UTC),
        )
        self.repo.session.add(quiz)
        await self.repo.session.flush()

        valid_doc_uuids = {s.document_id: uuid.UUID(s.document_id) for s in sources}
        persisted_questions: list[QuizQuestion] = []

        for idx, q in enumerate(parsed_payload.questions):
            src_source = sources[idx % len(sources)]
            raw_doc_id = (q.source_document_id or "").strip()
            resolved_doc_uuid = valid_doc_uuids.get(
                raw_doc_id, uuid.UUID(src_source.document_id)
            )
            resolved_doc_title = doc_title_by_id.get(
                str(resolved_doc_uuid), src_source.title
            )
            bloom_val = (
                q.bloom_level.value
                if hasattr(q.bloom_level, "value")
                else str(q.bloom_level)
            )
            options_json = [
                opt.model_dump() if hasattr(opt, "model_dump") else dict(opt)
                for opt in q.options
            ]
            question_db = QuizQuestion(
                id=uuid.uuid4(),
                quiz_id=quiz.id,
                question_text=q.question_text,
                bloom_level=bloom_val,
                options=options_json,
                correct_option=q.correct_option,
                explanation=q.explanation,
                target_page=max(1, q.target_page or 1),
                topic_tag=q.topic_tag or "Core Concept",
                source_document_id=resolved_doc_uuid,
                source_document_title=resolved_doc_title,
            )
            self.repo.session.add(question_db)
            persisted_questions.append(question_db)

        if getattr(roadmap, "exam_status", "locked") == "locked":
            roadmap.exam_status = "ready"

        await self.repo.session.flush()
        return QuizResponse(
            id=quiz.id,
            user_id=quiz.user_id,
            document_id=quiz.document_id,
            subject_id=quiz.subject_id,
            roadmap_id=quiz.roadmap_id,
            title=quiz.title,
            is_interleaved=quiz.is_interleaved,
            total_questions=quiz.total_questions,
            time_limit_minutes=quiz.time_limit_minutes,
            created_at=quiz.created_at,
            questions=[
                QuizQuestionResponse.model_validate(q) for q in persisted_questions
            ],
        )

    def _build_fallback_exam_payload(
        self,
        roadmap: Roadmap,
        sources: list[SourceDocumentInput],
        topic_nodes: list[RoadmapNode],
        num_questions: int,
    ) -> GeneratedQuizPayload:
        """Generates a deterministic multi-document exam when Gemini API is unavailable."""
        questions: list[GeneratedQuestionItem] = []
        bloom_cycle = [BloomLevel.REMEMBER, BloomLevel.UNDERSTAND, BloomLevel.APPLY]
        weak_list = list(getattr(roadmap, "weak_topics", None) or [])

        for i in range(num_questions):
            src = sources[i % len(sources)]
            topic_node = (
                topic_nodes[i % len(topic_nodes)] if topic_nodes else None
            )
            topic_label = (
                weak_list[i % len(weak_list)]
                if weak_list and i < (num_questions * 2) // 3
                else (topic_node.title if topic_node else f"Topic #{i + 1}")
            )
            page_num = (
                topic_node.target_page_start
                if topic_node and topic_node.target_page_start
                else ((i % max(1, src.total_pages)) + 1)
            )
            questions.append(
                GeneratedQuestionItem(
                    question_text=(
                        f"[{src.title}] Câu hỏi đánh giá tổng kết #{i + 1} về chủ đề '{topic_label}': "
                        f"Phát biểu nào sau đây phản ánh chính xác nhất nội dung trọng tâm tại trang {page_num}?"
                    ),
                    bloom_level=bloom_cycle[i % len(bloom_cycle)],
                    options=[
                        QuizOptionItem(
                            key="A",
                            text=f"Nắm vững định nghĩa, nguyên lý và công thức cốt lõi của {topic_label}",
                        ),
                        QuizOptionItem(
                            key="B",
                            text=f"Bỏ qua các điều kiện biên khi áp dụng {topic_label}",
                        ),
                        QuizOptionItem(
                            key="C",
                            text=f"Chỉ áp dụng {topic_label} cho trường hợp suy biến",
                        ),
                        QuizOptionItem(
                            key="D",
                            text=f"Thay thế hoàn toàn {topic_label} bằng giả thiết ngẫu nhiên",
                        ),
                    ],
                    correct_option="A",
                    explanation=(
                        f"Theo tài liệu '{src.title}' (Trang {page_num}), việc nắm vững nguyên lý và điều kiện áp dụng của '{topic_label}' là bắt buộc."
                    ),
                    target_page=page_num,
                    topic_tag=topic_label[:95],
                    source_document_id=src.document_id,
                    source_document_title=src.title,
                )
            )

        return GeneratedQuizPayload(
            title=f"Final Assessment: {roadmap.title}",
            questions=questions,
        )

    async def submit_roadmap_exam(
        self,
        roadmap_id: uuid.UUID,
        user_id: uuid.UUID,
        req: RoadmapExamSubmitRequest,
        user_role: str = "user",
    ) -> RoadmapExamAttemptResponse:
        """Grades a Roadmap Final Assessment submission and updates exam_status ('passed' >= 50%, else 'failed')."""
        roadmap = await self.repo.get_roadmap_by_id(roadmap_id)
        if not roadmap:
            raise RoadmapNotFoundException(roadmap_id)
        if roadmap.user_id != user_id and user_role != "admin":
            raise RoadmapAccessForbiddenException(roadmap_id)

        if roadmap.progress_percentage < 100.0 and roadmap.status != "completed":
            raise RoadmapExamLockedException(roadmap.id, roadmap.progress_percentage)

        quiz = await self.repo.get_latest_exam_quiz(roadmap_id)
        if not quiz or not quiz.questions:
            raise QuizNotFoundError(roadmap_id)

        submitted_map = {
            ans.question_id: ans.selected_option.strip().upper()
            for ans in req.answers
            if ans.selected_option
        }

        total_questions = len(quiz.questions)
        total_correct = 0
        weak_topics: list[str] = []
        now = datetime.now(UTC)

        attempt = QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=user_id,
            score=0.0,
            total_correct=0,
            total_incorrect=0,
            started_at=now,
            completed_at=now,
        )
        self.repo.session.add(attempt)
        await self.repo.session.flush()

        attempt_answers: list[QuizAttemptAnswer] = []
        for q in quiz.questions:
            selected = submitted_map.get(q.id, "")
            is_correct = bool(selected) and selected == q.correct_option.strip().upper()
            if is_correct:
                total_correct += 1
            else:
                tag = (q.topic_tag or "Core Concept").strip()
                if tag and tag not in weak_topics:
                    weak_topics.append(tag)

            ans_record = QuizAttemptAnswer(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                question_id=q.id,
                selected_option=(selected or "-"),
                is_correct=is_correct,
            )
            self.repo.session.add(ans_record)
            attempt_answers.append(ans_record)

        total_incorrect = total_questions - total_correct
        score = (
            round((total_correct / total_questions) * 100.0, 1)
            if total_questions > 0
            else 0.0
        )
        passed = score >= self.PASS_THRESHOLD_PERCENT

        attempt.score = score
        attempt.total_correct = total_correct
        attempt.total_incorrect = total_incorrect

        roadmap.latest_exam_score = score
        roadmap.exam_status = "passed" if passed else "failed"
        roadmap.weak_topics = weak_topics if not passed else []

        await self.repo.session.flush()

        return self._build_attempt_response(
            roadmap, quiz, attempt, answers_override=attempt_answers
        )

    async def initiate_remediation(
        self,
        roadmap_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str = "user",
    ) -> tuple[
        RoadmapTaskStatusResponse,
        RoadmapGenerateRequest,
        list[str],
        list[str],
        int,
    ]:
        """Archives a failed roadmap and initiates a longer, more detailed Adaptive Remediation Roadmap."""
        roadmap = await self.repo.get_roadmap_by_id(roadmap_id)
        if not roadmap:
            raise RoadmapNotFoundException(roadmap_id)
        if roadmap.user_id != user_id and user_role != "admin":
            raise RoadmapAccessForbiddenException(roadmap_id)

        current_exam_status = getattr(roadmap, "exam_status", "locked")
        if current_exam_status != "failed" or roadmap.status == "archived":
            raise RoadmapRemediationNotAllowedException(
                roadmap.id,
                "already_remediated" if roadmap.status == "archived" else current_exam_status,
            )

        quiz = await self.repo.get_latest_exam_quiz(roadmap_id)
        weak_topics = list(getattr(roadmap, "weak_topics", None) or [])
        incorrect_questions_summary: list[str] = []

        if quiz and quiz.attempts:
            sorted_attempts = sorted(
                quiz.attempts,
                key=lambda a: a.completed_at or datetime.min.replace(tzinfo=UTC),
                reverse=True,
            )
            latest_attempt = sorted_attempts[0]
            ans_map = {a.question_id: a for a in (latest_attempt.answers or [])}
            for q in quiz.questions or []:
                ans = ans_map.get(q.id)
                if not ans or not ans.is_correct:
                    if q.topic_tag and q.topic_tag not in weak_topics:
                        weak_topics.append(q.topic_tag)
                    doc_label = (
                        getattr(q, "source_document_title", None) or "Tài liệu môn học"
                    )
                    incorrect_questions_summary.append(
                        f"[{doc_label} - Trang {q.target_page or 1} - Chủ đề: {q.topic_tag}] Câu hỏi làm sai: {q.question_text}"
                    )

        if not weak_topics:
            weak_topics = ["Trọng tâm lý thuyết & Vận dụng chuyên sâu"]

        # Archive the old failed roadmap
        roadmap.status = "archived"

        new_iteration = (getattr(roadmap, "iteration", 1) or 1) + 1
        base_title = re.sub(r"\s*\(Adaptive Iteration #\d+\)$", "", roadmap.title).strip()
        new_title = f"{base_title} (Adaptive Iteration #{new_iteration})"

        # Extend deadline by +50% (at least 14 days from today, capped at 365 days)
        today = date.today()
        created_d = (
            roadmap.created_at.date()
            if isinstance(roadmap.created_at, datetime)
            else today
        )
        orig_days = (
            max(7, (roadmap.target_date - created_d).days)
            if roadmap.target_date
            else 14
        )
        extended_days = min(365, max(14, int(round(orig_days * 1.5))))
        new_target_date = today + timedelta(days=extended_days)

        new_roadmap = await self.repo.create_roadmap(
            user_id=roadmap.user_id,
            subject_id=roadmap.subject_id,
            title=new_title,
            target_date=new_target_date,
            available_hours_per_day=roadmap.available_hours_per_day,
            iteration=new_iteration,
            parent_roadmap_id=roadmap.id,
            weak_topics=weak_topics,
        )

        remediation_goal = (
            f"Học lại chuyên sâu (Iteration #{new_iteration}) tập trung khắc phục các lỗ hổng kiến thức: "
            f"{', '.join(weak_topics)}"
        )
        req = RoadmapGenerateRequest(
            subject_id=roadmap.subject_id,
            document_id=None,
            title=new_title,
            target_date=new_target_date,
            available_hours_per_day=roadmap.available_hours_per_day,
            study_goal=remediation_goal[:950],
        )

        task_id = str(uuid.uuid4())
        status_response = RoadmapTaskStatusResponse(
            task_id=task_id,
            roadmap_id=new_roadmap.id,
            status="processing",
            progress_percent=10,
            message=f"Đang tái cấu trúc lộ trình chuyên sâu (Lần #{new_iteration}) tập trung vào {len(weak_topics)} phần kiến thức yếu...",
        )
        self._task_cache[task_id] = status_response

        return (
            status_response,
            req,
            weak_topics,
            incorrect_questions_summary,
            new_iteration,
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
            elif n.parent_node_id in node_map:
                node_map[n.parent_node_id].children.append(current_resp)

        return roots
