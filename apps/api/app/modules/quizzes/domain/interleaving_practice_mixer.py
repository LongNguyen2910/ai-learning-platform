import random
from collections.abc import Sequence
from typing import TypeVar

from app.modules.quizzes.domain.entities import (
    InterleavedQuestion,
    InterleavingResult,
    QuestionSource,
)
from app.modules.quizzes.exceptions import InsufficientQuestionsError

T = TypeVar("T")


class InterleavingPracticeMixer:
    """Domain service for mixing current and historical quiz questions (FR-20)."""

    TARGET_NEW_RATIO = 0.7

    @staticmethod
    def mix(
        new_questions: Sequence[T] | None,
        review_questions: Sequence[T] | None,
        total_questions: int,
        seed: int | None = None,
    ) -> InterleavingResult[T]:
        """Mixes new questions and review questions according to 70/30 interleaving rules.

        Args:
            new_questions: Questions from the current lesson.
            review_questions: Historical questions from previous lessons.
            total_questions: Total number of questions desired for the quiz.
            seed: Optional seed for reproducible randomization.

        Returns:
            InterleavingResult containing shuffled tagged questions and count stats.

        Raises:
            ValueError: If total_questions is not a positive integer.
            InsufficientQuestionsError: If total available questions < total_questions.
        """
        if (
            isinstance(total_questions, bool)
            or not isinstance(total_questions, int)
            or total_questions <= 0
        ):
            raise ValueError("total_questions must be a positive integer.")

        safe_new = list(new_questions or [])
        safe_review = list(review_questions or [])

        total_available = len(safe_new) + len(safe_review)
        if total_available < total_questions:
            raise InsufficientQuestionsError(
                f"Insufficient questions in pool: required {total_questions}, available {total_available}."
            )

        target_new = round(total_questions * InterleavingPracticeMixer.TARGET_NEW_RATIO)
        target_review = total_questions - target_new

        # Compensatory allocation when pools are asymmetric
        if len(safe_review) < target_review:
            actual_review = len(safe_review)
            actual_new = total_questions - actual_review
        elif len(safe_new) < target_new:
            actual_new = len(safe_new)
            actual_review = total_questions - actual_new
        else:
            actual_new = target_new
            actual_review = target_review

        rng = random.Random(seed)
        selected_new = rng.sample(safe_new, actual_new)
        selected_review = rng.sample(safe_review, actual_review)

        tagged: list[InterleavedQuestion[T]] = [
            InterleavedQuestion(question=q, source=QuestionSource.NEW)
            for q in selected_new
        ] + [
            InterleavedQuestion(question=q, source=QuestionSource.REVIEW)
            for q in selected_review
        ]

        rng.shuffle(tagged)

        # An interleaved practice quiz must contain both new and review questions
        is_interleaved = actual_new > 0 and actual_review > 0

        return InterleavingResult(
            questions=tagged,
            total_count=total_questions,
            new_count=actual_new,
            review_count=actual_review,
            is_interleaved=is_interleaved,
        )
