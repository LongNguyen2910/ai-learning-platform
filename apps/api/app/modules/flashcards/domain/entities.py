from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class SM2ReviewResult:
    repetition_number: int
    easiness_factor: float
    interval_days: int
    due_date: date
