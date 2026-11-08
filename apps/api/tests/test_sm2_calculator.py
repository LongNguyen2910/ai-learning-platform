from datetime import date, timedelta

import pytest

from app.modules.flashcards.domain.sm2_calculator import SM2Calculator


def test_invalid_rating_raises_value_error():
    invalid_ratings = [6, -1, True, False, 3.5, "4"]
    for bad_rating in invalid_ratings:
        with pytest.raises(ValueError, match="Rating must be an integer between 0 and 5"):
            SM2Calculator.calculate(
                current_repetition=0,
                current_ef=2.5,
                current_interval=1,
                rating=bad_rating,  # type: ignore[arg-type]
            )


def test_rating_under_three_resets_repetition_and_interval():
    base_date = date(2026, 11, 8)
    result = SM2Calculator.calculate(
        current_repetition=3,
        current_ef=2.5,
        current_interval=15,
        rating=2,
        review_date=base_date,
    )

    assert result.repetition_number == 0
    assert result.interval_days == 1
    assert result.due_date == base_date + timedelta(days=1)
    # EF formula: 2.5 + (0.1 - (3 * 0.14)) = 2.5 + (0.1 - 0.42) = 2.18
    assert result.easiness_factor == 2.18


def test_easiness_factor_cannot_drop_below_minimum():
    result = SM2Calculator.calculate(
        current_repetition=1,
        current_ef=1.35,
        current_interval=6,
        rating=0,
    )

    assert result.easiness_factor == 1.30


def test_success_progression_intervals():
    base_date = date(2026, 1, 1)

    # First review: rating 4 (rep 0 -> 1, interval 1)
    # EF: 2.5 + (0.1 - 1 * 0.1) = 2.5
    res1 = SM2Calculator.calculate(
        current_repetition=0,
        current_ef=2.5,
        current_interval=1,
        rating=4,
        review_date=base_date,
    )
    assert res1.repetition_number == 1
    assert res1.interval_days == 1
    assert res1.easiness_factor == 2.5
    assert res1.due_date == base_date + timedelta(days=1)

    # Second review: rating 4 (rep 1 -> 2, interval 6)
    res2 = SM2Calculator.calculate(
        current_repetition=res1.repetition_number,
        current_ef=res1.easiness_factor,
        current_interval=res1.interval_days,
        rating=4,
        review_date=res1.due_date,
    )
    assert res2.repetition_number == 2
    assert res2.interval_days == 6
    assert res2.easiness_factor == 2.5
    assert res2.due_date == res1.due_date + timedelta(days=6)

    # Third review: rating 5 (rep 2 -> 3, interval = round(6 * EF'))
    # delta_ef: 0.1 - 0 = +0.1 -> new EF = 2.6
    # interval: round(6 * 2.6) = round(15.6) = 16
    res3 = SM2Calculator.calculate(
        current_repetition=res2.repetition_number,
        current_ef=res2.easiness_factor,
        current_interval=res2.interval_days,
        rating=5,
        review_date=res2.due_date,
    )
    assert res3.repetition_number == 3
    assert res3.interval_days == 16
    assert res3.easiness_factor == 2.6
    assert res3.due_date == res2.due_date + timedelta(days=16)


def test_result_immutability():
    result = SM2Calculator.calculate(
        current_repetition=0,
        current_ef=2.5,
        current_interval=1,
        rating=5,
    )

    with pytest.raises(AttributeError):
        result.interval_days = 10  # Frozen dataclass check


@pytest.mark.parametrize(
    ("rating", "expected_ef"),
    [
        (0, 1.70),
        (1, 1.96),
        (2, 2.18),
        (3, 2.36),
        (4, 2.50),
        (5, 2.60),
    ],
)
def test_all_ratings_delta_ef(rating: int, expected_ef: float):
    result = SM2Calculator.calculate(
        current_repetition=1,
        current_ef=2.5,
        current_interval=6,
        rating=rating,
    )
    assert result.easiness_factor == expected_ef

