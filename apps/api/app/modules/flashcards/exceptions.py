import uuid


class FlashcardNotFoundError(Exception):
    def __init__(self, flashcard_id: uuid.UUID):
        super().__init__(f"Flashcard with id {flashcard_id} not found.")
        self.flashcard_id = flashcard_id
