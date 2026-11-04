import { getAuthHeaders } from "@/lib/api/documents"
import type {
  StudySessionCreatePayload,
  StudySessionItem,
} from "@/types/study-session"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export async function createStudySession(
  payload: StudySessionCreatePayload
): Promise<StudySessionItem> {
  const res = await fetch(`${API_BASE_URL}/study-sessions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify(payload),
  })

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(
      errorBody.detail || "Không thể lưu nhật ký phiên học Pomodoro."
    )
  }

  return res.json()
}

export async function getStudySessions(params?: {
  subject_id?: string
  limit?: number
  offset?: number
}): Promise<StudySessionItem[]> {
  const query = new URLSearchParams()
  if (params?.subject_id) query.append("subject_id", params.subject_id)
  if (params?.limit) query.append("limit", params.limit.toString())
  if (params?.offset) query.append("offset", params.offset.toString())

  const queryString = query.toString() ? `?${query.toString()}` : ""
  const res = await fetch(`${API_BASE_URL}/study-sessions${queryString}`, {
    method: "GET",
    headers: getAuthHeaders(),
  })

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(
      errorBody.detail || "Không thể tải danh sách phiên học Pomodoro."
    )
  }

  return res.json()
}

export async function deleteStudySession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/study-sessions/${sessionId}`, {
    method: "DELETE",
    headers: getAuthHeaders(),
  })

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}))
    throw new Error(
      errorBody.detail || "Không thể xóa phiên học Pomodoro."
    )
  }
}
