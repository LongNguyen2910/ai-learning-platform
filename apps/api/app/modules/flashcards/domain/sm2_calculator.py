from datetime import UTC, date, datetime, timedelta

from app.modules.flashcards.domain.entities import SM2ReviewResult


class SM2Calculator:
    MIN_EASINESS_FACTOR = 1.3

    @staticmethod
    def calculate(
        current_repetition: int,
        current_ef: float,
        current_interval: int,
        rating: int,
        review_date: date | None = None,
    ) -> SM2ReviewResult:
        """Calculate the next SM-2 spaced repetition state.

        Args:
            current_repetition: Number of consecutive successful recalls (>= 0).
            current_ef: Current Easiness Factor (EF >= 1.3).
            current_interval: Current interval in days (>= 1).
            rating: User review score from 0 (complete blackout) to 5 (perfect).
            review_date: Date of review (defaults to UTC current date).

        Returns:
            SM2ReviewResult containing updated repetition, EF, interval, and due date.
        """
        if isinstance(rating, bool) or not isinstance(rating, int) or not (0 <= rating <= 5):
            raise ValueError("Rating must be an integer between 0 and 5.")

        target_date = review_date or datetime.now(UTC).date()

        # SM-2 EF update formula
        delta_ef = 0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02)
        new_ef = round(max(SM2Calculator.MIN_EASINESS_FACTOR, current_ef + delta_ef), 2)

        # Early return on lapse (failure)
        if rating < 3:
            return SM2ReviewResult(
                repetition_number=0,
                easiness_factor=new_ef,
                interval_days=1,
                due_date=target_date + timedelta(days=1),
            )

        # Successful recall
        if current_repetition == 0:
            next_interval = 1
        elif current_repetition == 1:
            next_interval = 6
        else:
            next_interval = round(current_interval * new_ef)

        next_repetition = current_repetition + 1

        return SM2ReviewResult(
            repetition_number=next_repetition,
            easiness_factor=new_ef,
            interval_days=next_interval,
            due_date=target_date + timedelta(days=next_interval),
        )
