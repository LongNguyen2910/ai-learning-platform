import math
from datetime import date, datetime
from typing import ClassVar

from app.modules.roadmaps.domain.entities import (
    AllocatedStudyBlock,
    PlannedChapterNode,
    PlannedTopicNode,
)
from app.modules.roadmaps.domain.study_session_mode import (
    StudySessionMode,
    resolve_block_duration_bounds,
)
from app.modules.roadmaps.exceptions import InvalidStudyGoalException
from app.modules.roadmaps.schemas import (
    RawChapterOutline,
    RawCurriculumOutline,
    RawStudyTopic,
)


class StudyBlockPacingCalculator:
    """Pure domain calculator for constraint allocation, pacing, and study block slicing."""

    POMODORO_BLOCK_MINUTES: int = 25
    MINUTES_PER_PAGE_BY_COMPLEXITY: ClassVar[dict[int, int]] = {1: 5, 2: 7, 3: 10}
    MAX_STUDY_HORIZON_DAYS: int = 366
    MIN_STUDY_HOURS_PER_DAY: float = 0.5
    MAX_STUDY_HOURS_PER_DAY: float = 12.0

    def calculate_available_minutes(
        self, target_date: date, today: date, hours_per_day: float
    ) -> int:
        """Computes total available study minutes between today and target date."""
        target_d = target_date.date() if isinstance(target_date, datetime) else target_date
        today_d = today.date() if isinstance(today, datetime) else today

        if target_d <= today_d:
            raise InvalidStudyGoalException("target_date must be in the future.")

        total_days = (target_d - today_d).days
        if total_days > self.MAX_STUDY_HORIZON_DAYS:
            raise InvalidStudyGoalException(
                f"target_date cannot exceed {self.MAX_STUDY_HORIZON_DAYS} days in the future (got {total_days} days)."
            )

        if not (self.MIN_STUDY_HOURS_PER_DAY <= hours_per_day <= self.MAX_STUDY_HOURS_PER_DAY):
            raise InvalidStudyGoalException(
                f"available_hours_per_day must be between {self.MIN_STUDY_HOURS_PER_DAY} and {self.MAX_STUDY_HOURS_PER_DAY}."
            )

        return int(total_days * hours_per_day * 60)

    def allocate(
        self,
        curriculum: RawCurriculumOutline,
        target_date: date,
        today: date,
        hours_per_day: float,
        session_mode: StudySessionMode = StudySessionMode.AUTO,
    ) -> list[PlannedChapterNode]:
        """Calculates pacing, prunes secondary content if constrained, and slices blocks."""
        if not curriculum.chapters:
            raise InvalidStudyGoalException("Curriculum must contain at least one chapter.")

        available_minutes = self.calculate_available_minutes(
            target_date, today, hours_per_day
        )
        total_baseline = self._sum_curriculum_baseline(curriculum)
        allow_secondary = total_baseline <= available_minutes

        planned_chapters: list[PlannedChapterNode] = []
        for chapter in curriculum.chapters:
            planned_chapter = self._process_chapter(
                chapter, allow_secondary, session_mode, hours_per_day
            )
            if planned_chapter.topics:
                planned_chapters.append(planned_chapter)

        if not planned_chapters:
            raise InvalidStudyGoalException("No study topics available for the given time constraint.")

        return planned_chapters

    def _process_chapter(
        self,
        chapter: RawChapterOutline,
        allow_secondary: bool,
        session_mode: StudySessionMode,
        hours_per_day: float,
    ) -> PlannedChapterNode:
        """Processes and filters topics inside a chapter."""
        planned_topics: list[PlannedTopicNode] = []
        for topic in chapter.topics:
            if not allow_secondary and not topic.is_core:
                continue

            blocks = self._slice_into_study_blocks(topic, session_mode, hours_per_day)
            planned_topics.append(
                PlannedTopicNode(
                    title=topic.title,
                    description=topic.description or "",
                    target_page_start=topic.target_page_start,
                    target_page_end=topic.target_page_end,
                    is_core=topic.is_core,
                    blocks=blocks,
                )
            )

        return PlannedChapterNode(
            title=chapter.title,
            description=chapter.description or "",
            target_page_start=chapter.target_page_start,
            target_page_end=chapter.target_page_end,
            topics=planned_topics,
        )

    def _slice_into_study_blocks(
        self,
        topic: RawStudyTopic,
        session_mode: StudySessionMode = StudySessionMode.MICRO,
        hours_per_day: float = 2.0,
    ) -> list[AllocatedStudyBlock]:
        """Slices topic pages into 15-30m or 45-90m blocks based on mode and constraints."""
        start = min(topic.target_page_start, topic.target_page_end)
        end = max(topic.target_page_start, topic.target_page_end)
        page_count = max(1, end - start + 1)
        mins_per_page = self.MINUTES_PER_PAGE_BY_COMPLEXITY.get(
            topic.complexity_level, 7
        )
        total_estimated = page_count * mins_per_page

        target_mins, min_mins, max_mins = resolve_block_duration_bounds(
            session_mode, topic.complexity_level, hours_per_day
        )
        block_count = max(1, math.ceil(total_estimated / target_mins))

        if block_count == 1:
            return [
                AllocatedStudyBlock(
                    title=f"Học lý thuyết: {topic.title}",
                    description=topic.description or "",
                    target_page_start=start,
                    target_page_end=end,
                    estimated_minutes=max(min_mins, min(max_mins, total_estimated)),
                    is_core=topic.is_core,
                )
            ]

        return self._create_multi_blocks(
            topic, start, end, page_count, block_count, target_mins
        )

    def _create_multi_blocks(
        self,
        topic: RawStudyTopic,
        start: int,
        end: int,
        page_count: int,
        block_count: int,
        target_mins: int,
    ) -> list[AllocatedStudyBlock]:
        """Divides multi-block topics across sequential page segments without truncation."""
        blocks: list[AllocatedStudyBlock] = []

        if page_count >= block_count:
            base_size = page_count // block_count
            remainder = page_count % block_count
            current_page = start

            for index in range(1, block_count + 1):
                chunk_size = base_size + (1 if index <= remainder else 0)
                end_page = current_page + chunk_size - 1
                blocks.append(
                    AllocatedStudyBlock(
                        title=f"{topic.title} (Phần {index}/{block_count})",
                        description=f"Nội dung từ trang {current_page} đến {end_page}",
                        target_page_start=current_page,
                        target_page_end=end_page,
                        estimated_minutes=target_mins,
                        is_core=topic.is_core,
                    )
                )
                current_page = end_page + 1
        else:
            # Dense material where multiple blocks cover the same pages
            for index in range(1, block_count + 1):
                blocks.append(
                    AllocatedStudyBlock(
                        title=f"{topic.title} (Phần {index}/{block_count})",
                        description=f"Nghiên cứu chuyên sâu từ trang {start} đến {end}",
                        target_page_start=start,
                        target_page_end=end,
                        estimated_minutes=target_mins,
                        is_core=topic.is_core,
                    )
                )

        return blocks

    def _sum_curriculum_baseline(self, curriculum: RawCurriculumOutline) -> int:
        """Calculates total minutes needed for all topics at baseline velocity."""
        total = 0
        for chapter in curriculum.chapters:
            for topic in chapter.topics:
                pages = max(1, topic.target_page_end - topic.target_page_start + 1)
                rate = self.MINUTES_PER_PAGE_BY_COMPLEXITY.get(
                    topic.complexity_level, 7
                )
                total += pages * rate
        return total
