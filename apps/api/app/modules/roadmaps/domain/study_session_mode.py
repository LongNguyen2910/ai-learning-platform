from enum import Enum


class StudySessionMode(str, Enum):
    """Study session duration mode for FR-13 block allocation."""

    AUTO = "auto"
    MICRO = "micro"
    DEEP_WORK = "deep_work"


MICRO_TARGET_MINUTES: int = 25
MICRO_MIN_MINUTES: int = 15
MICRO_MAX_MINUTES: int = 30

DEEP_WORK_TARGET_MINUTES: int = 50
DEEP_WORK_MIN_MINUTES: int = 45
DEEP_WORK_MAX_MINUTES: int = 90


def resolve_block_duration_bounds(
    mode: StudySessionMode,
    complexity_level: int,
    available_hours_per_day: float,
) -> tuple[int, int, int]:
    """Resolves (target_minutes, min_minutes, max_minutes) by mode and constraints."""
    if mode == StudySessionMode.MICRO:
        return MICRO_TARGET_MINUTES, MICRO_MIN_MINUTES, MICRO_MAX_MINUTES

    if mode == StudySessionMode.DEEP_WORK:
        return DEEP_WORK_TARGET_MINUTES, DEEP_WORK_MIN_MINUTES, DEEP_WORK_MAX_MINUTES

    # AUTO mode: heavy topic + ample daily time -> Deep Work; else Micro
    if complexity_level >= 3 and available_hours_per_day >= 1.5:
        return DEEP_WORK_TARGET_MINUTES, DEEP_WORK_MIN_MINUTES, DEEP_WORK_MAX_MINUTES

    return MICRO_TARGET_MINUTES, MICRO_MIN_MINUTES, MICRO_MAX_MINUTES
