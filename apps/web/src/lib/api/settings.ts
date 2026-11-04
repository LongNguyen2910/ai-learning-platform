import { getAuthHeaders } from "@/lib/api/documents"

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export type SocraticGuidanceDepth = "exploratory" | "balanced" | "concise"
export type StudySessionMode = "auto" | "micro" | "deep_work"
export type AppTheme = "light" | "dark" | "system"

export interface LearningPreferences {
  socraticEnabled: boolean
  guidanceDepth: SocraticGuidanceDepth
  dailyBudgetHours: number
  sessionMode: StudySessionMode
}

export interface AppearancePreferences {
  theme: AppTheme
  splitRatio: number
}

const LEARNING_PREFS_KEY = "luminal_learning_preferences"
const APPEARANCE_PREFS_KEY = "luminal_appearance_preferences"

export const DEFAULT_LEARNING_PREFS: LearningPreferences = {
  socraticEnabled: true,
  guidanceDepth: "balanced",
  dailyBudgetHours: 2.0,
  sessionMode: "auto",
}

export const DEFAULT_APPEARANCE_PREFS: AppearancePreferences = {
  theme: "system",
  splitRatio: 52,
}

export function loadLearningPreferences(): LearningPreferences {
  if (typeof window === "undefined") return DEFAULT_LEARNING_PREFS
  try {
    const raw = localStorage.getItem(LEARNING_PREFS_KEY)
    if (!raw) return DEFAULT_LEARNING_PREFS
    return { ...DEFAULT_LEARNING_PREFS, ...JSON.parse(raw) }
  } catch {
    return DEFAULT_LEARNING_PREFS
  }
}

export function saveLearningPreferences(prefs: LearningPreferences): void {
  if (typeof window === "undefined") return
  try {
    localStorage.setItem(LEARNING_PREFS_KEY, JSON.stringify(prefs))
  } catch {
    // Ignore localStorage storage quota failures
  }
}

export function loadAppearancePreferences(): AppearancePreferences {
  if (typeof window === "undefined") return DEFAULT_APPEARANCE_PREFS
  try {
    const raw = localStorage.getItem(APPEARANCE_PREFS_KEY)
    if (!raw) return DEFAULT_APPEARANCE_PREFS
    return { ...DEFAULT_APPEARANCE_PREFS, ...JSON.parse(raw) }
  } catch {
    return DEFAULT_APPEARANCE_PREFS
  }
}

export function saveAppearancePreferences(prefs: AppearancePreferences): void {
  if (typeof window === "undefined") return
  try {
    localStorage.setItem(APPEARANCE_PREFS_KEY, JSON.stringify(prefs))

    // Apply theme immediately to HTML root element
    const root = document.documentElement
    if (prefs.theme === "dark") {
      root.classList.add("dark")
    } else if (prefs.theme === "light") {
      root.classList.remove("dark")
    } else {
      // System mode
      if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
        root.classList.add("dark")
      } else {
        root.classList.remove("dark")
      }
    }
  } catch {
    // Ignore localStorage storage quota failures
  }
}

export interface DeleteAccountPayload {
  current_password: string
}

export interface MessageResponse {
  message: string
}

export async function deleteUserAccount(
  payload: DeleteAccountPayload
): Promise<MessageResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/account`, {
    method: "DELETE",
    headers: getAuthHeaders({
      Accept: "application/json",
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    const err = await response.json().catch(() => null)
    throw new Error(err?.detail || `Failed to delete account (${response.status})`)
  }

  return response.json()
}
