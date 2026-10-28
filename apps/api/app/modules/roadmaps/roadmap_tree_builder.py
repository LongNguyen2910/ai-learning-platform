import uuid
from dataclasses import dataclass

from app.modules.roadmaps.study_block_pacing_calculator import (
    AllocatedStudyBlock,
    PlannedChapterNode,
    PlannedTopicNode,
)


@dataclass
class UnpersistedNode:
    """Domain representation of a Roadmap Node before database persistence."""

    temp_id: uuid.UUID
    parent_temp_id: uuid.UUID | None
    title: str
    description: str | None
    order_index: int
    target_page_start: int | None
    target_page_end: int | None
    estimated_minutes: int
    is_unlocked: bool
    is_completed: bool = False
    document_id: uuid.UUID | None = None


class RoadmapTreeBuilder:
    """Builds a deterministic 3-tier roadmap tree with sequential unlocking."""

    def build_tree_nodes(
        self,
        planned_chapters: list[PlannedChapterNode],
        document_id: uuid.UUID | None = None,
    ) -> list[UnpersistedNode]:
        """Transforms planned domain chapters into flattened hierarchical node list."""
        if not planned_chapters:
            return []

        nodes: list[UnpersistedNode] = []
        global_order = 1
        first_leaf_unlocked = False

        for chapter in planned_chapters:
            chapter_id = uuid.uuid4()
            nodes.append(
                self._create_chapter_node(chapter, chapter_id, global_order, document_id)
            )
            global_order += 1

            for topic in chapter.topics:
                topic_id = uuid.uuid4()
                nodes.append(
                    self._create_topic_node(
                        topic, topic_id, chapter_id, global_order, document_id
                    )
                )
                global_order += 1

                for block in topic.blocks:
                    should_unlock = not first_leaf_unlocked
                    nodes.append(
                        self._create_block_node(
                            block, topic_id, global_order, should_unlock, document_id
                        )
                    )
                    first_leaf_unlocked = True
                    global_order += 1

        return nodes

    def _resolve_doc_uuid(
        self, node_doc_id: str | None, fallback_doc_id: uuid.UUID | None
    ) -> uuid.UUID | None:
        if node_doc_id:
            try:
                return uuid.UUID(str(node_doc_id))
            except ValueError:
                pass
        return fallback_doc_id

    def _create_chapter_node(
        self,
        chapter: PlannedChapterNode,
        chapter_id: uuid.UUID,
        order: int,
        document_id: uuid.UUID | None,
    ) -> UnpersistedNode:
        """Constructs a Level 1 Chapter node."""
        resolved_doc_id = self._resolve_doc_uuid(chapter.document_id, document_id)
        return UnpersistedNode(
            temp_id=chapter_id,
            parent_temp_id=None,
            title=chapter.title,
            description=chapter.description,
            order_index=order,
            target_page_start=chapter.target_page_start,
            target_page_end=chapter.target_page_end,
            estimated_minutes=0,
            is_unlocked=True,
            document_id=resolved_doc_id,
        )

    def _create_topic_node(
        self,
        topic: PlannedTopicNode,
        topic_id: uuid.UUID,
        parent_id: uuid.UUID,
        order: int,
        document_id: uuid.UUID | None,
    ) -> UnpersistedNode:
        """Constructs a Level 2 Topic node."""
        resolved_doc_id = self._resolve_doc_uuid(topic.document_id, document_id)
        return UnpersistedNode(
            temp_id=topic_id,
            parent_temp_id=parent_id,
            title=topic.title,
            description=topic.description,
            order_index=order,
            target_page_start=topic.target_page_start,
            target_page_end=topic.target_page_end,
            estimated_minutes=0,
            is_unlocked=True,
            document_id=resolved_doc_id,
        )

    def _create_block_node(
        self,
        block: AllocatedStudyBlock,
        parent_id: uuid.UUID,
        order: int,
        is_unlocked: bool,
        document_id: uuid.UUID | None,
    ) -> UnpersistedNode:
        """Constructs a Level 3 Leaf Study Block node."""
        resolved_doc_id = self._resolve_doc_uuid(block.document_id, document_id)
        return UnpersistedNode(
            temp_id=uuid.uuid4(),
            parent_temp_id=parent_id,
            title=block.title,
            description=block.description,
            order_index=order,
            target_page_start=block.target_page_start,
            target_page_end=block.target_page_end,
            estimated_minutes=block.estimated_minutes,
            is_unlocked=is_unlocked,
            document_id=resolved_doc_id,
        )
