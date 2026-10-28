"""Compatibility re-export layer for StudyBlockPacingCalculator and Domain Entities."""

from app.modules.roadmaps.domain import (
    DEEP_WORK_MAX_MINUTES,
    DEEP_WORK_MIN_MINUTES,
    DEEP_WORK_TARGET_MINUTES,
    MICRO_MAX_MINUTES,
    MICRO_MIN_MINUTES,
    MICRO_TARGET_MINUTES,
    AllocatedStudyBlock,
    PlannedChapterNode,
    PlannedTopicNode,
    StudyBlockPacingCalculator,
    StudySessionMode,
    resolve_block_duration_bounds,
)

__all__ = [
    "DEEP_WORK_MAX_MINUTES",
    "DEEP_WORK_MIN_MINUTES",
    "DEEP_WORK_TARGET_MINUTES",
    "MICRO_MAX_MINUTES",
    "MICRO_MIN_MINUTES",
    "MICRO_TARGET_MINUTES",
    "AllocatedStudyBlock",
    "PlannedChapterNode",
    "PlannedTopicNode",
    "StudyBlockPacingCalculator",
    "StudySessionMode",
    "resolve_block_duration_bounds",
]
