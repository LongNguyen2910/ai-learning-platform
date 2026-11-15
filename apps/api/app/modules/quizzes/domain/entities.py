from dataclasses import dataclass, field
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


class GapSeverity(StrEnum):
    CRITICAL_FOUNDATION = "critical_foundation"
    APPLICATION_PRACTICE = "application_practice"


@dataclass(frozen=True)
class BloomTaxonomyBreakdown:
    remember_correct: int = 0
    remember_total: int = 0
    understand_correct: int = 0
    understand_total: int = 0
    apply_correct: int = 0
    apply_total: int = 0


@dataclass(frozen=True)
class TopicAnalysisItem:
    topic_tag: str
    is_gap: bool
    severity: GapSeverity | None
    total_questions: int
    correct_questions: int
    incorrect_questions: int
    bloom_matrix: BloomTaxonomyBreakdown
    incorrect_question_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentReviewRecommendation:
    document_id: str | None
    document_title: str
    pages: list[int]
    topics: list[str]


@dataclass(frozen=True)
class QuizAnalysisResult:
    score: float
    total_questions: int
    total_correct: int
    total_incorrect: int
    weak_topics: list[TopicAnalysisItem]
    mastered_topics: list[TopicAnalysisItem]
    review_recommendations: list[DocumentReviewRecommendation]
    bloom_summary: BloomTaxonomyBreakdown

