import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.quizzes.domain.interleaving_practice_mixer import (
    InterleavingPracticeMixer,
)
from app.modules.quizzes.exceptions import QuizNotFoundError
from app.modules.quizzes.models import Quiz, QuizQuestion
from app.modules.quizzes.schemas import QuizCreateRequest


class QuizService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_interleaved_quiz(
        self,
        user_id: uuid.UUID,
        payload: QuizCreateRequest,
    ) -> Quiz:
        # 1. Fetch historical review questions from other documents for this user
        stmt = (
            select(QuizQuestion)
            .join(Quiz, QuizQuestion.quiz_id == Quiz.id)
            .where(
                Quiz.user_id == user_id,
                Quiz.document_id != payload.document_id,
            )
        )
        if payload.subject_id is not None:
            stmt = stmt.where(Quiz.subject_id == payload.subject_id)

        result = await self.db.execute(stmt)
        review_db_questions = result.scalars().all()

        # Format review questions for the mixer
        review_pool: list[dict[str, Any]] = [
            {
                "question_text": q.question_text,
                "bloom_level": q.bloom_level,
                "options": q.options,
                "correct_option": q.correct_option,
                "explanation": q.explanation,
                "target_page": q.target_page,
                "topic_tag": q.topic_tag,
            }
            for q in review_db_questions
        ]

        # Format new questions for the mixer
        new_pool: list[dict[str, Any]] = [
            q.model_dump() for q in payload.new_questions
        ]

        # 2. Run Interleaving Practice Mixer domain algorithm (FR-20)
        mixed_result = InterleavingPracticeMixer.mix(
            new_questions=new_pool,
            review_questions=review_pool,
            total_questions=payload.total_questions,
            seed=payload.seed,
        )

        # 3. Create Quiz entity
        quiz = Quiz(
            user_id=user_id,
            document_id=payload.document_id,
            subject_id=payload.subject_id,
            title=payload.title,
            is_interleaved=mixed_result.is_interleaved,
            total_questions=mixed_result.total_count,
            time_limit_minutes=payload.time_limit_minutes,
        )
        self.db.add(quiz)
        await self.db.flush()

        # 4. Create QuizQuestion entities from mixed questions
        for item in mixed_result.questions:
            q_data = item.question
            question_entity = QuizQuestion(
                quiz_id=quiz.id,
                question_text=q_data["question_text"],
                bloom_level=q_data["bloom_level"],
                options=q_data["options"],
                correct_option=q_data["correct_option"],
                explanation=q_data.get("explanation"),
                target_page=q_data.get("target_page"),
                topic_tag=q_data.get("topic_tag"),
            )
            self.db.add(question_entity)

        await self.db.commit()

        # Refresh quiz with its questions loaded
        stmt_reload = (
            select(Quiz)
            .options(selectinload(Quiz.questions))
            .where(Quiz.id == quiz.id)
        )
        reloaded = await self.db.execute(stmt_reload)
        return reloaded.scalar_one()

    async def get_quiz(
        self,
        user_id: uuid.UUID,
        quiz_id: uuid.UUID,
    ) -> Quiz:
        stmt = (
            select(Quiz)
            .options(selectinload(Quiz.questions))
            .where(
                Quiz.id == quiz_id,
                Quiz.user_id == user_id,
            )
        )
        result = await self.db.execute(stmt)
        quiz = result.scalar_one_or_none()
        if not quiz:
            raise QuizNotFoundError(quiz_id)
        return quiz
