from app.modules.quizzes.router import router as quizzes_router
from app.modules.quizzes.service import QuizService, quiz_service

__all__ = ["QuizService", "quiz_service", "quizzes_router"]
