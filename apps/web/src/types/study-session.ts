export interface StudySessionCreatePayload {
  subject_id: string
  duration_minutes: number
  document_id?: string | null
  roadmap_node_id?: string | null
  session_type?: "pomodoro" | "deep_work" | "review" | string
  completed_at?: string | null
}

export interface StudySessionItem {
  id: string
  user_id: string
  subject_id: string | null
  document_id: string | null
  roadmap_node_id: string | null
  duration_minutes: number
  session_type: string
  completed_at: string
}
