import uuid


class RoadmapDomainException(Exception):
    """Base exception for Roadmap domain errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RoadmapNotFoundException(RoadmapDomainException):
    """Raised when a roadmap cannot be found."""

    def __init__(self, roadmap_id: uuid.UUID | str) -> None:
        super().__init__(f"Roadmap with id '{roadmap_id}' was not found.")
        self.roadmap_id = roadmap_id


class SubjectNotFoundException(RoadmapDomainException):
    """Raised when the specified subject is missing or not accessible."""

    def __init__(self, subject_id: uuid.UUID | str) -> None:
        super().__init__(f"Subject with id '{subject_id}' was not found.")
        self.subject_id = subject_id


class DocumentNotParsedException(RoadmapDomainException):
    """Raised when the associated document has not been parsed or is missing."""

    def __init__(self, document_id: uuid.UUID | str) -> None:
        super().__init__(
            f"Document '{document_id}' is not parsed or ready for roadmap generation."
        )
        self.document_id = document_id


class InvalidStudyGoalException(RoadmapDomainException):
    """Raised when the target date or study hours are logically invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class CurriculumExtractionFailedException(RoadmapDomainException):
    """Raised when AI extraction of document curriculum fails."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Failed to extract curriculum outline: {reason}")


class NodeNotFoundException(RoadmapDomainException):
    """Raised when a roadmap node cannot be found."""

    def __init__(self, node_id: uuid.UUID | str) -> None:
        super().__init__(f"RoadmapNode '{node_id}' was not found.")
        self.node_id = node_id


class NodeLockedException(RoadmapDomainException):
    """Raised when attempting to complete a locked node."""

    def __init__(self, node_id: uuid.UUID | str) -> None:
        super().__init__(f"RoadmapNode '{node_id}' is locked and cannot be completed.")
        self.node_id = node_id


class NodeNotLeafException(RoadmapDomainException):
    """Raised when attempting to directly complete a parent chapter or topic."""

    def __init__(self, node_id: uuid.UUID | str) -> None:
        super().__init__(
            f"RoadmapNode '{node_id}' is not a leaf study block and cannot be completed directly."
        )
        self.node_id = node_id


class RoadmapAccessForbiddenException(RoadmapDomainException):
    """Raised when an unauthorized user attempts to mutate a roadmap node."""

    def __init__(self, roadmap_id: uuid.UUID | str) -> None:
        super().__init__(f"You do not have access to roadmap '{roadmap_id}'.")
        self.roadmap_id = roadmap_id


class RoadmapNotActiveException(RoadmapDomainException):
    """Raised when attempting to modify a roadmap that is archived or inactive."""

    def __init__(self, roadmap_id: uuid.UUID | str, status: str) -> None:
        super().__init__(
            f"Roadmap '{roadmap_id}' cannot be modified because its status is '{status}'."
        )
        self.roadmap_id = roadmap_id
        self.status = status


class PrerequisiteNotCompletedException(RoadmapDomainException):
    """Raised when attempting to complete a node before previous study blocks are completed."""

    def __init__(
        self, node_id: uuid.UUID | str, prerequisite_node_id: uuid.UUID | str
    ) -> None:
        super().__init__(
            f"Cannot complete node '{node_id}' before previous node '{prerequisite_node_id}' is completed."
        )
        self.node_id = node_id
        self.prerequisite_node_id = prerequisite_node_id

