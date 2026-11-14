"use client"

import * as React from "react"
import { Check, Flame, Loader2, Sparkles, X } from "lucide-react"
import {
  performDailyCheckin,
  type UserProfileResponse,
} from "@/lib/api/profile"
import {
  getLocalDateString,
  getYesterdayDateString,
  STREAK_MILESTONES,
} from "@/lib/streak-milestones"

export interface DailyStreakModalProps {
  isOpen: boolean
  onClose: () => void
  user: UserProfileResponse | null
  onUserUpdated?: (updated: UserProfileResponse) => void
}

function AnimatedTickIcon({
  animate = false,
  className = "h-4 w-4",
}: {
  animate?: boolean
  className?: string
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M5 13l4 4L19 7"
        style={
          animate
            ? {
                strokeDasharray: 24,
                strokeDashoffset: 24,
                animation:
                  "streak-tick-draw 380ms cubic-bezier(0.22, 1, 0.36, 1) 80ms forwards",
              }
            : undefined
        }
      />
    </svg>
  )
}

export function DailyStreakModal({
  isOpen,
  onClose,
  user,
  onUserUpdated,
}: DailyStreakModalProps) {
  const [isCheckingIn, setIsCheckingIn] = React.useState(false)
  const [justCheckedIn, setJustCheckedIn] = React.useState(false)
  const [unlockedMilestoneToday, setUnlockedMilestoneToday] = React.useState<
    number | null
  >(null)
  const [checkinError, setCheckinError] = React.useState<string | null>(null)
  const [dateBounds, setDateBounds] = React.useState<{
    today: string
    yesterday: string
  } | null>(null)

  // Compute local calendar boundaries and reset transient check-in animation state on open
  React.useEffect(() => {
    if (isOpen) {
      setDateBounds({
        today: getLocalDateString(),
        yesterday: getYesterdayDateString(),
      })
      setJustCheckedIn(false)
      setUnlockedMilestoneToday(null)
      setCheckinError(null)
    }
  }, [isOpen])

  // Close on Escape key when modal is open
  React.useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose()
      }
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const todayStr = dateBounds?.today ?? ""
  const yesterdayStr = dateBounds?.yesterday ?? ""
  const checkedInToday =
    Boolean(todayStr) && user?.last_checkin_date === todayStr

  // Effective completed days count before/after today's check-in
  const completedStreak = checkedInToday
    ? user?.current_streak ?? 0
    : Boolean(yesterdayStr) && user?.last_checkin_date === yesterdayStr
      ? user?.current_streak ?? 0
      : 0

  const pendingDay = completedStreak + 1
  const cycleAnchorDay = checkedInToday ? Math.max(1, completedStreak) : pendingDay
  const cycleIndex = Math.floor((cycleAnchorDay - 1) / 7)
  const cycleStartDay = cycleIndex * 7 + 1
  const cycleDays = Array.from({ length: 7 }, (_, i) => cycleStartDay + i)

  const completedInCycle = Math.min(
    7,
    Math.max(0, completedStreak - cycleStartDay + 1)
  )

  const unlockedTierBanner = unlockedMilestoneToday
    ? STREAK_MILESTONES.find((m) => m.days === unlockedMilestoneToday) ?? null
    : null

  const handleCheckInClick = async () => {
    if (checkedInToday || isCheckingIn) return
    setCheckinError(null)
    setIsCheckingIn(true)
    try {
      const checkInDate = dateBounds?.today || getLocalDateString()
      const res = await performDailyCheckin(checkInDate)
      localStorage.setItem("auth_user", JSON.stringify(res.user))
      window.dispatchEvent(new Event("auth-user-updated"))
      onUserUpdated?.(res.user)
      setJustCheckedIn(true)
      setUnlockedMilestoneToday(res.newly_unlocked_milestone)
    } catch (err) {
      setCheckinError(
        err instanceof Error ? err.message : "Could not complete daily check-in."
      )
    } finally {
      setIsCheckingIn(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/55 backdrop-blur-[2px] animate-in fade-in-0 duration-150"
      role="dialog"
      aria-modal="true"
      aria-labelledby="daily-login-modal-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-[0_20px_50px_-12px_rgba(15,23,42,0.25)] animate-in fade-in-0 zoom-in-95 duration-150 ease-out overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header: Daily Login + Flame Icon */}
        <div className="flex items-center justify-between gap-3 px-6 py-4 border-b border-slate-100 dark:border-slate-800/80">
          <div className="flex items-center gap-2.5 min-w-0">
            <div
              className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 transition-colors duration-150 ${
                checkedInToday
                  ? "bg-amber-500/15 text-amber-500 dark:bg-amber-500/20"
                  : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
              }`}
            >
              <Flame
                className={`h-4 w-4 stroke-[2.2] ${
                  checkedInToday ? "fill-amber-500/25" : ""
                }`}
              />
            </div>
            <h2
              id="daily-login-modal-title"
              className="text-base font-bold tracking-tight text-slate-900 dark:text-white"
            >
              Daily Login
            </h2>
            <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-mono font-semibold text-slate-600 dark:text-slate-300 tabular-nums">
              {completedStreak}d streak
            </span>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close daily login dialog"
            className="h-8 w-8 rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-white dark:hover:bg-slate-800 flex items-center justify-center transition-colors duration-150 cursor-pointer active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] shrink-0"
          >
            <X className="h-4 w-4 stroke-[2]" />
          </button>
        </div>

        {/* Body: 7-Day Check-In Cycle + Action Button */}
        <div className="p-6 space-y-5">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                7-Day Check-In Cycle (Days {cycleStartDay}–{cycleStartDay + 6})
              </h3>
              <span className="text-[11px] font-mono text-slate-500 dark:text-slate-400 tabular-nums">
                {completedInCycle}/7 complete
              </span>
            </div>

            <div className="grid grid-cols-7 gap-2">
              {cycleDays.map((dayNum) => {
                const isCompleted = dayNum <= completedStreak
                const isCheckedTodayTile =
                  checkedInToday && dayNum === completedStreak
                const isPendingTodayTile =
                  !checkedInToday && dayNum === pendingDay
                const playJustCheckedAnimation =
                  justCheckedIn && isCheckedTodayTile

                const milestoneForDay = STREAK_MILESTONES.find(
                  (m) => m.days === dayNum
                )
                const DayIcon = milestoneForDay?.icon

                return (
                  <div
                    key={dayNum}
                    style={
                      playJustCheckedAnimation
                        ? {
                            animation:
                              "streak-card-pop 420ms cubic-bezier(0.22, 1, 0.36, 1) forwards",
                          }
                        : undefined
                    }
                    className={`relative rounded-xl border p-2.5 flex flex-col items-center justify-center gap-1.5 transition-colors duration-150 ${
                      isCheckedTodayTile
                        ? "border-[#0A77FF] bg-[#0A77FF]/8 dark:bg-[#0A77FF]/15"
                        : isCompleted
                        ? "border-emerald-500/35 bg-emerald-50/70 dark:bg-emerald-950/30"
                        : isPendingTodayTile
                        ? "border-[#0A77FF] border-dashed bg-[#0A77FF]/[0.04] dark:bg-[#0A77FF]/[0.08]"
                        : milestoneForDay
                        ? "border-amber-400/50 border-dashed bg-amber-50/40 dark:bg-amber-950/15"
                        : "border-slate-200/80 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950/50"
                    }`}
                  >
                    <span
                      className={`text-[10px] font-mono font-semibold tabular-nums ${
                        isCheckedTodayTile || isPendingTodayTile
                          ? "text-[#0A77FF] dark:text-sky-300"
                          : isCompleted
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-slate-500 dark:text-slate-400"
                      }`}
                    >
                      D{dayNum}
                    </span>

                    <div className="relative h-7 w-7 flex items-center justify-center">
                      {playJustCheckedAnimation && (
                        <span
                          style={{
                            animation:
                              "streak-ripple 650ms cubic-bezier(0.16, 1, 0.3, 1) forwards",
                          }}
                          className="pointer-events-none absolute inset-0 rounded-lg bg-[#0A77FF]/45"
                          aria-hidden="true"
                        />
                      )}

                      <div
                        className={`relative h-7 w-7 rounded-lg flex items-center justify-center transition-colors duration-150 ${
                          isCheckedTodayTile
                            ? "bg-[#0A77FF] text-white"
                            : isCompleted
                            ? "bg-emerald-500 text-white"
                            : isPendingTodayTile
                            ? "bg-[#0A77FF]/12 text-[#0A77FF] dark:bg-[#0A77FF]/25 dark:text-sky-300"
                            : milestoneForDay
                            ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                            : "bg-slate-200/70 dark:bg-slate-800 text-slate-400"
                        }`}
                      >
                        {playJustCheckedAnimation ? (
                          <AnimatedTickIcon animate className="h-3.5 w-3.5" />
                        ) : isCompleted ? (
                          DayIcon ? (
                            <DayIcon className="h-3.5 w-3.5 stroke-[2.2]" />
                          ) : (
                            <Check className="h-3.5 w-3.5 stroke-[2.5]" />
                          )
                        ) : DayIcon ? (
                          <DayIcon className="h-3.5 w-3.5 stroke-[2]" />
                        ) : (
                          <span
                            className={`h-1.5 w-1.5 rounded-full bg-current ${
                              isPendingTodayTile ? "animate-pulse" : ""
                            }`}
                          />
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {unlockedTierBanner && (
            <div className="rounded-xl border border-emerald-500/30 bg-emerald-50/80 dark:bg-emerald-950/30 px-3.5 py-2.5 flex items-center gap-2.5 animate-in fade-in-0 slide-in-from-bottom-1 duration-150">
              <Sparkles className="h-4 w-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
              <p className="text-xs font-semibold text-emerald-900 dark:text-emerald-200">
                Milestone unlocked: {unlockedTierBanner.title} ({unlockedTierBanner.ringName})
              </p>
            </div>
          )}

          {checkinError && (
            <p className="text-xs text-rose-600 dark:text-rose-400 text-center">
              {checkinError}
            </p>
          )}

          {/* Bottom Check-In Button */}
          <button
            type="button"
            disabled={checkedInToday || isCheckingIn}
            onClick={() => void handleCheckInClick()}
            style={
              justCheckedIn
                ? {
                    animation:
                      "streak-card-pop 380ms cubic-bezier(0.22, 1, 0.36, 1) forwards",
                  }
                : undefined
            }
            className={`w-full h-11 rounded-xl text-sm font-semibold inline-flex items-center justify-center gap-2 transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] ${
              checkedInToday
                ? "border border-emerald-500/30 bg-emerald-50 dark:bg-emerald-950/35 text-emerald-700 dark:text-emerald-300 cursor-not-allowed"
                : "bg-[#0A77FF] hover:bg-[#0866DF] text-white shadow-[0_6px_18px_rgba(10,119,255,0.28)] cursor-pointer active:scale-[0.98] disabled:opacity-60"
            }`}
          >
            {isCheckingIn ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Checking In...</span>
              </>
            ) : checkedInToday ? (
              <>
                <span
                  className={`h-5 w-5 rounded-full flex items-center justify-center ${
                    justCheckedIn
                      ? "bg-emerald-500 text-white"
                      : "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"
                  }`}
                >
                  <AnimatedTickIcon
                    animate={justCheckedIn}
                    className="h-3.5 w-3.5"
                  />
                </span>
                <span>Checked In Today</span>
              </>
            ) : (
              <>
                <Check className="h-4 w-4 stroke-[2.5]" />
                <span>Check In Today</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
