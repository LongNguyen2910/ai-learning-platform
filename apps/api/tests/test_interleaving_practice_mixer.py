import pytest

from app.modules.quizzes.domain.entities import QuestionSource
from app.modules.quizzes.domain.interleaving_practice_mixer import (
    InterleavingPracticeMixer,
)
from app.modules.quizzes.exceptions import InsufficientQuestionsError


def test_invalid_total_questions_raises_error():
    invalid_totals = [0, -1, True, False, 5.5, "10"]
    for bad_total in invalid_totals:
        with pytest.raises(ValueError, match="total_questions must be a positive integer"):
            InterleavingPracticeMixer.mix(
                new_questions=["Q1", "Q2"],
                review_questions=["Q3"],
                total_questions=bad_total,  # type: ignore[arg-type]
            )


def test_insufficient_total_pool_raises_insufficient_questions_error():
    with pytest.raises(InsufficientQuestionsError, match="Insufficient questions in pool"):
        InterleavingPracticeMixer.mix(
            new_questions=["N1", "N2"],
            review_questions=["R1"],
            total_questions=5,
        )


def test_standard_70_30_split():
    new_pool = [f"N{i}" for i in range(1, 15)]
    review_pool = [f"R{i}" for i in range(1, 15)]

    result = InterleavingPracticeMixer.mix(
        new_questions=new_pool,
        review_questions=review_pool,
        total_questions=10,
        seed=42,
    )

    assert result.total_count == 10
    assert result.new_count == 7
    assert result.review_count == 3
    assert result.is_interleaved is True

    new_items = [q for q in result.questions if q.source == QuestionSource.NEW]
    review_items = [q for q in result.questions if q.source == QuestionSource.REVIEW]
    assert len(new_items) == 7
    assert len(review_items) == 3


def test_zero_review_questions_fallback():
    new_pool = [f"N{i}" for i in range(1, 15)]
    review_pool: list[str] = []

    result = InterleavingPracticeMixer.mix(
        new_questions=new_pool,
        review_questions=review_pool,
        total_questions=10,
    )

    assert result.total_count == 10
    assert result.new_count == 10
    assert result.review_count == 0
    assert result.is_interleaved is False
    assert all(q.source == QuestionSource.NEW for q in result.questions)


def test_zero_new_questions_fallback():
    review_pool = [f"R{i}" for i in range(1, 15)]

    result = InterleavingPracticeMixer.mix(
        new_questions=[],
        review_questions=review_pool,
        total_questions=5,
    )

    assert result.total_count == 5
    assert result.new_count == 0
    assert result.review_count == 5
    assert result.is_interleaved is False
    assert all(q.source == QuestionSource.REVIEW for q in result.questions)


def test_none_input_handled_gracefully():
    review_pool = [f"R{i}" for i in range(1, 6)]

    result = InterleavingPracticeMixer.mix(
        new_questions=None,
        review_questions=review_pool,
        total_questions=3,
    )

    assert result.total_count == 3
    assert result.new_count == 0
    assert result.review_count == 3
    assert result.is_interleaved is False


def test_insufficient_review_questions_compensates():
    new_pool = [f"N{i}" for i in range(1, 15)]
    review_pool = ["R1"]  # Only 1 review question, target is 3

    result = InterleavingPracticeMixer.mix(
        new_questions=new_pool,
        review_questions=review_pool,
        total_questions=10,
    )

    assert result.total_count == 10
    assert result.new_count == 9
    assert result.review_count == 1
    assert result.is_interleaved is True


def test_insufficient_new_questions_compensates():
    new_pool = [f"N{i}" for i in range(1, 6)]  # Only 5 new questions, target is 7
    review_pool = [f"R{i}" for i in range(1, 10)]

    result = InterleavingPracticeMixer.mix(
        new_questions=new_pool,
        review_questions=review_pool,
        total_questions=10,
    )

    assert result.total_count == 10
    assert result.new_count == 5
    assert result.review_count == 5
    assert result.is_interleaved is True


def test_odd_total_rounding():
    new_pool = [f"N{i}" for i in range(1, 10)]
    review_pool = [f"R{i}" for i in range(1, 10)]

    # 5 * 0.7 = 3.5 -> round to 4
    result = InterleavingPracticeMixer.mix(
        new_questions=new_pool,
        review_questions=review_pool,
        total_questions=5,
    )

    assert result.total_count == 5
    assert result.new_count == 4
    assert result.review_count == 1


def test_deterministic_shuffle_with_seed():
    new_pool = [f"N{i}" for i in range(1, 10)]
    review_pool = [f"R{i}" for i in range(1, 10)]

    res1 = InterleavingPracticeMixer.mix(
        new_questions=new_pool,
        review_questions=review_pool,
        total_questions=8,
        seed=123,
    )
    res2 = InterleavingPracticeMixer.mix(
        new_questions=new_pool,
        review_questions=review_pool,
        total_questions=8,
        seed=123,
    )

    order1 = [q.question for q in res1.questions]
    order2 = [q.question for q in res2.questions]
    assert order1 == order2


def test_pool_immutability():
    new_pool = ["N1", "N2", "N3", "N4", "N5"]
    review_pool = ["R1", "R2", "R3"]

    new_copy = list(new_pool)
    review_copy = list(review_pool)

    InterleavingPracticeMixer.mix(
        new_questions=new_pool,
        review_questions=review_pool,
        total_questions=5,
        seed=99,
    )

    assert new_pool == new_copy
    assert review_pool == review_copy
