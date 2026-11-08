import { getAuthHeaders } from "@/lib/api/documents"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

const API_ORIGIN = API_BASE_URL.replace(/\/api\/v1\/?$/, "")

export interface UserProfileResponse {
  id: string
  email: string
  full_name: string | null
  avatar_url?: string | null
  role: string
  is_active: boolean
  daily_token_limit: number
  used_token_today: number
  created_at: string
}

export interface UserUpdatePayload {
  full_name?: string | null
  avatar_url?: string | null
}

export interface ChangePasswordPayload {
  current_password: string
  new_password: string
}

export interface MessageResponse {
  message: string
}

export function resolveAvatarUrl(avatarUrl?: string | null): string | null {
  if (!avatarUrl) return null
  const trimmed = avatarUrl.trim()
  if (!trimmed) return null
  if (
    trimmed.startsWith("http://") ||
    trimmed.startsWith("https://") ||
    trimmed.startsWith("data:") ||
    trimmed.startsWith("blob:")
  ) {
    return trimmed
  }
  if (trimmed.startsWith("/")) {
    return `${API_ORIGIN}${trimmed}`
  }
  return `${API_ORIGIN}/${trimmed}`
}

export async function fetchUserProfile(): Promise<UserProfileResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Failed to fetch profile (${response.status})`)
  }

  return response.json()
}

export async function updateUserProfile(
  payload: UserUpdatePayload
): Promise<UserProfileResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    method: "PATCH",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Failed to update profile (${response.status})`)
  }

  return response.json()
}

export async function uploadUserAvatar(
  file: File
): Promise<UserProfileResponse> {
  const formData = new FormData()
  formData.append("file", file)

  const response = await fetch(`${API_BASE_URL}/auth/me/avatar`, {
    method: "POST",
    headers: getAuthHeaders({ Accept: "application/json" }),
    body: formData,
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Failed to upload avatar (${response.status})`)
  }

  return response.json()
}

export async function changeUserPassword(
  payload: ChangePasswordPayload
): Promise<MessageResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/change-password`, {
    method: "POST",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Failed to change password (${response.status})`)
  }

  return response.json()
}
