import { Award, Crown, ShieldCheck, Zap, type LucideIcon } from "lucide-react"

export interface StreakMilestoneTier {
  days: number
  title: string
  ringName: string
  description: string
  icon: LucideIcon
  ringClass: string
  previewRingClass: string
  badgeClass: string
  accentTextClass: string
  dotClass: string
}

export const STREAK_MILESTONES: StreakMilestoneTier[] = [
  {
    days: 3,
    title: "Focused Initiate",
    ringName: "Cobalt Pulse Ring",
    description: "Build initial momentum with 3 consecutive days of study.",
    icon: Zap,
    ringClass:
      "ring-2 ring-[#0A77FF] ring-offset-2 ring-offset-white dark:ring-offset-slate-950 shadow-[0_0_12px_rgba(10,119,255,0.28)]",
    previewRingClass:
      "ring-2 ring-[#0A77FF] ring-offset-2 ring-offset-white dark:ring-offset-slate-900 shadow-[0_0_12px_rgba(10,119,255,0.25)]",
    badgeClass:
      "bg-[#0A77FF]/10 text-[#0A77FF] border-[#0A77FF]/25 dark:bg-[#0A77FF]/20 dark:text-sky-300 dark:border-[#0A77FF]/40",
    accentTextClass: "text-[#0A77FF] dark:text-sky-400",
    dotClass: "bg-[#0A77FF]",
  },
  {
    days: 7,
    title: "Consistent Scholar",
    ringName: "Emerald Precision Ring",
    description: "Complete a full 7-day learning cycle without missing a day.",
    icon: ShieldCheck,
    ringClass:
      "ring-2 ring-emerald-500 ring-offset-2 ring-offset-white dark:ring-offset-slate-950 shadow-[0_0_12px_rgba(16,185,129,0.28)]",
    previewRingClass:
      "ring-2 ring-emerald-500 ring-offset-2 ring-offset-white dark:ring-offset-slate-900 shadow-[0_0_12px_rgba(16,185,129,0.25)]",
    badgeClass:
      "bg-emerald-500/10 text-emerald-700 border-emerald-500/25 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-500/40",
    accentTextClass: "text-emerald-600 dark:text-emerald-400",
    dotClass: "bg-emerald-500",
  },
  {
    days: 14,
    title: "Dedicated Researcher",
    ringName: "Amber Tactile Ring",
    description: "Maintain two uninterrupted weeks of active study sessions.",
    icon: Award,
    ringClass:
      "ring-2 ring-amber-500 ring-offset-2 ring-offset-white dark:ring-offset-slate-950 shadow-[0_0_14px_rgba(245,158,11,0.32)]",
    previewRingClass:
      "ring-2 ring-amber-500 ring-offset-2 ring-offset-white dark:ring-offset-slate-900 shadow-[0_0_14px_rgba(245,158,11,0.28)]",
    badgeClass:
      "bg-amber-500/10 text-amber-700 border-amber-500/30 dark:bg-amber-500/20 dark:text-amber-300 dark:border-amber-500/40",
    accentTextClass: "text-amber-600 dark:text-amber-400",
    dotClass: "bg-amber-500",
  },
  {
    days: 30,
    title: "Relentless Master",
    ringName: "Obsidian & Cobalt Halo",
    description: "Achieve mastery discipline across 30 consecutive login days.",
    icon: Crown,
    ringClass:
      "ring-[2.5px] ring-slate-900 dark:ring-sky-400 ring-offset-2 ring-offset-[#0A77FF]/25 shadow-[0_0_16px_rgba(10,119,255,0.4)]",
    previewRingClass:
      "ring-[2.5px] ring-slate-900 dark:ring-sky-400 ring-offset-2 ring-offset-[#0A77FF]/25 shadow-[0_0_16px_rgba(10,119,255,0.35)]",
    badgeClass:
      "bg-slate-900 text-white border-slate-800 dark:bg-sky-500/20 dark:text-sky-200 dark:border-sky-400/50",
    accentTextClass: "text-slate-900 dark:text-sky-300",
    dotClass: "bg-slate-900 dark:bg-sky-400",
  },
]

export function getActiveMilestoneTier(
  longestStreak: number,
  equippedMilestone?: number | null
): StreakMilestoneTier | null {
  if (
    equippedMilestone != null &&
    equippedMilestone <= longestStreak
  ) {
    const matched = STREAK_MILESTONES.find((m) => m.days === equippedMilestone)
    if (matched) return matched
  }

  // Fallback to highest unlocked tier if equippedMilestone is unset or locked
  const unlocked = STREAK_MILESTONES.filter((m) => longestStreak >= m.days)
  if (unlocked.length === 0) return null
  return unlocked[unlocked.length - 1]
}

export function getNextMilestoneTier(
  longestStreak: number
): StreakMilestoneTier | null {
  return STREAK_MILESTONES.find((m) => longestStreak < m.days) ?? null
}

export function getLocalDateString(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  const day = String(now.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

export function getYesterdayDateString(): string {
  const d = new Date()
  d.setDate(d.getDate() - 1)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}
