from app.modules.flashcards.router import router as flashcards_router
from app.modules.flashcards.service import FlashcardService, flashcard_service

__all__ = ["FlashcardService", "flashcard_service", "flashcards_router"]
