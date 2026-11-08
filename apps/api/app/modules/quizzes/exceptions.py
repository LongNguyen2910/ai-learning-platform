import uuid


class QuizDomainError(ValueError):
    """Base domain exception for quizzes module."""


class InsufficientQuestionsError(QuizDomainError):
    """Raised when question pool has fewer questions than requested."""


class QuizNotFoundError(QuizDomainError):
    """Raised when quiz is not found."""

    def __init__(self, quiz_id: uuid.UUID):
        super().__init__(f"Quiz with id {quiz_id} not found.")
        self.quiz_id = quiz_id
