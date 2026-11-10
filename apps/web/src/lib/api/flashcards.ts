import { getAuthHeaders } from "@/lib/api/documents"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export type FlashcardCategory = "term" | "concept" | "formula"
export type FlashcardReviewRating = "again" | "hard" | "good" | "easy"

export interface FlashcardItem {
  id: string
  deck_id: string
  user_id: string
  front_text: string
  back_text: string
  page_number: number | null
  repetition_number: number
  easiness_factor: number
  interval_days: number
  due_date: string
  created_at: string
}

export interface FlashcardDeckSummary {
  id: string
  user_id: string
  subject_id: string | null
  document_id: string | null
  title: string
  description: string | null
  created_at: string
  total_cards: number
  due_count: number
  mastered_count: number
}

export interface FlashcardDeckDetail extends FlashcardDeckSummary {
  cards: FlashcardItem[]
}

export interface ExtractedFlashcardCandidate {
  front_text: string
  back_text: string
  category?: FlashcardCategory | string
  context_snippet?: string | null
  trigger_reason?: string | null
  target_page?: number | null
}

export interface FlashcardExtractResponse {
  source_type: "quiz_attempt" | "chat_session"
  source_id: string
  cards: ExtractedFlashcardCandidate[]
  total_extracted: number
  message: string | null
}

export interface FlashcardCreatePayload {
  front_text: string
  back_text: string
  page_number?: number | null
}

export interface FlashcardDeckCreatePayload {
  title: string
  description?: string | null
  subject_id?: string | null
  document_id?: string | null
}

export interface FlashcardDeckGeneratePayload {
  document_id: string
  num_cards: number
  page_start?: number | null
  page_end?: number | null
  title?: string | null
}

export async function fetchFlashcardDecks(
  subjectId?: string | null
): Promise<FlashcardDeckSummary[]> {
  const url = new URL(`${API_BASE_URL}/flashcards/decks`)
  if (subjectId) {
    url.searchParams.set("subject_id", subjectId)
  }

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to load flashcard decks (${response.status})`
    )
  }

  return response.json()
}

export async function fetchFlashcardDeckDetail(
  deckId: string
): Promise<FlashcardDeckDetail> {
  const response = await fetch(`${API_BASE_URL}/flashcards/decks/${deckId}`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to load flashcard deck (${response.status})`
    )
  }

  return response.json()
}

export async function createFlashcardDeck(
  payload: FlashcardDeckCreatePayload
): Promise<FlashcardDeckDetail> {
  const response = await fetch(`${API_BASE_URL}/flashcards/decks`, {
    method: "POST",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to create flashcard deck (${response.status})`
    )
  }

  return response.json()
}

export async function generateFlashcardDeck(
  payload: FlashcardDeckGeneratePayload
): Promise<FlashcardDeckDetail> {
  const response = await fetch(`${API_BASE_URL}/flashcards/decks/generate`, {
    method: "POST",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to generate AI flashcard deck (${response.status})`
    )
  }

  return response.json()
}

export async function deleteFlashcardDeck(deckId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/flashcards/decks/${deckId}`, {
    method: "DELETE",
    headers: getAuthHeaders({ Accept: "application/json" }),
  })

  if (!response.ok && response.status !== 204) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to delete flashcard deck (${response.status})`
    )
  }
}

export async function createSingleFlashcard(
  deckId: string,
  payload: FlashcardCreatePayload
): Promise<FlashcardItem> {
  const response = await fetch(
    `${API_BASE_URL}/flashcards/decks/${deckId}/cards`,
    {
      method: "POST",
      headers: getAuthHeaders({
        Accept: "application/json",
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(payload),
    }
  )

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to create flashcard (${response.status})`
    )
  }

  return response.json()
}

export async function updateSingleFlashcard(
  cardId: string,
  payload: FlashcardCreatePayload
): Promise<FlashcardItem> {
  const response = await fetch(`${API_BASE_URL}/flashcards/cards/${cardId}`, {
    method: "PUT",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to update flashcard (${response.status})`
    )
  }

  return response.json()
}

export async function deleteSingleFlashcard(cardId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/flashcards/cards/${cardId}`, {
    method: "DELETE",
    headers: getAuthHeaders({ Accept: "application/json" }),
  })

  if (!response.ok && response.status !== 204) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to delete flashcard (${response.status})`
    )
  }
}

export async function reviewFlashcard(
  cardId: string,
  rating: FlashcardReviewRating
): Promise<FlashcardItem> {
  const response = await fetch(
    `${API_BASE_URL}/flashcards/cards/${cardId}/review`,
    {
      method: "POST",
      headers: getAuthHeaders({
        Accept: "application/json",
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({ rating }),
    }
  )

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to record flashcard review (${response.status})`
    )
  }

  return response.json()
}

export async function extractFlashcardsFromQuizAttempt(
  attemptId: string
): Promise<FlashcardExtractResponse> {
  const response = await fetch(`${API_BASE_URL}/flashcards/extract`, {
    method: "POST",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({
      source_type: "quiz_attempt",
      source_id: attemptId,
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to extract flashcards (${response.status})`
    )
  }

  return response.json()
}

export async function bulkSaveFlashcards(
  deckId: string,
  cards: FlashcardCreatePayload[]
): Promise<{
  deck_id: string
  created_count: number
  cards: FlashcardItem[]
}> {
  const response = await fetch(`${API_BASE_URL}/flashcards/bulk`, {
    method: "POST",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({
      deck_id: deckId,
      cards,
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Failed to save flashcards to deck (${response.status})`
    )
  }

  return response.json()
}
