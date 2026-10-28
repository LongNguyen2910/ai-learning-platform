import { getAuthHeaders } from "@/lib/api/documents"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export interface SubjectItem {
  id: string
  user_id: string
  name: string
  code?: string | null
  description?: string | null
  color_hex: string
  created_at: string
}

export interface RoadmapGeneratePayload {
  subject_id: string
  document_id?: string | null
  title: string
  target_date: string
  available_hours_per_day: number
  study_goal?: string | null
}

export interface RoadmapTaskStatusResponse {
  task_id: string
  roadmap_id: string | null
  status: "processing" | "completed" | "failed" | string
  progress_percent: number
  message: string
  error?: string | null
}

export interface RoadmapItem {
  id: string
  user_id: string
  subject_id: string
  title: string
  target_date: string | null
  available_hours_per_day: number
  progress_percentage: number
  status: "generating" | "active" | "completed" | "failed" | string
  created_at: string
}

export interface RoadmapNodeItem {
  id: string
  roadmap_id: string
  parent_node_id: string | null
  document_id: string | null
  title: string
  description: string | null
  order_index: number
  target_page_start: number | null
  target_page_end: number | null
  estimated_minutes: number
  is_unlocked: boolean
  is_completed: boolean
  completed_at: string | null
  children: RoadmapNodeItem[]
}

export interface RoadmapTreeResponse {
  roadmap: RoadmapItem
  tree: RoadmapNodeItem[]
  total_nodes: number
  total_estimated_minutes: number
}

export async function fetchSubjects(): Promise<SubjectItem[]> {
  const response = await fetch(`${API_BASE_URL}/subjects`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch subjects (${response.status})`)
  }

  return response.json()
}

export async function createSubject(payload: {
  name: string
  code?: string
  description?: string
  color_hex?: string
}): Promise<SubjectItem> {
  const response = await fetch(`${API_BASE_URL}/subjects`, {
    method: "POST",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify({
      name: payload.name,
      code: payload.code ?? null,
      description: payload.description ?? null,
      color_hex: payload.color_hex ?? "#0A77FF",
    }),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Could not create subject (${response.status})`
    )
  }

  return response.json()
}

/**
 * Automatically resolves an existing Subject or creates one matching the document title
 * so the user doesn't have to manually configure Subjects before generating a roadmap.
 */
export async function resolveOrCreateDefaultSubject(
  fallbackTitle: string
): Promise<SubjectItem> {
  const subjects = await fetchSubjects().catch(() => [])
  const normalizedTitle = fallbackTitle.trim().toLowerCase()
  const matched = subjects.find(
    (s) => s.name.trim().toLowerCase() === normalizedTitle
  )
  if (matched) return matched
  if (subjects.length > 0) return subjects[0]

  const cleanName = fallbackTitle.trim().slice(0, 140) || "Học phần chung"
  return createSubject({
    name: cleanName,
    description: "Tự động khởi tạo từ trình tạo lộ trình học tập AI",
    color_hex: "#0A77FF",
  })
}

export async function fetchRoadmaps(): Promise<RoadmapItem[]> {
  const response = await fetch(`${API_BASE_URL}/roadmaps`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    // Fallback: iterate subjects if backend wasn't restarted with GET /roadmaps yet
    const subjects = await fetchSubjects().catch(() => [])
    const allLists = await Promise.all(
      subjects.map((s) => fetchSubjectRoadmaps(s.id).catch(() => []))
    )
    return allLists
      .flat()
      .sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
  }

  return response.json()
}

export async function fetchSubjectRoadmaps(
  subjectId: string
): Promise<RoadmapItem[]> {
  const response = await fetch(`${API_BASE_URL}/roadmaps/subject/${subjectId}`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch subject roadmaps (${response.status})`)
  }

  return response.json()
}

export async function generateRoadmap(
  payload: RoadmapGeneratePayload
): Promise<RoadmapTaskStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/roadmaps/generate`, {
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
      err?.detail || `Không thể khởi tạo lộ trình (${response.status})`
    )
  }

  return response.json()
}

export async function fetchRoadmapTaskStatus(
  taskId: string
): Promise<RoadmapTaskStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/roadmaps/tasks/${taskId}`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Không thể kiểm tra tiến độ (${response.status})`
    )
  }

  return response.json()
}

export async function fetchRoadmapTree(
  roadmapId: string
): Promise<RoadmapTreeResponse> {
  const response = await fetch(`${API_BASE_URL}/roadmaps/${roadmapId}/tree`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Không thể tải cấu trúc lộ trình (${response.status})`
    )
  }

  return response.json()
}

export async function deleteRoadmap(roadmapId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/roadmaps/${roadmapId}`, {
    method: "DELETE",
    headers: getAuthHeaders({ Accept: "application/json" }),
  })

  if (!response.ok && response.status !== 204) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Không thể xóa lộ trình (${response.status})`)
  }
}

export async function deleteSubject(subjectId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/subjects/${subjectId}`, {
    method: "DELETE",
    headers: getAuthHeaders({ Accept: "application/json" }),
  })

  if (!response.ok && response.status !== 204) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Không thể xóa môn học (${response.status})`)
  }
}
