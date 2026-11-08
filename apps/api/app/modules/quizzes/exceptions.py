import uuid


class QuizDomainException(Exception):
    """Base exception for Quiz domain errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


QuizDomainError = QuizDomainException


class InsufficientQuestionsError(QuizDomainException):
    """Raised when question pool has fewer questions than requested."""


class DocumentNotFoundError(QuizDomainException):
    """Raised when the specified document does not exist or user lacks access."""

    def __init__(self, document_id: uuid.UUID | str) -> None:
        super().__init__(f"Document with id '{document_id}' was not found.")
        self.document_id = document_id


class DocumentNotReadyError(QuizDomainException):
    """Raised when the document is not in a ready/completed status or parsed pages are missing."""

    def __init__(
        self,
        document_id: uuid.UUID | str,
        reason: str = "Document is not ready or parsed",
    ) -> None:
        super().__init__(f"Document '{document_id}' is not ready: {reason}")
        self.document_id = document_id
        self.reason = reason


class InvalidPageRangeError(QuizDomainException):
    """Raised when the requested page range is logically invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class GeminiGenerationError(QuizDomainException):
    """Raised when LLM quiz generation fails or returns invalid format."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Failed to generate quiz: {reason}")
        self.reason = reason


class QuizNotFoundError(QuizDomainException):
    """Raised when the specified quiz does not exist or user lacks access."""

    def __init__(self, quiz_id: uuid.UUID | str) -> None:
        super().__init__(f"Quiz with id {quiz_id} not found.")
        self.quiz_id = quiz_id
