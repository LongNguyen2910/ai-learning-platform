class StudySessionError(Exception):
    """Base exception for study session domain."""
    pass


class SubjectNotFoundError(StudySessionError):
    """Subject not found or does not belong to user."""
    pass


class DocumentMismatchError(StudySessionError):
    """Document not found or does not belong to user/subject."""
    pass


class RoadmapNodeMismatchError(StudySessionError):
    """Roadmap node not found or does not belong to user/subject."""
    pass


class StudySessionNotFoundError(StudySessionError):
    """Study session not found or does not belong to user."""
    pass
