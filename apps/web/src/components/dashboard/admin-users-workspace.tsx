"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  Users,
  Zap,
  Database,
  AlertTriangle,
  Search,
  X,
  RefreshCw,
  Shield,
  ShieldAlert,
  Ban,
  CheckCircle2,
  Trash2,
  SlidersHorizontal,
  RotateCcw,
  Flame,
  Loader2,
  Check,
  ArrowUpDown,
} from "lucide-react"
import {
  AdminApiError,
  deleteAdminUser,
  fetchAdminUsers,
  updateAdminUser,
  type AdminUserItem,
  type AdminUsersSummary,
} from "@/lib/api/admin"
import { resolveAvatarUrl, type UserProfileResponse } from "@/lib/api/profile"

type StatusFilter = "all" | "active" | "suspended" | "admin"
type SortOption = "created_at" | "tokens_today" | "tokens_total"

const QUOTA_PRESETS = [25_000, 50_000, 100_000, 250_000]

function formatJoinDate(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      year: "numeric",
    }).format(new Date(iso))
  } catch {
    return iso.slice(0, 10)
  }
}

export function AdminUsersWorkspace() {
  const router = useRouter()

  const [currentUserId, setCurrentUserId] = React.useState<string | null>(null)
  const [summary, setSummary] = React.useState<AdminUsersSummary | null>(null)
  const [users, setUsers] = React.useState<AdminUserItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [isRefreshing, setIsRefreshing] = React.useState(false)
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null)
  const [isForbidden, setIsForbidden] = React.useState(false)

  // Search, Filter & Sort State
  const [searchInput, setSearchInput] = React.useState("")
  const [debouncedSearch, setDebouncedSearch] = React.useState("")
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all")
  const [sortBy, setSortBy] = React.useState<SortOption>("created_at")

  // Row Mutation & Inline Quota Editor State
  const [mutatingUserId, setMutatingUserId] = React.useState<string | null>(null)
  const [editingQuotaUserId, setEditingQuotaUserId] = React.useState<
    string | null
  >(null)
  const [quotaInputValue, setQuotaInputValue] = React.useState("")
  const [actionNotice, setActionNotice] = React.useState<string | null>(null)

  // Delete Confirmation Modal State
  const [deleteTarget, setDeleteTarget] = React.useState<AdminUserItem | null>(
    null
  )
  const [isDeleting, setIsDeleting] = React.useState(false)

  React.useEffect(() => {
    const syncCurrentUser = () => {
      try {
        const raw = localStorage.getItem("auth_user")
        if (raw) {
          const parsed = JSON.parse(raw) as UserProfileResponse
          setCurrentUserId(parsed?.id ?? null)
        }
      } catch {
        // Ignore invalid JSON
      }
    }

    syncCurrentUser()
    window.addEventListener("auth-user-updated", syncCurrentUser)
    return () => {
      window.removeEventListener("auth-user-updated", syncCurrentUser)
    }
  }, [])

  React.useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim())
    }, 220)
    return () => clearTimeout(timer)
  }, [searchInput])

  const loadUsers = React.useCallback(
    async (silent = false) => {
      if (!silent) {
        setIsLoading(true)
      } else {
        setIsRefreshing(true)
      }
      setErrorMsg(null)
      setIsForbidden(false)

      try {
        const data = await fetchAdminUsers({
          search: debouncedSearch || undefined,
          status_filter: statusFilter,
          sort_by: sortBy,
        })
        setSummary(data.summary)
        setUsers(data.users)
      } catch (err) {
        if (err instanceof AdminApiError) {
          if (err.status === 401) {
            localStorage.removeItem("auth_token")
            localStorage.removeItem("auth_user")
            router.replace("/login")
            return
          }
          if (err.status === 403) {
            setIsForbidden(true)
            setErrorMsg(err.message)
            return
          }
        }
        setErrorMsg(
          err instanceof Error
            ? err.message
            : "Failed to load users."
        )
      } finally {
        setIsLoading(false)
        setIsRefreshing(false)
      }
    },
    [debouncedSearch, router, sortBy, statusFilter]
  )

  React.useEffect(() => {
    void loadUsers(summary !== null)
  }, [loadUsers])

  const showNotice = (msg: string) => {
    setActionNotice(msg)
    setTimeout(() => {
      setActionNotice((prev) => (prev === msg ? null : prev))
    }, 3000)
  }

  const handleToggleLock = async (user: AdminUserItem) => {
    if (mutatingUserId) return
    setMutatingUserId(user.id)
    setErrorMsg(null)
    try {
      await updateAdminUser(user.id, { is_active: !user.is_active })
      await loadUsers(true)
      showNotice(
        user.is_active
          ? `Suspended account ${user.email}.`
          : `Reactivated account ${user.email}.`
      )
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Failed to update account status."
      )
    } finally {
      setMutatingUserId(null)
    }
  }

  const handleToggleUserRole = async (user: AdminUserItem) => {
    if (mutatingUserId) return
    if (user.role === "admin") {
      setErrorMsg("Cannot demote another Administrator.")
      return
    }
    if (!user.is_active) {
      setErrorMsg(
        "Cannot promote a suspended account to Admin. Please unlock the account first."
      )
      return
    }
    const nextRole = "admin"
    setMutatingUserId(user.id)
    setErrorMsg(null)
    try {
      await updateAdminUser(user.id, { role: nextRole })
      await loadUsers(true)
      showNotice(`Promoted ${user.email} to Admin.`)
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Failed to update user role."
      )
    } finally {
      setMutatingUserId(null)
    }
  }

  const handleSaveQuota = async (user: AdminUserItem, customLimit?: number) => {
    const parsedLimit =
      customLimit !== undefined ? customLimit : Number(quotaInputValue)
    if (!Number.isFinite(parsedLimit) || parsedLimit < 0) {
      setErrorMsg("Daily token limit must be a non-negative integer.")
      return
    }
    setMutatingUserId(user.id)
    setErrorMsg(null)
    try {
      await updateAdminUser(user.id, {
        daily_token_limit: Math.round(parsedLimit),
      })
      setEditingQuotaUserId(null)
      await loadUsers(true)
      showNotice(
        `Updated daily token limit for ${user.email} to ${Math.round(
          parsedLimit
        ).toLocaleString()} tokens.`
      )
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Failed to update daily token limit."
      )
    } finally {
      setMutatingUserId(null)
    }
  }

  const handleResetTodayTokens = async (user: AdminUserItem) => {
    setMutatingUserId(user.id)
    setErrorMsg(null)
    try {
      await updateAdminUser(user.id, { reset_today_tokens: true })
      setEditingQuotaUserId(null)
      await loadUsers(true)
      showNotice(`Reset today's token usage for ${user.email} to 0.`)
    } catch (err) {
      setErrorMsg(
        err instanceof Error
          ? err.message
          : "Failed to reset today's token usage."
      )
    } finally {
      setMutatingUserId(null)
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget || isDeleting) return
    setIsDeleting(true)
    setErrorMsg(null)
    try {
      await deleteAdminUser(deleteTarget.id)
      const deletedEmail = deleteTarget.email
      setDeleteTarget(null)
      await loadUsers(true)
      showNotice(`Permanently deleted account ${deletedEmail}.`)
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Failed to delete user account."
      )
    } finally {
      setIsDeleting(false)
    }
  }

  if (isForbidden) {
    return (
      <div className="flex-1 overflow-y-auto px-6 py-12 bg-[#F8FAFC] dark:bg-slate-950 flex items-center justify-center">
        <div className="max-w-md w-full rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-7 text-center shadow-xs space-y-4">
          <div className="mx-auto h-12 w-12 rounded-2xl bg-rose-50 dark:bg-rose-950/50 border border-rose-200/70 dark:border-rose-900/60 text-rose-600 dark:text-rose-400 flex items-center justify-center">
            <ShieldAlert className="h-6 w-6 stroke-[1.8]" />
          </div>
          <div className="space-y-1.5">
            <span className="inline-block rounded-md bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider">
              403 Restricted Access
            </span>
            <h2 className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">
              Administrator Access Required
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Your current account does not have Administrator privileges to view and manage user accounts. You can enable Admin Access Mode in Settings for testing.
            </p>
          </div>
          <div className="flex items-center justify-center gap-2.5 pt-2">
            <Link
              href="/settings"
              className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] text-white text-xs font-semibold inline-flex items-center gap-1.5 transition-colors"
            >
              <span>Open Settings</span>
            </Link>
            <Link
              href="/dashboard"
              className="h-9 px-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 text-xs font-medium inline-flex items-center transition-colors"
            >
              Back to Dashboard
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-7 bg-[#F8FAFC] dark:bg-slate-950">
      <div className="max-w-6xl w-full min-w-0 mx-auto space-y-6">
        {/* Page Heading + Refresh */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-[#0A77FF]/25 bg-[#0A77FF]/8 px-2.5 py-0.5 text-[11px] font-semibold text-[#0A77FF] dark:text-sky-300">
              <Shield className="h-3 w-3 stroke-[2]" />
              <span>Admin Console</span>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              User Accounts &amp; Token Governance
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
              Search user accounts, monitor real-time AI token consumption, configure daily quotas, and manage account access.
            </p>
          </div>

          <button
            type="button"
            disabled={isLoading || isRefreshing}
            onClick={() => void loadUsers(true)}
            className="h-9 px-3.5 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-2 transition-colors cursor-pointer shrink-0 active:scale-[0.98] disabled:opacity-60"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 stroke-[1.8] ${
                isLoading || isRefreshing ? "animate-spin" : ""
              }`}
            />
            <span>Refresh</span>
          </button>
        </div>

        {/* 4-Card KPI Summary Strip */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
          {isLoading && !summary ? (
            Array.from({ length: 4 }).map((_, idx) => (
              <div
                key={idx}
                className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 space-y-2.5 animate-pulse"
              >
                <div className="h-3 w-24 rounded bg-slate-200 dark:bg-slate-800" />
                <div className="h-7 w-20 rounded bg-slate-200 dark:bg-slate-800" />
                <div className="h-3 w-32 rounded bg-slate-100 dark:bg-slate-800/60" />
              </div>
            ))
          ) : (
            <>
              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 shadow-2xs space-y-1.5">
                <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                  <span className="text-xs font-medium">Total Accounts</span>
                  <Users className="h-4 w-4 text-[#0A77FF] stroke-[1.8]" />
                </div>
                <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">
                  {(summary?.total_users ?? 0).toLocaleString()}
                </div>
                <p className="text-[11px] font-mono tabular-nums text-slate-500 dark:text-slate-400">
                  {summary?.active_users ?? 0} active ·{" "}
                  <span
                    className={
                      (summary?.suspended_users ?? 0) > 0
                        ? "text-rose-600 dark:text-rose-400 font-semibold"
                        : ""
                    }
                  >
                    {summary?.suspended_users ?? 0} suspended
                  </span>
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 shadow-2xs space-y-1.5">
                <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                  <span className="text-xs font-medium">Tokens Used Today</span>
                  <Zap className="h-4 w-4 text-amber-500 stroke-[1.8]" />
                </div>
                <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">
                  {(summary?.total_tokens_today ?? 0).toLocaleString()}
                </div>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  Consumed today (UTC)
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 shadow-2xs space-y-1.5">
                <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                  <span className="text-xs font-medium">Cumulative Tokens</span>
                  <Database className="h-4 w-4 text-indigo-500 stroke-[1.8]" />
                </div>
                <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">
                  {(summary?.total_tokens_all_time ?? 0).toLocaleString()}
                </div>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  All-time platform AI token usage
                </p>
              </div>

              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 shadow-2xs space-y-1.5">
                <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                  <span className="text-xs font-medium">
                    Near Daily Limit (&ge;80%)
                  </span>
                  <AlertTriangle
                    className={`h-4 w-4 stroke-[1.8] ${
                      (summary?.near_limit_users ?? 0) > 0
                        ? "text-rose-500"
                        : "text-emerald-500"
                    }`}
                  />
                </div>
                <div className="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">
                  {(summary?.near_limit_users ?? 0).toLocaleString()}
                </div>
                <p className="text-[11px] text-slate-500 dark:text-slate-400">
                  Accounts at or above 80% of daily quota
                </p>
              </div>
            </>
          )}
        </div>

        {/* Alerts & Action Feedback */}
        {errorMsg && (
          <div
            role="alert"
            className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-4 py-3 text-xs text-rose-700 dark:text-rose-300 flex items-center justify-between gap-3"
          >
            <span>{errorMsg}</span>
            <button
              type="button"
              onClick={() => void loadUsers(true)}
              className="h-7 px-2.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-[11px] font-semibold shrink-0 cursor-pointer"
            >
              Retry
            </button>
          </div>
        )}

        {actionNotice && (
          <div
            role="status"
            className="rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/80 dark:bg-emerald-950/40 px-4 py-2.5 text-xs text-emerald-700 dark:text-emerald-300 flex items-center gap-2 animate-in fade-in-0 duration-150"
          >
            <Check className="h-4 w-4 shrink-0" />
            <span>{actionNotice}</span>
          </div>
        )}

        {/* Toolbar: Search + Status Filter Pills + Sort */}
        <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-3.5 shadow-2xs flex flex-col lg:flex-row lg:items-center justify-between gap-3">
          <div className="relative flex-1 min-w-0 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search by user name or email..."
              aria-label="Search users by name or email"
              className="h-9 w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-[#F8FAFC] dark:bg-slate-950 pl-9 pr-8 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:border-[#0A77FF] focus:bg-white dark:focus:bg-slate-950 focus:outline-none focus:ring-2 focus:ring-[#0A77FF]/15 transition-colors"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => setSearchInput("")}
                aria-label="Clear search query"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 cursor-pointer"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-between lg:justify-end gap-2">
            {/* Status Filter Pills */}
            <div
              role="tablist"
              aria-label="Filter accounts by status"
              className="flex items-center gap-1 flex-wrap"
            >
              {(
                [
                  {
                    id: "all",
                    label: "All",
                    count: summary?.total_users,
                  },
                  {
                    id: "active",
                    label: "Active",
                    count: summary?.active_users,
                  },
                  {
                    id: "suspended",
                    label: "Suspended",
                    count: summary?.suspended_users,
                  },
                  {
                    id: "admin",
                    label: "Admins",
                    count: summary?.admin_users,
                  },
                ] as const
              ).map((tab) => {
                const isActive = statusFilter === tab.id
                return (
                  <button
                    key={tab.id}
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    onClick={() => setStatusFilter(tab.id)}
                    className={`h-8 px-3 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 transition-colors cursor-pointer tabular-nums ${
                      isActive
                        ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                        : "bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-300 hover:bg-slate-200/80 dark:hover:bg-slate-800"
                    }`}
                  >
                    <span>{tab.label}</span>
                    {tab.count !== undefined && (
                      <span
                        className={`font-mono text-[11px] ${
                          isActive ? "text-white/85" : "text-slate-400"
                        }`}
                      >
                        ({tab.count})
                      </span>
                    )}
                  </button>
                )
              })}
            </div>

            {/* Sort Selector */}
            <div className="relative flex items-center">
              <ArrowUpDown className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 pointer-events-none" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortOption)}
                aria-label="Sort users"
                className="h-8 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 pl-8 pr-3 text-xs font-medium text-slate-700 dark:text-slate-200 focus:border-[#0A77FF] focus:outline-none cursor-pointer"
              >
                <option value="created_at">Newest registered</option>
                <option value="tokens_today">Highest tokens today</option>
                <option value="tokens_total">Highest cumulative tokens</option>
              </select>
            </div>
          </div>
        </div>

        {/* High-Density Operational Users Table */}
        <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 shadow-2xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 dark:border-slate-800/80 bg-slate-50/70 dark:bg-slate-950/60 text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  <th className="py-3 px-4">User</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 min-w-[240px]">
                    Today / Daily Quota
                  </th>
                  <th className="py-3 px-4">Total Tokens &amp; Activity</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800/80 text-xs">
                {isLoading && users.length === 0 ? (
                  Array.from({ length: 5 }).map((_, idx) => (
                    <tr key={idx} className="animate-pulse">
                      <td className="py-3.5 px-4">
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-full bg-slate-200 dark:bg-slate-800 shrink-0" />
                          <div className="space-y-1.5">
                            <div className="h-3.5 w-32 rounded bg-slate-200 dark:bg-slate-800" />
                            <div className="h-3 w-44 rounded bg-slate-100 dark:bg-slate-800/60" />
                          </div>
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="h-5 w-20 rounded-full bg-slate-200 dark:bg-slate-800" />
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="space-y-1.5">
                          <div className="h-3 w-28 rounded bg-slate-200 dark:bg-slate-800" />
                          <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800/60" />
                        </div>
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="space-y-1.5">
                          <div className="h-3.5 w-24 rounded bg-slate-200 dark:bg-slate-800" />
                          <div className="h-3 w-28 rounded bg-slate-100 dark:bg-slate-800/60" />
                        </div>
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <div className="inline-block h-7 w-32 rounded-lg bg-slate-200 dark:bg-slate-800" />
                      </td>
                    </tr>
                  ))
                ) : users.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-12 px-4 text-center">
                      <div className="max-w-xs mx-auto space-y-2.5">
                        <Users className="h-8 w-8 text-slate-300 dark:text-slate-700 mx-auto stroke-[1.6]" />
                        <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                          No matching accounts found
                        </p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                          Try adjusting your search query or resetting the status filter.
                        </p>
                        {(searchInput || statusFilter !== "all") && (
                          <button
                            type="button"
                            onClick={() => {
                              setSearchInput("")
                              setStatusFilter("all")
                            }}
                            className="h-8 px-3 rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 cursor-pointer"
                          >
                            Reset filters
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : (
                  users.map((user) => {
                    const isSelf = currentUserId === user.id
                    const isTargetAdmin = user.role === "admin"
                    const isMutating = mutatingUserId === user.id
                    const isEditingQuota = editingQuotaUserId === user.id
                    const displayName =
                      user.full_name?.trim() || user.email.split("@")[0]
                    const avatar = resolveAvatarUrl(user.avatar_url)

                    const limit = Math.max(user.daily_token_limit, 0)
                    const pct =
                      limit > 0
                        ? Math.min(
                            100,
                            Math.round((user.used_token_today / limit) * 100)
                          )
                        : 0

                    const barColor =
                      pct >= 95
                        ? "bg-rose-500"
                        : pct >= 75
                          ? "bg-amber-500"
                          : "bg-emerald-500"

                    return (
                      <tr
                        key={user.id}
                        className={`transition-colors hover:bg-slate-50/70 dark:hover:bg-slate-800/35 ${
                          !user.is_active
                            ? "bg-rose-50/25 dark:bg-rose-950/10"
                            : ""
                        }`}
                      >
                        {/* 1. User Identity */}
                        <td className="py-3.5 px-4 align-top">
                          <div className="flex items-start gap-3">
                            <div className="h-9 w-9 rounded-full bg-[#0A77FF] text-white flex items-center justify-center font-bold text-xs shrink-0 overflow-hidden">
                              {avatar ? (
                                <img
                                  src={avatar}
                                  alt={displayName}
                                  className="h-full w-full object-cover"
                                />
                              ) : (
                                displayName.charAt(0).toUpperCase()
                              )}
                            </div>
                            <div className="min-w-0 space-y-0.5">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-semibold text-slate-900 dark:text-white truncate max-w-[180px]">
                                  {displayName}
                                </span>
                                {user.role === "admin" && (
                                  <span className="inline-flex items-center gap-0.5 rounded-md bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300 px-1.5 py-0.5 text-[10px] font-semibold">
                                    <Shield className="h-2.5 w-2.5" />
                                    Admin
                                  </span>
                                )}
                                {isSelf && (
                                  <span className="rounded-md bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300 px-1.5 py-0.5 text-[10px] font-semibold">
                                    You
                                  </span>
                                )}
                                <span
                                  title="Current login streak"
                                  className="inline-flex items-center gap-0.5 rounded-md bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200/70 dark:border-amber-900/50 px-1.5 py-0.5 text-[10px] font-mono tabular-nums"
                                >
                                  <Flame className="h-2.5 w-2.5" />
                                  {user.current_streak}d
                                </span>
                              </div>
                              <p className="font-mono text-[11px] text-slate-500 dark:text-slate-400 truncate max-w-[230px]">
                                {user.email}
                              </p>
                              <p className="text-[10px] text-slate-400 dark:text-slate-500">
                                Joined {formatJoinDate(user.created_at)}
                              </p>
                            </div>
                          </div>
                        </td>

                        {/* 2. Account Status */}
                        <td className="py-3.5 px-4 align-top">
                          {user.is_active ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200/80 dark:border-emerald-900/60 px-2.5 py-1 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-50 dark:bg-rose-950/60 border border-rose-200/80 dark:border-rose-900/60 px-2.5 py-1 text-[11px] font-semibold text-rose-700 dark:text-rose-300">
                              <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
                              Suspended
                            </span>
                          )}
                        </td>

                        {/* 3. Daily Token Usage & Inline Quota Editor */}
                        <td className="py-3.5 px-4 align-top">
                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between gap-2 font-mono tabular-nums text-[11px]">
                              <span className="text-slate-800 dark:text-slate-200 font-semibold">
                                {user.used_token_today.toLocaleString()}
                                <span className="text-slate-400 font-normal">
                                  {" "}
                                  /{" "}
                                  {limit > 0
                                    ? limit.toLocaleString()
                                    : "Unlimited"}
                                </span>
                              </span>
                              {limit > 0 && (
                                <span
                                  className={`text-[10px] font-semibold ${
                                    pct >= 95
                                      ? "text-rose-600 dark:text-rose-400"
                                      : pct >= 75
                                        ? "text-amber-600 dark:text-amber-400"
                                        : "text-slate-500 dark:text-slate-400"
                                  }`}
                                >
                                  {pct}%
                                </span>
                              )}
                            </div>

                            {limit > 0 && (
                              <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                                <div
                                  className={`h-full rounded-full transition-all duration-300 ${barColor}`}
                                  style={{ width: `${pct}%` }}
                                />
                              </div>
                            )}

                            {!isEditingQuota ? (
                              <div className="flex items-center gap-2 pt-0.5">
                                <button
                                  type="button"
                                  disabled={isMutating}
                                  onClick={() => {
                                    setEditingQuotaUserId(user.id)
                                    setQuotaInputValue(
                                      String(user.daily_token_limit)
                                    )
                                  }}
                                  className="text-[11px] font-medium text-[#0A77FF] hover:underline inline-flex items-center gap-1 cursor-pointer disabled:opacity-50"
                                >
                                  <SlidersHorizontal className="h-3 w-3" />
                                  <span>Edit limit</span>
                                </button>
                                {user.used_token_today > 0 && (
                                  <button
                                    type="button"
                                    disabled={isMutating}
                                    onClick={() =>
                                      void handleResetTodayTokens(user)
                                    }
                                    className="text-[11px] font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200 inline-flex items-center gap-1 cursor-pointer disabled:opacity-50"
                                  >
                                    <RotateCcw className="h-3 w-3" />
                                    <span>Reset (0)</span>
                                  </button>
                                )}
                              </div>
                            ) : (
                              <div className="mt-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 p-2.5 space-y-2">
                                <div className="flex items-center gap-1 flex-wrap">
                                  {QUOTA_PRESETS.map((preset) => (
                                    <button
                                      key={preset}
                                      type="button"
                                      onClick={() =>
                                        setQuotaInputValue(String(preset))
                                      }
                                      className={`px-2 py-0.5 rounded-md text-[10px] font-mono cursor-pointer transition-colors ${
                                        Number(quotaInputValue) === preset
                                          ? "bg-[#0A77FF] text-white"
                                          : "bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:border-[#0A77FF]/50"
                                      }`}
                                    >
                                      {preset / 1000}k
                                    </button>
                                  ))}
                                </div>

                                <div className="flex items-center gap-1.5">
                                  <input
                                    type="number"
                                    min={0}
                                    step={1000}
                                    value={quotaInputValue}
                                    onChange={(e) =>
                                      setQuotaInputValue(e.target.value)
                                    }
                                    aria-label={`Daily token limit for ${user.email}`}
                                    className="h-7 w-28 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 text-xs font-mono tabular-nums text-slate-900 dark:text-white focus:border-[#0A77FF] focus:outline-none"
                                  />
                                  <button
                                    type="button"
                                    disabled={isMutating}
                                    onClick={() => void handleSaveQuota(user)}
                                    className="h-7 px-2.5 rounded-lg bg-[#0A77FF] hover:bg-[#0866DF] text-white text-[11px] font-semibold inline-flex items-center gap-1 cursor-pointer disabled:opacity-50"
                                  >
                                    {isMutating ? (
                                      <Loader2 className="h-3 w-3 animate-spin" />
                                    ) : (
                                      <Check className="h-3 w-3" />
                                    )}
                                    <span>Save</span>
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setEditingQuotaUserId(null)}
                                    className="h-7 px-2 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-800 dark:text-slate-400 text-[11px] cursor-pointer"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        </td>

                        {/* 4. Cumulative Tokens & Activity */}
                        <td className="py-3.5 px-4 align-top">
                          <div className="space-y-0.5">
                            <div className="font-mono tabular-nums font-semibold text-slate-900 dark:text-white">
                              {user.total_tokens_used.toLocaleString()}{" "}
                              <span className="text-[11px] font-normal text-slate-400">
                                tokens
                              </span>
                            </div>
                            <p className="font-mono tabular-nums text-[11px] text-slate-500 dark:text-slate-400">
                              {user.documents_count} docs ·{" "}
                              {user.chat_sessions_count} chats
                            </p>
                          </div>
                        </td>

                        {/* 5. Row Actions */}
                        <td className="py-3.5 px-4 align-top text-right">
                          <div className="inline-flex items-center justify-end gap-1.5">
                            <button
                              type="button"
                              disabled={
                                isSelf ||
                                isTargetAdmin ||
                                !user.is_active ||
                                isMutating
                              }
                              onClick={() => void handleToggleUserRole(user)}
                              title={
                                isSelf
                                  ? "Cannot change your own role here"
                                  : isTargetAdmin
                                    ? "Cannot demote another Administrator"
                                    : !user.is_active
                                      ? "Suspended accounts cannot be promoted to Admin (unlock first)"
                                      : "Promote to Administrator"
                              }
                              className="h-8 px-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-[11px] font-medium text-slate-700 dark:text-slate-300 inline-flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              <Shield className="h-3.5 w-3.5 text-indigo-500" />
                              <span>
                                {isTargetAdmin ? "Admin" : "Make Admin"}
                              </span>
                            </button>

                            <button
                              type="button"
                              disabled={
                                isSelf ||
                                (isTargetAdmin && user.is_active) ||
                                isMutating
                              }
                              onClick={() => void handleToggleLock(user)}
                              title={
                                isSelf
                                  ? "Cannot suspend your own account"
                                  : isTargetAdmin && user.is_active
                                    ? "Cannot suspend an Administrator account"
                                    : user.is_active
                                      ? "Suspend this account"
                                      : "Unlock / Reactivate this account"
                              }
                              className={`h-8 px-2.5 rounded-lg text-[11px] font-semibold inline-flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed ${
                                user.is_active
                                  ? "border border-amber-200 dark:border-amber-900/60 bg-amber-50/70 hover:bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:hover:bg-amber-950/70 dark:text-amber-300"
                                  : "bg-emerald-600 hover:bg-emerald-700 text-white"
                              }`}
                            >
                              {isMutating ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : user.is_active ? (
                                <Ban className="h-3.5 w-3.5" />
                              ) : (
                                <CheckCircle2 className="h-3.5 w-3.5" />
                              )}
                              <span>
                                {user.is_active ? "Suspend" : "Unlock"}
                              </span>
                            </button>

                            <button
                              type="button"
                              disabled={isSelf || isTargetAdmin || isMutating}
                              onClick={() => setDeleteTarget(user)}
                              aria-label={`Delete user ${user.email}`}
                              title={
                                isSelf
                                  ? "Cannot delete your own account"
                                  : isTargetAdmin
                                    ? "Cannot delete an Administrator account"
                                    : "Permanently delete account"
                              }
                              className="h-8 w-8 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-rose-50 hover:border-rose-200 hover:text-rose-600 dark:hover:bg-rose-950/40 dark:hover:border-rose-900/60 dark:hover:text-rose-400 text-slate-400 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              <Trash2 className="h-3.5 w-3.5 stroke-[1.9]" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Permanent Delete Confirmation Modal */}
      {deleteTarget && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="admin-delete-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 backdrop-blur-xs p-4 animate-in fade-in-0 duration-150"
        >
          <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-xl space-y-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-xl bg-rose-100 dark:bg-rose-950/60 text-rose-600 dark:text-rose-400 flex items-center justify-center shrink-0">
                  <AlertTriangle className="h-5 w-5" />
                </div>
                <div>
                  <h3
                    id="admin-delete-modal-title"
                    className="text-sm font-bold text-slate-900 dark:text-white"
                  >
                    Confirm Permanent Account Deletion
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    This action cannot be undone.
                  </p>
                </div>
              </div>

              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setDeleteTarget(null)}
                aria-label="Close modal"
                className="h-7 w-7 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-center cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/70 p-3.5 space-y-1.5 text-xs">
              <p className="font-semibold text-slate-900 dark:text-white">
                {deleteTarget.full_name?.trim() || deleteTarget.email}
              </p>
              <p className="font-mono text-[11px] text-slate-500 dark:text-slate-400">
                {deleteTarget.email}
              </p>
              <p className="text-[11px] text-rose-600 dark:text-rose-400 pt-1">
                Will permanently delete all{" "}
                <span className="font-mono font-semibold">
                  {deleteTarget.documents_count}
                </span>{" "}
                documents,{" "}
                <span className="font-mono font-semibold">
                  {deleteTarget.chat_sessions_count}
                </span>{" "}
                chat sessions, roadmaps, quizzes, and flashcards belonging to this user.
              </p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setDeleteTarget(null)}
                className="h-9 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-700 dark:text-slate-200 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => void handleConfirmDelete()}
                className="h-9 px-4 rounded-xl bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white text-xs font-semibold inline-flex items-center gap-1.5 cursor-pointer"
              >
                {isDeleting ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 className="h-3.5 w-3.5" />
                    <span>Delete Permanently</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
