import math
from dataclasses import dataclass, field
from datetime import date
from typing import ClassVar

from app.modules.roadmaps.exceptions import InvalidStudyGoalException
from app.modules.roadmaps.schemas import (
    RawChapterOutline,
    RawCurriculumOutline,
    RawStudyTopic,
)


@dataclass(frozen=True)
class AllocatedStudyBlock:
    """Domain Value Object representing a single scheduled Pomodoro study block."""

    title: str
    description: str
    target_page_start: int
    target_page_end: int
    estimated_minutes: int
    is_core: bool = True


@dataclass
class PlannedTopicNode:
    """Domain node representing Level 2 topic with planned study blocks."""

    title: str
    description: str
    target_page_start: int
    target_page_end: int
    is_core: bool
    blocks: list[AllocatedStudyBlock] = field(default_factory=list)


@dataclass
class PlannedChapterNode:
    """Domain node representing Level 1 chapter with planned topics."""

    title: str
    description: str
    target_page_start: int
    target_page_end: int
    topics: list[PlannedTopicNode] = field(default_factory=list)


class StudyBlockPacingCalculator:
    """Pure domain calculator for constraint allocation, pacing, and pruning."""

    POMODORO_BLOCK_MINUTES: int = 25
    MINUTES_PER_PAGE_BY_COMPLEXITY: ClassVar[dict[int, int]] = {1: 5, 2: 7, 3: 10}

    def calculate_available_minutes(
        self, target_date: date, today: date, hours_per_day: float
    ) -> int:
        """Computes total available study minutes between today and target date."""
        if target_date <= today:
            raise InvalidStudyGoalException("target_date must be in the future.")

        total_days = (target_date - today).days
        return int(total_days * hours_per_day * 60)

    def allocate(
        self,
        curriculum: RawCurriculumOutline,
        target_date: date,
        today: date,
        hours_per_day: float,
    ) -> list[PlannedChapterNode]:
        """Calculates optimal pacing and prunes secondary content if constrained."""
        available_minutes = self.calculate_available_minutes(
            target_date, today, hours_per_day
        )
        total_baseline = self._sum_curriculum_baseline(curriculum)
        allow_secondary = total_baseline <= available_minutes

        planned_chapters: list[PlannedChapterNode] = []
        for chapter in curriculum.chapters:
            planned_chapter = self._process_chapter(chapter, allow_secondary)
            if planned_chapter.topics:
                planned_chapters.append(planned_chapter)

        return planned_chapters

    def _process_chapter(
        self, chapter: RawChapterOutline, allow_secondary: bool
    ) -> PlannedChapterNode:
        """Processes and filters topics inside a chapter."""
        planned_topics: list[PlannedTopicNode] = []
        for topic in chapter.topics:
            if not allow_secondary and not topic.is_core:
                continue

            blocks = self._slice_into_study_blocks(topic)
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
        self, topic: RawStudyTopic
    ) -> list[AllocatedStudyBlock]:
        """Slices a topic's pages into discrete 25-minute Pomodoro study blocks."""
        start = min(topic.target_page_start, topic.target_page_end)
        end = max(topic.target_page_start, topic.target_page_end)
        page_count = max(1, end - start + 1)
        mins_per_page = self.MINUTES_PER_PAGE_BY_COMPLEXITY.get(
            topic.complexity_level, 7
        )
        total_estimated = page_count * mins_per_page
        block_count = max(1, math.ceil(total_estimated / self.POMODORO_BLOCK_MINUTES))

        if block_count == 1:
            return [
                AllocatedStudyBlock(
                    title=f"Học lý thuyết: {topic.title}",
                    description=topic.description or "",
                    target_page_start=start,
                    target_page_end=end,
                    estimated_minutes=max(15, min(30, total_estimated)),
                    is_core=topic.is_core,
                )
            ]

        return self._create_multi_blocks(topic, start, end, page_count, block_count)

    def _create_multi_blocks(
        self,
        topic: RawStudyTopic,
        start: int,
        end: int,
        page_count: int,
        block_count: int,
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
                        estimated_minutes=self.POMODORO_BLOCK_MINUTES,
                        is_core=topic.is_core,
                    )
                )
                current_page = end_page + 1
        else:
            # Dense material where multiple Pomodoro blocks cover the same pages
            for index in range(1, block_count + 1):
                blocks.append(
                    AllocatedStudyBlock(
                        title=f"{topic.title} (Phần {index}/{block_count})",
                        description=f"Nghiên cứu chuyên sâu từ trang {start} đến {end}",
                        target_page_start=start,
                        target_page_end=end,
                        estimated_minutes=self.POMODORO_BLOCK_MINUTES,
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
