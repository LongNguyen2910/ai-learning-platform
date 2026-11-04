"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  ArrowLeft,
  Sparkles,
  Monitor,
  AlertTriangle,
  Sun,
  Moon,
  Laptop,
  Check,
  Loader2,
  Lock,
  Columns2,
  Clock,
  BookOpen,
  X,
  AlertCircle,
  HelpCircle,
} from "lucide-react"
import {
  loadLearningPreferences,
  saveLearningPreferences,
  loadAppearancePreferences,
  saveAppearancePreferences,
  deleteUserAccount,
  type LearningPreferences,
  type AppearancePreferences,
  type SocraticGuidanceDepth,
  type StudySessionMode,
  type AppTheme,
} from "@/lib/api/settings"

type SettingsTab = "learning" | "appearance" | "danger"

const HOUR_PRESETS = [1.0, 2.0, 3.0, 4.0]

export default function SettingsPage() {
  const router = useRouter()
  const [activeTab, setActiveTab] = React.useState<SettingsTab>("learning")

  // Learning Preferences State
  const [learningPrefs, setLearningPrefs] = React.useState<LearningPreferences>(
    loadLearningPreferences
  )
  const [isSavingLearning, setIsSavingLearning] = React.useState(false)
  const [learningSuccessMsg, setLearningSuccessMsg] = React.useState<string | null>(null)

  // Appearance Preferences State
  const [appearancePrefs, setAppearancePrefs] = React.useState<AppearancePreferences>(
    loadAppearancePreferences
  )
  const [appearanceSuccessMsg, setAppearanceSuccessMsg] = React.useState<string | null>(null)

  // Danger Zone & Modal State
  const [isDeleteModalOpen, setIsDeleteModalOpen] = React.useState(false)
  const [deletePassword, setDeletePassword] = React.useState("")
  const [deleteConfirmationText, setDeleteConfirmationText] = React.useState("")
  const [isDeletingAccount, setIsDeletingAccount] = React.useState(false)
  const [deleteErrorMsg, setDeleteErrorMsg] = React.useState<string | null>(null)

  // Load preferences on client mount
  React.useEffect(() => {
    setLearningPrefs(loadLearningPreferences())
    setAppearancePrefs(loadAppearancePreferences())
  }, [])

  // Handle Save Learning Preferences
  const handleSaveLearning = (e: React.FormEvent) => {
    e.preventDefault()
    setIsSavingLearning(true)
    saveLearningPreferences(learningPrefs)
    setTimeout(() => {
      setIsSavingLearning(false)
      setLearningSuccessMsg("Learning preferences saved successfully.")
      setTimeout(() => setLearningSuccessMsg(null), 3000)
    }, 250)
  }

  // Handle Select Theme
  const handleSelectTheme = (theme: AppTheme) => {
    const updated = { ...appearancePrefs, theme }
    setAppearancePrefs(updated)
    saveAppearancePreferences(updated)
    setAppearanceSuccessMsg("Theme updated successfully.")
    setTimeout(() => setAppearanceSuccessMsg(null), 2500)
  }

  // Handle Select Reader Split Ratio
  const handleSelectSplitRatio = (splitRatio: number) => {
    const updated = { ...appearancePrefs, splitRatio }
    setAppearancePrefs(updated)
    saveAppearancePreferences(updated)
    setAppearanceSuccessMsg("Reader split layout saved.")
    setTimeout(() => setAppearanceSuccessMsg(null), 2500)
  }

  // Handle Permanent Delete Account
  const handleConfirmDeleteAccount = async (e: React.FormEvent) => {
    e.preventDefault()
    setDeleteErrorMsg(null)

    if (deleteConfirmationText.trim() !== "DELETE") {
      setDeleteErrorMsg("Please type DELETE to confirm.")
      return
    }

    if (!deletePassword) {
      setDeleteErrorMsg("Please enter your current password.")
      return
    }

    setIsDeletingAccount(true)
    try {
      await deleteUserAccount({ current_password: deletePassword })

      // Wipe entire client storage on account deletion
      if (typeof window !== "undefined") {
        localStorage.clear()
        sessionStorage.clear()
      }

      router.replace("/login")
      router.refresh()
    } catch (err) {
      setDeleteErrorMsg(
        err instanceof Error ? err.message : "Failed to delete account."
      )
      setIsDeletingAccount(false)
    }
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 bg-[#F8FAFC] dark:bg-slate-950">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Navigation Bar & Header */}
        <div className="space-y-3 border-b border-slate-200/80 dark:border-slate-800/80 pb-5">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-xs font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors cursor-pointer group"
          >
            <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
            <span>Back to Dashboard</span>
          </Link>

          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Application Settings
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-0.5">
              Customize your AI learning preferences, reader appearance, and account data.
            </p>
          </div>
        </div>

        {/* GitHub/Linear Style Sidebar Navigation Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* LEFT SIDEBAR TABS (3 cols) */}
          <nav aria-label="Settings navigation" className="lg:col-span-3 space-y-1">
            <button
              type="button"
              onClick={() => setActiveTab("learning")}
              className={`w-full flex items-center justify-between rounded-xl px-3.5 py-2.5 text-xs font-medium transition-colors cursor-pointer ${
                activeTab === "learning"
                  ? "bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300 font-semibold"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-200"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <Sparkles className="h-4 w-4 stroke-[1.8]" />
                <span>Learning & AI</span>
              </span>
              {activeTab === "learning" && (
                <span className="h-1.5 w-1.5 rounded-full bg-[#0A77FF] dark:bg-sky-400" />
              )}
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("appearance")}
              className={`w-full flex items-center justify-between rounded-xl px-3.5 py-2.5 text-xs font-medium transition-colors cursor-pointer ${
                activeTab === "appearance"
                  ? "bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300 font-semibold"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-200"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <Monitor className="h-4 w-4 stroke-[1.8]" />
                <span>Appearance & Reader</span>
              </span>
              {activeTab === "appearance" && (
                <span className="h-1.5 w-1.5 rounded-full bg-[#0A77FF] dark:bg-sky-400" />
              )}
            </button>

            <div className="pt-3 border-t border-slate-200/60 dark:border-slate-800/60 mt-3" />

            <button
              type="button"
              onClick={() => setActiveTab("danger")}
              className={`w-full flex items-center justify-between rounded-xl px-3.5 py-2.5 text-xs font-medium transition-colors cursor-pointer ${
                activeTab === "danger"
                  ? "bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-400 font-semibold"
                  : "text-slate-500 hover:text-rose-600 hover:bg-rose-50/60 dark:text-slate-400 dark:hover:bg-rose-950/20 dark:hover:text-rose-400"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <AlertTriangle className="h-4 w-4 stroke-[1.8] text-rose-500" />
                <span>Danger Zone</span>
              </span>
              {activeTab === "danger" && (
                <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
              )}
            </button>
          </nav>

          {/* RIGHT CONTENT PANEL (9 cols) */}
          <main className="lg:col-span-9 space-y-6">
            {/* ============================================================== */}
            {/* TAB 1: LEARNING & AI PREFERENCES */}
            {/* ============================================================== */}
            {activeTab === "learning" && (
              <div className="space-y-6 animate-in fade-in-0 duration-150">
                <form onSubmit={handleSaveLearning} className="space-y-6">
                  {/* Card 1: AI Tutor & Socratic Method */}
                  <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-6 shadow-2xs space-y-5">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                        AI Tutor & Socratic Method
                      </h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Configure how the AI Tutor guides you through exercises and core concepts.
                      </p>
                    </div>

                    {/* Socratic Mode Toggle Row */}
                    <div className="flex items-center justify-between p-4 rounded-xl border border-slate-200/70 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/60">
                      <div className="space-y-0.5 max-w-md">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold text-slate-900 dark:text-white">
                            Default Socratic Guidance
                          </span>
                          <span className="rounded bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300 text-[10px] font-mono font-medium px-1.5 py-0.2">
                            Pedagogical
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400">
                          When enabled, AI Tutor asks guiding questions instead of giving direct answers right away.
                        </p>
                      </div>

                      <button
                        type="button"
                        role="switch"
                        aria-checked={learningPrefs.socraticEnabled}
                        onClick={() =>
                          setLearningPrefs((prev) => ({
                            ...prev,
                            socraticEnabled: !prev.socraticEnabled,
                          }))
                        }
                        className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] ${
                          learningPrefs.socraticEnabled
                            ? "bg-[#0A77FF]"
                            : "bg-slate-200 dark:bg-slate-700"
                        }`}
                      >
                        <span
                          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
                            learningPrefs.socraticEnabled
                              ? "translate-x-5"
                              : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>

                    {/* Guidance Depth Radio Group */}
                    <div className="space-y-2 pt-2">
                      <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
                        Socratic Guidance Depth
                      </label>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                        {[
                          {
                            id: "exploratory" as SocraticGuidanceDepth,
                            title: "Exploratory",
                            desc: "Deep conceptual questions from foundational theory",
                          },
                          {
                            id: "balanced" as SocraticGuidanceDepth,
                            title: "Balanced (Default)",
                            desc: "Equilibrium between step-by-step hints and application",
                          },
                          {
                            id: "concise" as SocraticGuidanceDepth,
                            title: "Concise",
                            desc: "Targeted quick clues, moving swiftly to solutions",
                          },
                        ].map((tier) => {
                          const isSelected = learningPrefs.guidanceDepth === tier.id
                          return (
                            <button
                              key={tier.id}
                              type="button"
                              onClick={() =>
                                setLearningPrefs((prev) => ({
                                  ...prev,
                                  guidanceDepth: tier.id,
                                }))
                              }
                              className={`p-3.5 rounded-xl border text-left transition-all cursor-pointer ${
                                isSelected
                                  ? "border-[#0A77FF] bg-[#0A77FF]/[0.05] dark:bg-[#0A77FF]/15 ring-1 ring-[#0A77FF]"
                                  : "border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700"
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-semibold text-slate-900 dark:text-white">
                                  {tier.title}
                                </span>
                                {isSelected && (
                                  <Check className="h-3.5 w-3.5 text-[#0A77FF]" />
                                )}
                              </div>
                              <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-1">
                                {tier.desc}
                              </p>
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  </div>

                  {/* Card 2: Roadmap & Study Pacing */}
                  <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-6 shadow-2xs space-y-5">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                        Roadmap & Study Pacing
                      </h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                        Default time allocations auto-filled when generating new study roadmaps.
                      </p>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                      {/* Daily Hours Budget */}
                      <div className="space-y-2">
                        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
                          Default Daily Study Budget
                        </label>
                        <div className="flex items-center gap-1.5">
                          {HOUR_PRESETS.map((hrs) => (
                            <button
                              key={hrs}
                              type="button"
                              onClick={() =>
                                setLearningPrefs((prev) => ({
                                  ...prev,
                                  dailyBudgetHours: hrs,
                                }))
                              }
                              className={`flex-1 h-9 rounded-lg text-xs font-mono font-medium transition-colors cursor-pointer tabular-nums ${
                                learningPrefs.dailyBudgetHours === hrs
                                  ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                                  : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200"
                              }`}
                            >
                              {hrs} hrs
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Session Mode */}
                      <div className="space-y-2">
                        <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">
                          Default Session Allocation Mode
                        </label>
                        <div className="grid grid-cols-3 gap-1.5">
                          {[
                            { id: "auto" as StudySessionMode, label: "Auto" },
                            { id: "micro" as StudySessionMode, label: "Micro (25m)" },
                            { id: "deep_work" as StudySessionMode, label: "Deep (50m)" },
                          ].map((mode) => (
                            <button
                              key={mode.id}
                              type="button"
                              onClick={() =>
                                setLearningPrefs((prev) => ({
                                  ...prev,
                                  sessionMode: mode.id,
                                }))
                              }
                              className={`h-9 px-1 rounded-lg text-xs font-medium transition-colors cursor-pointer truncate ${
                                learningPrefs.sessionMode === mode.id
                                  ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                                  : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200"
                              }`}
                            >
                              {mode.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {learningSuccessMsg && (
                    <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/80 dark:bg-emerald-950/40 px-3 py-2 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                      <Check className="h-4 w-4 shrink-0" />
                      <span>{learningSuccessMsg}</span>
                    </div>
                  )}

                  <div className="flex justify-end">
                    <button
                      type="submit"
                      disabled={isSavingLearning}
                      className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] disabled:opacity-50 text-white text-xs font-semibold inline-flex items-center gap-1.5 transition-all cursor-pointer active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                    >
                      {isSavingLearning ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Saving...</span>
                        </>
                      ) : (
                        <>
                          <Check className="h-3.5 w-3.5 stroke-[2.2]" />
                          <span>Save Preferences</span>
                        </>
                      )}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* ============================================================== */}
            {/* TAB 2: APPEARANCE & READER PREFERENCES */}
            {/* ============================================================== */}
            {activeTab === "appearance" && (
              <div className="space-y-6 animate-in fade-in-0 duration-150">
                {/* Theme Selector */}
                <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-6 shadow-2xs space-y-4">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      Interface Theme
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                      Select your preferred workspace visual theme.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {[
                      { id: "light" as AppTheme, title: "Light", icon: Sun, desc: "Clean crisp light surfaces" },
                      { id: "dark" as AppTheme, title: "Dark", icon: Moon, desc: "Deep monochrome dark mode" },
                      { id: "system" as AppTheme, title: "System", icon: Laptop, desc: "Sync with OS theme" },
                    ].map((item) => {
                      const Icon = item.icon
                      const isSelected = appearancePrefs.theme === item.id
                      return (
                        <button
                          key={item.id}
                          type="button"
                          onClick={() => handleSelectTheme(item.id)}
                          className={`p-4 rounded-xl border text-left transition-all cursor-pointer ${
                            isSelected
                              ? "border-[#0A77FF] bg-[#0A77FF]/[0.05] dark:bg-[#0A77FF]/15 ring-1 ring-[#0A77FF]"
                              : "border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700"
                          }`}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="h-8 w-8 rounded-lg bg-slate-100 dark:bg-slate-800 flex items-center justify-center text-slate-700 dark:text-slate-300">
                              <Icon className="h-4 w-4 stroke-[1.8]" />
                            </div>
                            {isSelected && (
                              <Check className="h-3.5 w-3.5 text-[#0A77FF]" />
                            )}
                          </div>
                          <span className="block text-xs font-semibold text-slate-900 dark:text-white">
                            {item.title}
                          </span>
                          <span className="block text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                            {item.desc}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Reader Split-View Defaults */}
                <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-6 shadow-2xs space-y-4">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      Document Reader Split Layout
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                      Default screen ratio when opening PDF documents alongside AI Tutor.
                    </p>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {[
                      { ratio: 52, label: "50 : 50 (Balanced)", desc: "Equal room for PDF text & AI chat" },
                      { ratio: 62, label: "60 : 40 (Book Focus)", desc: "Wider canvas for textbooks & diagrams" },
                      { ratio: 42, label: "40 : 60 (Tutor Focus)", desc: "Expanded chat for in-depth Socratic discussion" },
                    ].map((layout) => {
                      const isSelected = Math.abs(appearancePrefs.splitRatio - layout.ratio) < 5
                      return (
                        <button
                          key={layout.ratio}
                          type="button"
                          onClick={() => handleSelectSplitRatio(layout.ratio)}
                          className={`p-3.5 rounded-xl border text-left transition-all cursor-pointer ${
                            isSelected
                              ? "border-[#0A77FF] bg-[#0A77FF]/[0.05] dark:bg-[#0A77FF]/15 ring-1 ring-[#0A77FF]"
                              : "border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-300 dark:hover:border-slate-700"
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-semibold text-slate-900 dark:text-white">
                              {layout.label}
                            </span>
                            {isSelected && (
                              <Check className="h-3.5 w-3.5 text-[#0A77FF]" />
                            )}
                          </div>
                          <p className="text-[11px] text-slate-500 dark:text-slate-400">
                            {layout.desc}
                          </p>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {appearanceSuccessMsg && (
                  <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/80 dark:bg-emerald-950/40 px-3 py-2 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                    <Check className="h-4 w-4 shrink-0" />
                    <span>{appearanceSuccessMsg}</span>
                  </div>
                )}
              </div>
            )}

            {/* ============================================================== */}
            {/* TAB 3: DANGER ZONE */}
            {/* ============================================================== */}
            {activeTab === "danger" && (
              <div className="space-y-6 animate-in fade-in-0 duration-150">
                <div className="rounded-2xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/30 dark:bg-rose-950/20 p-6 shadow-2xs space-y-5">
                  <div className="flex items-start gap-3">
                    <div className="h-9 w-9 rounded-xl bg-rose-100 dark:bg-rose-900/50 text-rose-600 dark:text-rose-400 flex items-center justify-center shrink-0">
                      <AlertTriangle className="h-5 w-5 stroke-[2]" />
                    </div>
                    <div className="space-y-1">
                      <h3 className="text-sm font-semibold text-rose-900 dark:text-rose-200">
                        Permanently Delete Account & Study Data
                      </h3>
                      <p className="text-xs text-rose-700/80 dark:text-rose-300/80 leading-relaxed max-w-2xl">
                        Once you delete your account, there is no going back. All uploaded textbooks, synthesized roadmaps, flashcard decks, quiz attempts, and conversation histories will be immediately erased from our servers.
                      </p>
                    </div>
                  </div>

                  <div className="pt-2 flex justify-start">
                    <button
                      type="button"
                      onClick={() => {
                        setDeletePassword("")
                        setDeleteConfirmationText("")
                        setDeleteErrorMsg(null)
                        setIsDeleteModalOpen(true)
                      }}
                      className="h-9 px-4 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold inline-flex items-center gap-1.5 transition-all cursor-pointer active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500 shadow-2xs"
                    >
                      <AlertTriangle className="h-3.5 w-3.5 stroke-[2]" />
                      <span>Delete Account</span>
                    </button>
                  </div>
                </div>
              </div>
            )}
          </main>
        </div>
      </div>

      {/* ==================================================================== */}
      {/* TWO-LAYER SECURITY MODAL: ACCOUNT DELETION */}
      {/* ==================================================================== */}
      {isDeleteModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in-0 duration-150"
        >
          <div className="w-full max-w-md rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-rose-600 dark:text-rose-400">
                <AlertTriangle className="h-5 w-5 stroke-[2]" />
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  Delete Account Confirmation
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsDeleteModalOpen(false)}
                className="h-8 w-8 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 flex items-center justify-center cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              This action is <strong className="text-rose-600 dark:text-rose-400">irreversible</strong>. Please confirm your credentials below to permanently delete your account and all associated study materials.
            </p>

            <form onSubmit={handleConfirmDeleteAccount} className="space-y-4">
              {/* Layer 1: Current Password */}
              <div className="space-y-1.5">
                <label
                  htmlFor="delete-password-input"
                  className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                >
                  Step 1: Enter your current password
                </label>
                <input
                  id="delete-password-input"
                  type="password"
                  required
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                  placeholder="Your account password"
                  className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                />
              </div>

              {/* Layer 2: Type DELETE */}
              <div className="space-y-1.5">
                <label
                  htmlFor="delete-confirm-input"
                  className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                >
                  Step 2: Type <span className="font-mono font-bold text-rose-600">DELETE</span> to confirm
                </label>
                <input
                  id="delete-confirm-input"
                  type="text"
                  required
                  value={deleteConfirmationText}
                  onChange={(e) => setDeleteConfirmationText(e.target.value)}
                  placeholder="Type DELETE"
                  className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs font-mono text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
                />
              </div>

              {deleteErrorMsg && (
                <div className="rounded-lg border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-3 py-2 text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                  <span>{deleteErrorMsg}</span>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  disabled={isDeletingAccount}
                  onClick={() => setIsDeleteModalOpen(false)}
                  className="h-9 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium cursor-pointer"
                >
                  Cancel
                </button>

                <button
                  type="submit"
                  disabled={
                    isDeletingAccount ||
                    !deletePassword ||
                    deleteConfirmationText.trim() !== "DELETE"
                  }
                  className="h-9 px-4 rounded-xl bg-rose-600 hover:bg-rose-700 disabled:opacity-40 disabled:pointer-events-none text-white text-xs font-semibold inline-flex items-center gap-1.5 transition-all cursor-pointer active:scale-[0.98]"
                >
                  {isDeletingAccount ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      <span>Deleting Account...</span>
                    </>
                  ) : (
                    <>
                      <AlertTriangle className="h-3.5 w-3.5" />
                      <span>Permanently Delete</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
