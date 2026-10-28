"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  User,
  Settings,
  LogOut,
  ChevronDown,
  FileText,
  ChevronRight,
  Network,
} from "lucide-react"
import { getAuthHeaders, getAuthToken } from "@/lib/api/documents"
import type { SidebarSection } from "@/components/dashboard/app-sidebar"

interface AuthUser {
  id: string
  email: string
  full_name?: string | null
  role?: string
}

interface TopHeaderProps {
  activeSection?: SidebarSection
  activeDocumentTitle?: string | null
  onBackToDocuments?: () => void
}

export function TopHeader({
  activeSection = "documents",
  activeDocumentTitle,
  onBackToDocuments,
}: TopHeaderProps) {
  const router = useRouter()
  const [menuOpen, setMenuOpen] = React.useState(false)
  const [noticeMessage, setNoticeMessage] = React.useState<string | null>(null)
  const [currentUser, setCurrentUser] = React.useState<AuthUser | null>(null)
  const dropdownRef = React.useRef<HTMLDivElement>(null)

  // Load current user from localStorage immediately, then sync with GET /auth/me
  React.useEffect(() => {
    if (typeof window === "undefined") return

    try {
      const cached = localStorage.getItem("auth_user")
      if (cached) {
        const parsed = JSON.parse(cached) as AuthUser
        if (parsed && (parsed.full_name || parsed.email)) {
          setCurrentUser(parsed)
        }
      }
    } catch {
      // Ignore invalid JSON in localStorage
    }

    const token = getAuthToken()
    if (!token) return

    let cancelled = false
    const apiUrl =
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

    const fetchMe = async () => {
      try {
        const response = await fetch(`${apiUrl}/auth/me`, {
          method: "GET",
          headers: getAuthHeaders({ Accept: "application/json" }),
        })
        if (!response.ok) return
        const data = (await response.json()) as AuthUser
        if (!cancelled && data) {
          setCurrentUser(data)
          localStorage.setItem("auth_user", JSON.stringify(data))
        }
      } catch {
        // Keep cached user if backend is temporarily unreachable
      }
    }

    void fetchMe()
    return () => {
      cancelled = true
    }
  }, [])

  // Close dropdown when clicking outside or pressing Escape
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setMenuOpen(false)
      }
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false)
      }
    }

    document.addEventListener("mousedown", handleClickOutside)
    document.addEventListener("keydown", handleKeyDown)
    return () => {
      document.removeEventListener("mousedown", handleClickOutside)
      document.removeEventListener("keydown", handleKeyDown)
    }
  }, [])

  const handlePlaceholderClick = (featureName: string) => {
    setMenuOpen(false)
    setNoticeMessage(`${featureName} will be available in an upcoming sprint.`)
    setTimeout(() => {
      setNoticeMessage(null)
    }, 2800)
  }

  const handleLogout = () => {
    setMenuOpen(false)
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token")
      localStorage.removeItem("auth_user")
    }
    router.replace("/login")
    router.refresh()
  }

  const displayName =
    currentUser?.full_name?.trim() ||
    currentUser?.email?.split("@")[0] ||
    "Account"
  const displayEmail = currentUser?.email || "Personal Account"

  return (
    <header className="h-16 w-full border-b border-slate-200/80 dark:border-slate-800/80 bg-white/95 dark:bg-slate-950/95 backdrop-blur-sm px-6 flex items-center justify-between shrink-0 z-20">
      {/* Left: Context Breadcrumb */}
      <div className="flex items-center gap-2 min-w-0">
        {activeSection === "roadmap" ? (
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white px-2 py-1 -ml-2">
            <Network className="h-4 w-4 text-[#0A77FF] shrink-0" />
            <span>Roadmap</span>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={() => onBackToDocuments?.()}
              className={`flex items-center gap-2 text-sm font-medium rounded-lg px-2 py-1 -ml-2 transition-colors ${
                activeDocumentTitle
                  ? "text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-white dark:hover:bg-slate-900 cursor-pointer"
                  : "text-slate-900 dark:text-white font-semibold cursor-default"
              }`}
            >
              <FileText className="h-4 w-4 text-[#0A77FF] shrink-0" />
              <span>My Documents</span>
            </button>

            {activeDocumentTitle && (
              <>
                <ChevronRight className="h-4 w-4 text-slate-300 dark:text-slate-700 shrink-0" />
                <span className="text-sm font-semibold text-slate-900 dark:text-white truncate max-w-[240px] sm:max-w-[420px]">
                  {activeDocumentTitle}
                </span>
              </>
            )}
          </>
        )}
      </div>

      {/* Right: Subtle notification pill & User Profile Dropdown */}
      <div className="flex items-center gap-3">
        {noticeMessage && (
          <div
            role="status"
            className="hidden sm:flex items-center gap-2 rounded-full bg-slate-100 dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 px-3 py-1 text-xs font-medium text-slate-600 dark:text-slate-300 animate-in fade-in-0 duration-150"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-[#0A77FF]" />
            <span>{noticeMessage}</span>
          </div>
        )}

        <div className="relative" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((prev) => !prev)}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
            aria-label="User profile menu"
            className="flex items-center gap-2.5 rounded-full p-1 pr-3 border border-slate-200/90 dark:border-slate-800 bg-slate-50/70 hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 transition-colors duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] active:scale-[0.98]"
          >
            <div className="h-8 w-8 rounded-full bg-gradient-to-br from-[#0A77FF] to-indigo-600 text-white flex items-center justify-center shadow-xs shrink-0">
              <User className="h-4 w-4 stroke-[2]" />
            </div>
            <span className="hidden sm:block text-xs font-semibold text-slate-700 dark:text-slate-200 max-w-[160px] truncate">
              {displayName}
            </span>
            <ChevronDown
              className={`h-3.5 w-3.5 text-slate-400 transition-transform duration-150 shrink-0 ${
                menuOpen ? "rotate-180" : ""
              }`}
            />
          </button>

          {/* Sub-menu Popover */}
          {menuOpen && (
            <div
              role="menu"
              aria-orientation="vertical"
              className="absolute right-0 mt-2 w-56 origin-top-right rounded-2xl bg-white dark:bg-slate-900 p-1.5 shadow-[0_12px_32px_-4px_rgba(15,23,42,0.12),0_2px_6px_-1px_rgba(15,23,42,0.06)] ring-1 ring-slate-200/90 dark:ring-slate-800 z-50 animate-in fade-in-0 zoom-in-95 duration-150"
            >
              <div className="px-3 py-2 border-b border-slate-100 dark:border-slate-800/80 mb-1">
                <p className="text-xs font-semibold text-slate-900 dark:text-white truncate">
                  {displayName}
                </p>
                <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">
                  {displayEmail}
                </p>
              </div>

              <button
                type="button"
                role="menuitem"
                onClick={() => handlePlaceholderClick("Profile")}
                className="w-full flex items-center justify-between rounded-xl px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors cursor-pointer"
              >
                <span className="flex items-center gap-2.5">
                  <User className="h-4 w-4 text-slate-400 stroke-[1.75]" />
                  <span>Profile</span>
                </span>
                <span className="text-[10px] font-mono text-slate-400 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">
                  Soon
                </span>
              </button>

              <button
                type="button"
                role="menuitem"
                onClick={() => handlePlaceholderClick("Settings")}
                className="w-full flex items-center justify-between rounded-xl px-3 py-2 text-xs font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors cursor-pointer"
              >
                <span className="flex items-center gap-2.5">
                  <Settings className="h-4 w-4 text-slate-400 stroke-[1.75]" />
                  <span>Settings</span>
                </span>
                <span className="text-[10px] font-mono text-slate-400 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">
                  Soon
                </span>
              </button>

              <div className="my-1 border-t border-slate-100 dark:border-slate-800/80" />

              <button
                type="button"
                role="menuitem"
                onClick={handleLogout}
                className="w-full flex items-center gap-2.5 rounded-xl px-3 py-2 text-xs font-semibold text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
              >
                <LogOut className="h-4 w-4 stroke-[1.8]" />
                <span>Log out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
