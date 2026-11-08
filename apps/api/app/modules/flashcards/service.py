import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.flashcards.domain.sm2_calculator import SM2Calculator
from app.modules.flashcards.exceptions import FlashcardNotFoundError
from app.modules.flashcards.models import Flashcard


class FlashcardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def review_flashcard(
        self,
        user_id: uuid.UUID,
        flashcard_id: uuid.UUID,
        rating: int,
        review_date: date | None = None,
    ) -> Flashcard:
        stmt = select(Flashcard).where(
            Flashcard.id == flashcard_id,
            Flashcard.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        flashcard = result.scalar_one_or_none()

        if not flashcard:
            raise FlashcardNotFoundError(flashcard_id)

        sm2_result = SM2Calculator.calculate(
            current_repetition=flashcard.repetition_number,
            current_ef=flashcard.easiness_factor,
            current_interval=flashcard.interval_days,
            rating=rating,
            review_date=review_date,
        )

        flashcard.repetition_number = sm2_result.repetition_number
        flashcard.easiness_factor = sm2_result.easiness_factor
        flashcard.interval_days = sm2_result.interval_days
        flashcard.due_date = sm2_result.due_date

        await self.db.commit()
        await self.db.refresh(flashcard)
        return flashcard
