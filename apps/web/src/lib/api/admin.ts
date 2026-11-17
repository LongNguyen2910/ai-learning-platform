import { getAuthHeaders } from "@/lib/api/documents"
import type { UserProfileResponse } from "@/lib/api/profile"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export interface AdminUserItem {
  id: string
  email: string
  full_name: string | null
  avatar_url?: string | null
  role: string
  is_active: boolean
  daily_token_limit: number
  used_token_today: number
  total_tokens_used: number
  documents_count: number
  chat_sessions_count: number
  current_streak: number
  longest_streak: number
  last_checkin_date?: string | null
  created_at: string
}

export interface AdminUsersSummary {
  total_users: number
  active_users: number
  suspended_users: number
  admin_users: number
  total_tokens_today: number
  total_tokens_all_time: number
  near_limit_users: number
}

export interface AdminUsersListResponse {
  summary: AdminUsersSummary
  users: AdminUserItem[]
}

export interface AdminUpdateUserPayload {
  is_active?: boolean
  role?: "user" | "admin"
  daily_token_limit?: number
  reset_today_tokens?: boolean
}

export class AdminApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "AdminApiError"
    this.status = status
  }
}

async function parseErrorDetail(
  response: Response,
  fallback: string
): Promise<string> {
  try {
    const data = await response.json()
    if (data && typeof data.detail === "string" && data.detail.trim()) {
      return data.detail
    }
  } catch {
    // Ignore non-JSON error bodies
  }
  return fallback
}

export async function fetchAdminUsers(params?: {
  search?: string
  status_filter?: "all" | "active" | "suspended" | "admin"
  sort_by?: "created_at" | "tokens_today" | "tokens_total"
}): Promise<AdminUsersListResponse> {
  const url = new URL(`${API_BASE_URL}/admin/users`)
  if (params?.search?.trim()) {
    url.searchParams.set("search", params.search.trim())
  }
  if (params?.status_filter) {
    url.searchParams.set("status_filter", params.status_filter)
  }
  if (params?.sort_by) {
    url.searchParams.set("sort_by", params.sort_by)
  }

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    const detail = await parseErrorDetail(
      response,
      `Failed to load users (${response.status})`
    )
    throw new AdminApiError(detail, response.status)
  }

  return response.json()
}

export async function updateAdminUser(
  userId: string,
  payload: AdminUpdateUserPayload
): Promise<AdminUserItem> {
  const response = await fetch(
    `${API_BASE_URL}/admin/users/${encodeURIComponent(userId)}`,
    {
      method: "PATCH",
      headers: getAuthHeaders({
        Accept: "application/json",
        "Content-Type": "application/json",
      }),
      body: JSON.stringify(payload),
    }
  )

  if (!response.ok) {
    const detail = await parseErrorDetail(
      response,
      `Failed to update user (${response.status})`
    )
    throw new AdminApiError(detail, response.status)
  }

  return response.json()
}

export async function deleteAdminUser(
  userId: string
): Promise<{ message: string }> {
  const response = await fetch(
    `${API_BASE_URL}/admin/users/${encodeURIComponent(userId)}`,
    {
      method: "DELETE",
      headers: getAuthHeaders({ Accept: "application/json" }),
    }
  )

  if (!response.ok) {
    const detail = await parseErrorDetail(
      response,
      `Failed to delete user (${response.status})`
    )
    throw new AdminApiError(detail, response.status)
  }

  return response.json()
}

export async function toggleMyAdminRole(): Promise<UserProfileResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/me/toggle-role`, {
    method: "POST",
    headers: getAuthHeaders({ Accept: "application/json" }),
  })

  if (!response.ok) {
    const detail = await parseErrorDetail(
      response,
      `Failed to toggle role (${response.status})`
    )
    throw new AdminApiError(detail, response.status)
  }

  return response.json()
}
