import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.modules.roadmaps.exceptions import (
    NodeLockedException,
    NodeNotFoundException,
    NodeNotLeafException,
    PrerequisiteNotCompletedException,
)
from app.modules.roadmaps.models import RoadmapNode


@dataclass
class ProgressionUpdateResult:
    """Domain result holding mutated node IDs, progress and status."""

    completed_node_ids: list[uuid.UUID] = field(default_factory=list)
    unlocked_node_ids: list[uuid.UUID] = field(default_factory=list)
    progress_percentage: float = 0.0
    roadmap_status: str = "active"


class NodeProgressionCalculator:
    """Domain logic for linear cascade unlocking and roadmap progress calculation (FR-14)."""

    def calculate_completion(
        self,
        nodes: list[RoadmapNode],
        target_node_id: uuid.UUID,
        now: datetime | None = None,
    ) -> ProgressionUpdateResult:
        current_time = now or datetime.now(UTC)
        node_map = {n.id: n for n in nodes}
        target_node = node_map.get(target_node_id)
        if not target_node:
            raise NodeNotFoundException(target_node_id)

        parent_ids = {n.parent_node_id for n in nodes if n.parent_node_id is not None}
        if target_node.parent_node_id is None or target_node.id in parent_ids:
            raise NodeNotLeafException(target_node_id)

        if not target_node.is_unlocked:
            raise NodeLockedException(target_node_id)

        leaf_nodes = sorted(
            [n for n in nodes if n.id not in parent_ids],
            key=lambda x: x.order_index,
        )

        if target_node.is_completed:
            progress = self._calc_progress(leaf_nodes)
            status = "completed" if progress >= 100.0 else "active"
            return ProgressionUpdateResult(
                completed_node_ids=[target_node.id],
                unlocked_node_ids=[],
                progress_percentage=progress,
                roadmap_status=status,
            )

        for leaf in leaf_nodes:
            if leaf.order_index < target_node.order_index and not leaf.is_completed:
                raise PrerequisiteNotCompletedException(target_node.id, leaf.id)

        target_node.is_completed = True
        target_node.completed_at = current_time
        completed_ids = [target_node.id]

        parent_completed_ids = self._cascade_parents(node_map, target_node, current_time)
        completed_ids.extend(parent_completed_ids)

        unlocked_ids = self._unlock_next_leaf(leaf_nodes, target_node)

        progress = self._calc_progress(leaf_nodes)
        status = "completed" if progress >= 100.0 else "active"

        return ProgressionUpdateResult(
            completed_node_ids=completed_ids,
            unlocked_node_ids=unlocked_ids,
            progress_percentage=progress,
            roadmap_status=status,
        )

    def _cascade_parents(
        self,
        node_map: dict[uuid.UUID, RoadmapNode],
        target_node: RoadmapNode,
        now: datetime,
    ) -> list[uuid.UUID]:
        completed_parent_ids: list[uuid.UUID] = []
        curr_parent_id = target_node.parent_node_id

        while curr_parent_id:
            parent_node = node_map.get(curr_parent_id)
            if not parent_node:
                break

            children = [n for n in node_map.values() if n.parent_node_id == curr_parent_id]
            if not all(c.is_completed for c in children):
                break

            if not parent_node.is_completed:
                parent_node.is_completed = True
                parent_node.completed_at = now
                completed_parent_ids.append(parent_node.id)

            curr_parent_id = parent_node.parent_node_id

        return completed_parent_ids

    def _unlock_next_leaf(
        self,
        leaf_nodes: list[RoadmapNode],
        target_node: RoadmapNode,
    ) -> list[uuid.UUID]:
        next_leaf = next(
            (
                n
                for n in leaf_nodes
                if n.order_index > target_node.order_index and not n.is_unlocked
            ),
            None,
        )
        if not next_leaf:
            return []

        next_leaf.is_unlocked = True
        return [next_leaf.id]

    def _calc_progress(self, leaf_nodes: list[RoadmapNode]) -> float:
        total_minutes = sum(n.estimated_minutes for n in leaf_nodes)
        if total_minutes <= 0:
            all_done = all(n.is_completed for n in leaf_nodes)
            return 100.0 if all_done and leaf_nodes else 0.0

        done_minutes = sum(n.estimated_minutes for n in leaf_nodes if n.is_completed)
        return round((done_minutes / total_minutes) * 100, 2)
