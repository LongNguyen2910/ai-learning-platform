from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class QuestionSource(StrEnum):
    NEW = "new"
    REVIEW = "review"


@dataclass(frozen=True)
class InterleavedQuestion(Generic[T]):
    question: T
    source: QuestionSource


@dataclass(frozen=True)
class InterleavingResult(Generic[T]):
    questions: list[InterleavedQuestion[T]]
    total_count: int
    new_count: int
    review_count: int
    is_interleaved: bool
