import { getAuthHeaders } from "@/lib/api/documents"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export type BloomLevel = "remember" | "understand" | "apply" | string

export interface QuizOptionItem {
  key: "A" | "B" | "C" | "D" | string
  text: string
}

export interface QuizQuestionItem {
  id: string
  question_text: string
  bloom_level: BloomLevel
  options: QuizOptionItem[]
  correct_option: string
  explanation: string | null
  target_page: number | null
  topic_tag: string | null
}

export interface QuizItem {
  id: string
  document_id: string
  subject_id: string | null
  title: string
  total_questions: number
  time_limit_minutes: number
  created_at: string
  questions: QuizQuestionItem[]
}

export interface QuizGeneratePayload {
  document_id: string
  num_questions: number
  page_start?: number | null
  page_end?: number | null
  topic_tag?: string | null
  title?: string | null
}

export async function fetchQuizzes(subjectId?: string | null): Promise<QuizItem[]> {
  const url = new URL(`${API_BASE_URL}/quizzes`)
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
    throw new Error(err?.detail || `Failed to load quizzes (${response.status})`)
  }

  return response.json()
}

export async function fetchQuizById(quizId: string): Promise<QuizItem> {
  const response = await fetch(`${API_BASE_URL}/quizzes/${quizId}`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Quiz not found (${response.status})`)
  }

  return response.json()
}

export async function generateQuiz(payload: QuizGeneratePayload): Promise<QuizItem> {
  const response = await fetch(`${API_BASE_URL}/quizzes/generate`, {
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
      err?.detail || `Failed to generate AI quiz (${response.status})`
    )
  }

  return response.json()
}

export async function deleteQuiz(quizId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/quizzes/${quizId}`, {
    method: "DELETE",
    headers: getAuthHeaders({ Accept: "application/json" }),
  })

  if (!response.ok && response.status !== 204) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Failed to delete quiz (${response.status})`)
  }
}
