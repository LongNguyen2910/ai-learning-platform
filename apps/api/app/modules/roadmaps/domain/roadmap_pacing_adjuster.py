import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.modules.roadmaps.models import Roadmap, RoadmapNode


@dataclass(frozen=True)
class RoadmapAdjustmentResult:
    """Domain result for roadmap auto-pacing adjustment."""

    was_adjusted: bool
    original_target_date: date | None
    new_target_date: date | None
    days_extended: int
    remaining_minutes: int
    available_minutes: int
    new_status: str
    message: str | None = None


class RoadmapPacingAdjuster:
    """Pure domain calculator for detecting delays and auto-adjusting roadmap target date (FR-15)."""

    MAX_STUDY_HORIZON_DAYS: int = 366
    DEFAULT_HOURS_PER_DAY: float = 2.0

    def adjust_if_behind(
        self,
        roadmap: Roadmap,
        nodes: list[RoadmapNode],
        today: date | None = None,
    ) -> RoadmapAdjustmentResult:
        """Evaluates whether roadmap is behind schedule and computes extended target date if needed."""
        current_date = today or datetime.now(UTC).date()

        if roadmap.target_date is None or roadmap.status in ("completed", "archived"):
            return RoadmapAdjustmentResult(
                was_adjusted=False,
                original_target_date=roadmap.target_date,
                new_target_date=roadmap.target_date,
                days_extended=0,
                remaining_minutes=0,
                available_minutes=0,
                new_status=roadmap.status,
            )

        parent_ids = {n.parent_node_id for n in nodes if n.parent_node_id is not None}
        leaf_nodes = [n for n in nodes if n.id not in parent_ids]
        uncompleted_leaf_nodes = [n for n in leaf_nodes if not n.is_completed]
        remaining_minutes = sum(n.estimated_minutes for n in uncompleted_leaf_nodes)

        if not uncompleted_leaf_nodes or remaining_minutes <= 0:
            return RoadmapAdjustmentResult(
                was_adjusted=False,
                original_target_date=roadmap.target_date,
                new_target_date=roadmap.target_date,
                days_extended=0,
                remaining_minutes=0,
                available_minutes=0,
                new_status=roadmap.status,
            )

        hours_per_day = (
            roadmap.available_hours_per_day
            if roadmap.available_hours_per_day and roadmap.available_hours_per_day > 0
            else self.DEFAULT_HOURS_PER_DAY
        )
        daily_minutes = round(hours_per_day * 60)
        if daily_minutes <= 0:
            daily_minutes = int(self.DEFAULT_HOURS_PER_DAY * 60)

        days_to_target = (roadmap.target_date - current_date).days
        available_minutes = max(0, days_to_target * daily_minutes)

        is_behind = (roadmap.target_date <= current_date) or (
            remaining_minutes > available_minutes
        )

        if not is_behind:
            return RoadmapAdjustmentResult(
                was_adjusted=False,
                original_target_date=roadmap.target_date,
                new_target_date=roadmap.target_date,
                days_extended=0,
                remaining_minutes=remaining_minutes,
                available_minutes=available_minutes,
                new_status=roadmap.status,
            )

        days_needed = math.ceil(remaining_minutes / daily_minutes)
        if days_needed < 1:
            days_needed = 1

        new_target_date = current_date + timedelta(days=days_needed)

        if new_target_date <= roadmap.target_date:
            new_target_date = roadmap.target_date + timedelta(days=1)

        max_horizon_target = current_date + timedelta(days=self.MAX_STUDY_HORIZON_DAYS)
        if new_target_date > max_horizon_target:
            new_target_date = max_horizon_target

        days_extended = (new_target_date - roadmap.target_date).days
        if days_extended <= 0:
            return RoadmapAdjustmentResult(
                was_adjusted=False,
                original_target_date=roadmap.target_date,
                new_target_date=roadmap.target_date,
                days_extended=0,
                remaining_minutes=remaining_minutes,
                available_minutes=available_minutes,
                new_status=roadmap.status,
            )

        message = (
            f"Lộ trình đã tự động gia hạn thêm {days_extended} ngày (hạn chót mới: {new_target_date.isoformat()}) "
            f"để hoàn thành {remaining_minutes} phút học còn lại với nhịp độ {hours_per_day:.1f}h/ngày."
        )

        return RoadmapAdjustmentResult(
            was_adjusted=True,
            original_target_date=roadmap.target_date,
            new_target_date=new_target_date,
            days_extended=days_extended,
            remaining_minutes=remaining_minutes,
            available_minutes=available_minutes,
            new_status="active",
            message=message,
        )
