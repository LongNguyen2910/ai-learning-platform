from dataclasses import dataclass, field


@dataclass(frozen=True)
class AllocatedStudyBlock:
    """Domain Value Object representing single scheduled study block."""

    title: str
    description: str
    target_page_start: int
    target_page_end: int
    estimated_minutes: int
    is_core: bool = True
    document_id: str | None = None


@dataclass
class PlannedTopicNode:
    """Domain node representing Level 2 topic with planned study blocks."""

    title: str
    description: str
    target_page_start: int
    target_page_end: int
    is_core: bool
    document_id: str | None = None
    blocks: list[AllocatedStudyBlock] = field(default_factory=list)


@dataclass
class PlannedChapterNode:
    """Domain node representing Level 1 chapter with planned topics."""

    title: str
    description: str
    target_page_start: int
    target_page_end: int
    document_id: str | None = None
    topics: list[PlannedTopicNode] = field(default_factory=list)
