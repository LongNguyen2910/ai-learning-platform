"use client"

import * as React from "react"
import {
  Target,
  Plus,
  Sparkles,
  FileText,
  Clock,
  Trash2,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowLeft,
  ArrowRight,
  RotateCcw,
  BookOpen,
  ChevronDown,
  Check,
  X,
  Play,
  Award,
  RefreshCw,
  AlertCircle,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { DocumentItem } from "@/lib/api/documents"
import type { SubjectItem } from "@/lib/api/roadmaps"
import {
  fetchQuizzes,
  generateQuiz,
  deleteQuiz,
  type QuizItem,
} from "@/lib/api/quizzes"
import { ChatMarkdownRenderer } from "@/components/dashboard/chat-markdown-renderer"

export type QuizMode = "practice" | "exam"

interface QuizWorkspaceProps {
  documents: DocumentItem[]
  subjects: SubjectItem[]
  onOpenDocumentAtPage: (documentId: string, pageNumber: number) => void
  onSwitchToDocuments?: () => void
}

interface StoredAttemptSummary {
  bestScore: number
  lastScore: number
  attemptsCount: number
  totalQuestions: number
  lastAttemptAt: string
}

const ATTEMPTS_STORAGE_KEY = "ai_learning_quiz_attempts_v1"

function loadAttemptSummaries(): Record<string, StoredAttemptSummary> {
  if (typeof window === "undefined") return {}
  try {
    const raw = localStorage.getItem(ATTEMPTS_STORAGE_KEY)
    if (!raw) return {}
    return JSON.parse(raw) as Record<string, StoredAttemptSummary>
  } catch {
    return {}
  }
}

function saveAttemptSummary(
  quizId: string,
  score: number,
  total: number,
  incrementAttemptCount: boolean
) {
  if (typeof window === "undefined") return
  try {
    const current = loadAttemptSummaries()
    const prev = current[quizId]
    const prevCount = prev?.attemptsCount ?? (prev ? 1 : 0)
    current[quizId] = {
      bestScore: prev ? Math.max(prev.bestScore, score) : score,
      lastScore: score,
      attemptsCount: incrementAttemptCount
        ? prevCount + 1
        : Math.max(1, prevCount),
      totalQuestions: total,
      lastAttemptAt: new Date().toISOString(),
    }
    localStorage.setItem(ATTEMPTS_STORAGE_KEY, JSON.stringify(current))
  } catch {
    // Ignore storage quota errors
  }
}

function computeBloomPreview(n: number) {
  const remember = Math.round(n * 0.4)
  const understand = Math.round(n * 0.4)
  const apply = Math.max(1, n - remember - understand)
  return { remember, understand, apply }
}

function formatTimer(totalSeconds: number): string {
  const clamped = Math.max(0, totalSeconds)
  const mins = Math.floor(clamped / 60)
  const secs = clamped % 60
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
}

export function QuizWorkspace({
  documents,
  subjects,
  onOpenDocumentAtPage,
  onSwitchToDocuments,
}: QuizWorkspaceProps) {
  // Library state (Phase 1)
  const [quizzes, setQuizzes] = React.useState<QuizItem[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  const [subjectFilter, setSubjectFilter] = React.useState<
    "all" | "uncategorized" | string
  >("all")
  const [deletingQuizId, setDeletingQuizId] = React.useState<string | null>(null)
  const [attemptSummaries, setAttemptSummaries] = React.useState<
    Record<string, StoredAttemptSummary>
  >({})

  // AI Generator Modal state
  const [isCreateModalOpen, setIsCreateModalOpen] = React.useState(false)
  const [selectedDocId, setSelectedDocId] = React.useState<string>("")
  const [isDocDropdownOpen, setIsDocDropdownOpen] = React.useState(false)
  const [numQuestions, setNumQuestions] = React.useState<number>(5)
  const [pageStart, setPageStart] = React.useState<number>(1)
  const [pageEnd, setPageEnd] = React.useState<number>(1)
  const [topicTag, setTopicTag] = React.useState<string>("")
  const [customTitle, setCustomTitle] = React.useState<string>("")
  const [initialLaunchMode, setInitialLaunchMode] =
    React.useState<QuizMode>("practice")
  const [isGenerating, setIsGenerating] = React.useState(false)
  const [generateError, setGenerateError] = React.useState<string | null>(null)

  const docDropdownRef = React.useRef<HTMLDivElement | null>(null)
  const filterScrollRef = React.useRef<HTMLDivElement | null>(null)

  // Active Quiz Session state (Phase 2)
  const [activeQuiz, setActiveQuiz] = React.useState<QuizItem | null>(null)
  const [quizMode, setQuizMode] = React.useState<QuizMode>("practice")
  const [currentQuestionIdx, setCurrentQuestionIdx] = React.useState<number>(0)
  const [selectedAnswers, setSelectedAnswers] = React.useState<
    Record<string, string>
  >({})
  const [isSubmitted, setIsSubmitted] = React.useState<boolean>(false)
  const [remainingSeconds, setRemainingSeconds] = React.useState<number>(15 * 60)
  const [elapsedSeconds, setElapsedSeconds] = React.useState<number>(0)

  // Tracks whether the current active session has already incremented attemptsCount
  const hasCountedSessionRef = React.useRef<boolean>(false)

  const readyDocuments = React.useMemo(
    () =>
      documents.filter(
        (d) => d.status === "ready" || d.status === "parsed"
      ),
    [documents]
  )

  const selectedDocForModal = React.useMemo(
    () =>
      readyDocuments.find((d) => d.document_id === selectedDocId) ||
      readyDocuments[0] ||
      null,
    [readyDocuments, selectedDocId]
  )

  // Sync default selected document in modal
  React.useEffect(() => {
    if (!selectedDocId && readyDocuments.length > 0) {
      const firstDoc = readyDocuments[0]
      setSelectedDocId(firstDoc.document_id)
      setPageStart(1)
      setPageEnd(Math.max(1, firstDoc.total_pages))
    }
  }, [readyDocuments, selectedDocId])

  // Close custom document dropdown on outside click
  React.useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (
        docDropdownRef.current &&
        !docDropdownRef.current.contains(e.target as Node)
      ) {
        setIsDocDropdownOpen(false)
      }
    }
    document.addEventListener("mousedown", handleOutside)
    return () => document.removeEventListener("mousedown", handleOutside)
  }, [])

  // Horizontal wheel scroll for subject filter bar
  React.useEffect(() => {
    const el = filterScrollRef.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (el.scrollWidth > el.clientWidth && Math.abs(e.deltaY) > 0) {
        e.preventDefault()
        el.scrollLeft += e.deltaY
      }
    }
    el.addEventListener("wheel", onWheel, { passive: false })
    return () => el.removeEventListener("wheel", onWheel)
  }, [subjects.length, activeQuiz])

  const loadQuizzes = React.useCallback(async () => {
    setIsLoading(true)
    setErrorMessage(null)
    try {
      const list = await fetchQuizzes()
      setQuizzes(list)
      setAttemptSummaries(loadAttemptSummaries())
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Could not load quizzes."
      )
    } finally {
      setIsLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void loadQuizzes()
  }, [loadQuizzes])

  // Session timer in Phase 2 (Exam mode countdown + elapsed time tracking)
  React.useEffect(() => {
    if (!activeQuiz || isSubmitted) return
    if (
      quizMode === "practice" &&
      activeQuiz.questions.length > 0 &&
      Object.keys(selectedAnswers).length === activeQuiz.questions.length
    ) {
      return
    }

    const interval = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1)
      if (quizMode === "exam") {
        setRemainingSeconds((prev) => {
          if (prev <= 1) {
            return 0
          }
          return prev - 1
        })
      }
    }, 1000)

    return () => clearInterval(interval)
  }, [activeQuiz, isSubmitted, quizMode, selectedAnswers])

  const computeCorrectCount = React.useCallback(
    (quiz: QuizItem, answers: Record<string, string>) => {
      let correctCount = 0
      for (const q of quiz.questions) {
        const chosen = answers[q.id]
        if (
          chosen &&
          chosen.trim().toUpperCase() === q.correct_option.trim().toUpperCase()
        ) {
          correctCount += 1
        }
      }
      return correctCount
    },
    []
  )

  // Submit handler for Exam mode
  const handleSubmitQuiz = React.useCallback(() => {
    if (!activeQuiz) return
    const correctCount = computeCorrectCount(activeQuiz, selectedAnswers)
    setIsSubmitted(true)
    saveAttemptSummary(
      activeQuiz.id,
      correctCount,
      activeQuiz.questions.length,
      !hasCountedSessionRef.current
    )
    hasCountedSessionRef.current = true
    setAttemptSummaries(loadAttemptSummaries())
  }, [activeQuiz, selectedAnswers, computeCorrectCount])

  // Auto-submit when exam timer hits 0
  React.useEffect(() => {
    if (
      activeQuiz &&
      quizMode === "exam" &&
      !isSubmitted &&
      remainingSeconds === 0
    ) {
      handleSubmitQuiz()
    }
  }, [activeQuiz, quizMode, isSubmitted, remainingSeconds, handleSubmitQuiz])

  const handleStartQuiz = React.useCallback(
    (quiz: QuizItem, mode: QuizMode) => {
      hasCountedSessionRef.current = false
      setActiveQuiz(quiz)
      setQuizMode(mode)
      setCurrentQuestionIdx(0)
      setSelectedAnswers({})
      setIsSubmitted(false)
      setRemainingSeconds((quiz.time_limit_minutes || 15) * 60)
      setElapsedSeconds(0)
    },
    []
  )

  const handleReturnToLibrary = React.useCallback(() => {
    setActiveQuiz(null)
  }, [])

  const handleSelectDocumentInModal = (doc: DocumentItem) => {
    setSelectedDocId(doc.document_id)
    setPageStart(1)
    setPageEnd(Math.max(1, doc.total_pages))
    setIsDocDropdownOpen(false)
    setGenerateError(null)
  }

  const handleGenerateQuiz = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedDocForModal) {
      setGenerateError("Please select a ready document.")
      return
    }

    const maxPages = Math.max(1, selectedDocForModal.total_pages)
    const cleanStart = Math.max(1, Math.min(pageStart || 1, maxPages))
    const cleanEnd = Math.max(cleanStart, Math.min(pageEnd || maxPages, maxPages))

    setIsGenerating(true)
    setGenerateError(null)

    try {
      const created = await generateQuiz({
        document_id: selectedDocForModal.document_id,
        num_questions: numQuestions,
        page_start: cleanStart,
        page_end: cleanEnd,
        topic_tag: topicTag.trim() || null,
        title: customTitle.trim() || null,
      })

      setQuizzes((prev) => [
        created,
        ...prev.filter((q) => q.id !== created.id),
      ])
      setIsCreateModalOpen(false)
      setTopicTag("")
      setCustomTitle("")
      handleStartQuiz(created, initialLaunchMode)
    } catch (err) {
      setGenerateError(
        err instanceof Error
          ? err.message
          : "An error occurred while generating the quiz."
      )
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDeleteQuiz = async (quizId: string) => {
    setDeletingQuizId(quizId)
    try {
      await deleteQuiz(quizId)
      setQuizzes((prev) => prev.filter((q) => q.id !== quizId))
      if (activeQuiz?.id === quizId) {
        setActiveQuiz(null)
      }
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Could not delete quiz."
      )
    } finally {
      setDeletingQuizId(null)
    }
  }

  const documentMap = React.useMemo(() => {
    const map = new Map<string, DocumentItem>()
    for (const d of documents) {
      map.set(d.document_id, d)
    }
    return map
  }, [documents])

  const subjectMap = React.useMemo(() => {
    const map = new Map<string, SubjectItem>()
    for (const s of subjects) {
      map.set(s.id, s)
    }
    return map
  }, [subjects])

  const resolveQuizSubjectId = React.useCallback(
    (q: QuizItem): string | null => {
      if (q.subject_id) return q.subject_id
      const doc = documentMap.get(q.document_id)
      return doc?.subject_id ?? null
    },
    [documentMap]
  )

  const filteredQuizzes = React.useMemo(() => {
    if (subjectFilter === "all") return quizzes
    if (subjectFilter === "uncategorized") {
      return quizzes.filter((q) => !resolveQuizSubjectId(q))
    }
    return quizzes.filter((q) => resolveQuizSubjectId(q) === subjectFilter)
  }, [quizzes, subjectFilter, resolveQuizSubjectId])

  const uncategorizedCount = React.useMemo(
    () => quizzes.filter((q) => !resolveQuizSubjectId(q)).length,
    [quizzes, resolveQuizSubjectId]
  )

  // ============================================================================
  // PHASE 2: DEDICATED QUIZ SESSION & RESULTS SCREEN
  // ============================================================================
  if (activeQuiz) {
    const questions = activeQuiz.questions || []
    const totalQ = questions.length
    const safeIdx = Math.min(Math.max(0, currentQuestionIdx), Math.max(0, totalQ - 1))
    const currentQuestion = questions[safeIdx]
    const sourceDoc = documentMap.get(activeQuiz.document_id)

    const answeredCount = Object.keys(selectedAnswers).length
    const currentChosenOption = currentQuestion
      ? selectedAnswers[currentQuestion.id]
      : undefined

    // Whether the current question reveals correctness & explanation immediately
    const isCurrentRevealed =
      isSubmitted || (quizMode === "practice" && Boolean(currentChosenOption))

    // Score & Bloom breakdown calculation
    const stats = (() => {
      let correct = 0
      const bloomTotals: Record<"remember" | "understand" | "apply", { correct: number; total: number }> = {
        remember: { correct: 0, total: 0 },
        understand: { correct: 0, total: 0 },
        apply: { correct: 0, total: 0 },
      }

      for (const q of questions) {
        const levelKey = (
          ["remember", "understand", "apply"].includes(
            q.bloom_level?.toLowerCase()
          )
            ? q.bloom_level.toLowerCase()
            : "understand"
        ) as "remember" | "understand" | "apply"

        bloomTotals[levelKey].total += 1
        const chosen = selectedAnswers[q.id]
        const isCorrect =
          Boolean(chosen) &&
          chosen.trim().toUpperCase() === q.correct_option.trim().toUpperCase()

        if (isCorrect) {
          correct += 1
          bloomTotals[levelKey].correct += 1
        }
      }

      const percent = totalQ > 0 ? Math.round((correct / totalQ) * 100) : 0
      return { correct, totalQ, percent, bloomTotals }
    })()

    const handleSelectOption = (optionKey: string) => {
      if (!currentQuestion || isSubmitted) return
      // In practice mode, once an option is chosen for a question, lock that question so immediate feedback stays honest
      if (quizMode === "practice" && selectedAnswers[currentQuestion.id]) {
        return
      }
      const nextAnswers = {
        ...selectedAnswers,
        [currentQuestion.id]: optionKey,
      }
      setSelectedAnswers(nextAnswers)

      // In practice mode, ONLY record the attempt once ALL questions have been answered
      if (
        quizMode === "practice" &&
        totalQ > 0 &&
        Object.keys(nextAnswers).length === totalQ
      ) {
        const correctCount = computeCorrectCount(activeQuiz, nextAnswers)
        saveAttemptSummary(
          activeQuiz.id,
          correctCount,
          totalQ,
          !hasCountedSessionRef.current
        )
        hasCountedSessionRef.current = true
        setAttemptSummaries(loadAttemptSummaries())
      }
    }

    const isPracticeCompleted =
      quizMode === "practice" && totalQ > 0 && answeredCount === totalQ
    const showSummaryBanner = isSubmitted || isPracticeCompleted
    const isLowTime =
      quizMode === "exam" && !isSubmitted && remainingSeconds <= 60

    return (
      <div className="flex-1 min-h-0 flex flex-col bg-[#F8FAFC] dark:bg-slate-950 overflow-hidden">
        {/* Session Top Bar */}
        <div className="h-16 border-b border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 px-6 flex items-center justify-between gap-4 shrink-0">
          {/* Left: Quiz Title & Source Document (Back to Quizzes button removed from top bar) */}
          <div className="min-w-0">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white truncate">
              {activeQuiz.title}
            </h2>
            {sourceDoc && (
              <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate">
                Document: {sourceDoc.title}
              </p>
            )}
          </div>

          {/* Right: Mode-Specific Controls */}
          <div className="flex items-center gap-3 shrink-0">
            {quizMode === "practice" ? (
              <>
                <span className="hidden sm:inline-flex items-center gap-1.5 rounded-xl bg-slate-100 dark:bg-slate-800/80 px-3 h-9 text-xs font-semibold text-slate-600 dark:text-slate-300">
                  <BookOpen className="h-3.5 w-3.5 text-[#0A77FF] stroke-[2]" />
                  <span>Practice Mode</span>
                </span>

                {answeredCount > 0 && (
                  <button
                    type="button"
                    onClick={() => handleStartQuiz(activeQuiz, "practice")}
                    className="h-9 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer active:scale-[0.98]"
                  >
                    <RotateCcw className="h-3.5 w-3.5 stroke-[2]" />
                    <span>Retry</span>
                  </button>
                )}
              </>
            ) : (
              <>
                <div
                  className={cn(
                    "h-9 px-3 rounded-xl border inline-flex items-center gap-2 text-xs font-mono font-semibold tabular-nums",
                    isLowTime
                      ? "border-rose-300 bg-rose-50 text-rose-600 dark:border-rose-900 dark:bg-rose-950/50 dark:text-rose-400 animate-pulse"
                      : "border-slate-200/80 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-700 dark:text-slate-300"
                  )}
                >
                  <Clock className="h-3.5 w-3.5 stroke-[2]" />
                  <span>{formatTimer(remainingSeconds)}</span>
                </div>

                {!isSubmitted ? (
                  <button
                    type="button"
                    onClick={handleSubmitQuiz}
                    className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-[0_2px_10px_rgba(10,119,255,0.25)] transition-all cursor-pointer active:scale-[0.98]"
                  >
                    <CheckCircle2 className="h-3.5 w-3.5 stroke-[2]" />
                    <span>Submit</span>
                    <span className="font-mono text-[11px] opacity-85 tabular-nums">
                      ({answeredCount}/{totalQ})
                    </span>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => handleStartQuiz(activeQuiz, "exam")}
                    className="h-9 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer active:scale-[0.98]"
                  >
                    <RotateCcw className="h-3.5 w-3.5 stroke-[2]" />
                    <span>Retake Quiz</span>
                  </button>
                )}
              </>
            )}
          </div>
        </div>

        {/* Scrollable Session Body */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="max-w-4xl mx-auto space-y-6">
            {/* Summary & Bloom Breakdown */}
            {showSummaryBanner && (
              <section
                aria-label="Quiz results"
                className="rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-xs space-y-5 animate-in fade-in-0 duration-200"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 dark:border-slate-800/80 pb-4">
                  <div className="flex items-center gap-3.5">
                    <div
                      className={cn(
                        "h-12 w-12 rounded-2xl flex items-center justify-center shrink-0",
                        stats.percent >= 80
                          ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                          : stats.percent >= 50
                            ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                            : "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                      )}
                    >
                      <Award className="h-6 w-6 stroke-[2]" />
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                        Assessment Results
                      </p>
                      <div className="flex items-baseline gap-2.5 mt-0.5">
                        <span className="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">
                          {stats.correct} / {stats.totalQ}
                        </span>
                        <span
                          className={cn(
                            "text-sm font-mono font-bold tabular-nums px-2 py-0.5 rounded-md",
                            stats.percent >= 80
                              ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
                              : stats.percent >= 50
                                ? "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300"
                                : "bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300"
                          )}
                        >
                          {stats.percent}% Accuracy
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2.5 flex-wrap text-xs text-slate-500 dark:text-slate-400">
                    {quizMode === "exam" && (
                      <div className="mr-2">
                        <span className="block text-[11px] text-slate-400">
                          Time Spent
                        </span>
                        <span className="font-mono font-semibold text-slate-700 dark:text-slate-200 tabular-nums">
                          {formatTimer(elapsedSeconds)}
                        </span>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => handleStartQuiz(activeQuiz, quizMode)}
                      className="h-9 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <RotateCcw className="h-3.5 w-3.5 stroke-[2]" />
                      <span>Retry</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleReturnToLibrary}
                      className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white font-semibold inline-flex items-center gap-1.5 shadow-[0_2px_10px_rgba(10,119,255,0.25)] transition-colors cursor-pointer"
                    >
                      <ArrowLeft className="h-3.5 w-3.5 stroke-[2]" />
                      <span>Back to Quizzes</span>
                    </button>
                  </div>
                </div>

                {/* 3-Level Bloom Taxonomy Breakdown */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  {(
                    [
                      {
                        key: "remember",
                        label: "Remember",
                        barClass: "bg-sky-500",
                      },
                      {
                        key: "understand",
                        label: "Understand",
                        barClass: "bg-indigo-500",
                      },
                      {
                        key: "apply",
                        label: "Apply",
                        barClass: "bg-amber-500",
                      },
                    ] as const
                  ).map((lvl) => {
                    const item = stats.bloomTotals[lvl.key]
                    const pct =
                      item.total > 0
                        ? Math.round((item.correct / item.total) * 100)
                        : 0
                    return (
                      <div
                        key={lvl.key}
                        className="rounded-xl border border-slate-200/70 dark:border-slate-800/80 bg-slate-50/60 dark:bg-slate-950/60 p-3.5 space-y-2"
                      >
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-semibold text-slate-700 dark:text-slate-200">
                            {lvl.label}
                          </span>
                          <span className="font-mono font-semibold text-slate-600 dark:text-slate-300 tabular-nums">
                            {item.correct}/{item.total}
                          </span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden">
                          <div
                            className={cn(
                              "h-full rounded-full transition-all duration-300",
                              lvl.barClass
                            )}
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
            )}

            {/* Question Palette [1..N] */}
            <div className="flex items-center justify-between gap-3 flex-wrap rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-3.5 shadow-2xs">
              <div className="flex items-center gap-1.5 flex-wrap">
                {questions.map((q, idx) => {
                  const chosen = selectedAnswers[q.id]
                  const isCurrent = idx === safeIdx
                  const isRevealedForBtn =
                    isSubmitted || (quizMode === "practice" && Boolean(chosen))
                  const isCorrectBtn =
                    Boolean(chosen) &&
                    chosen.trim().toUpperCase() ===
                      q.correct_option.trim().toUpperCase()

                  let btnStyle =
                    "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-transparent hover:bg-slate-200/80 dark:hover:bg-slate-700"
                  if (isRevealedForBtn) {
                    btnStyle = isCorrectBtn
                      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40"
                      : "bg-rose-500/15 text-rose-700 dark:text-rose-300 border-rose-500/40"
                  } else if (chosen) {
                    btnStyle =
                      "bg-[#0A77FF]/15 text-[#0A77FF] dark:text-sky-300 border-[#0A77FF]/40"
                  }

                  return (
                    <button
                      key={q.id}
                      type="button"
                      onClick={() => setCurrentQuestionIdx(idx)}
                      className={cn(
                        "h-9 w-9 rounded-xl border text-xs font-mono font-bold tabular-nums transition-all cursor-pointer flex items-center justify-center",
                        btnStyle,
                        isCurrent &&
                          "ring-2 ring-[#0A77FF] ring-offset-2 dark:ring-offset-slate-900"
                      )}
                    >
                      {idx + 1}
                    </button>
                  )
                })}
              </div>

              <span className="text-xs font-mono text-slate-400 dark:text-slate-500 tabular-nums">
                Answered {answeredCount}/{totalQ}
              </span>
            </div>

            {/* Active Question Card */}
            {currentQuestion && (
              <div className="rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-xs space-y-6">
                {/* Question Header: ONLY question index as requested */}
                <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800/80 pb-3.5">
                  <span className="text-xs font-mono font-bold uppercase tracking-wider text-[#0A77FF] dark:text-sky-400 tabular-nums">
                    Question {safeIdx + 1} / {totalQ}
                  </span>
                </div>

                {/* Question Stem */}
                <div className="text-[15px] font-medium text-slate-900 dark:text-slate-100 leading-relaxed">
                  <ChatMarkdownRenderer content={currentQuestion.question_text} />
                </div>

                {/* 4 Options (A, B, C, D) */}
                <div className="space-y-2.5">
                  {currentQuestion.options.map((opt) => {
                    const isSelected = currentChosenOption === opt.key
                    const isCorrectOpt =
                      opt.key.trim().toUpperCase() ===
                      currentQuestion.correct_option.trim().toUpperCase()

                    let optionStyle =
                      "border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-[#0A77FF]/50 hover:bg-slate-50/70 dark:hover:bg-slate-800/50"
                    let badgeStyle =
                      "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300"

                    if (isCurrentRevealed) {
                      if (isCorrectOpt) {
                        optionStyle =
                          "border-emerald-500/70 bg-emerald-50/60 dark:bg-emerald-950/30 dark:border-emerald-500/50"
                        badgeStyle = "bg-emerald-600 text-white"
                      } else if (isSelected && !isCorrectOpt) {
                        optionStyle =
                          "border-rose-500/70 bg-rose-50/60 dark:bg-rose-950/30 dark:border-rose-500/50"
                        badgeStyle = "bg-rose-600 text-white"
                      } else {
                        optionStyle =
                          "border-slate-200/60 dark:border-slate-800/60 opacity-65"
                      }
                    } else if (isSelected) {
                      optionStyle =
                        "border-[#0A77FF] bg-[#0A77FF]/[0.06] dark:bg-[#0A77FF]/15 ring-1 ring-[#0A77FF]"
                      badgeStyle = "bg-[#0A77FF] text-white"
                    }

                    return (
                      <button
                        key={opt.key}
                        type="button"
                        disabled={isCurrentRevealed}
                        onClick={() => handleSelectOption(opt.key)}
                        className={cn(
                          "w-full text-left rounded-xl border p-4 flex items-start gap-3.5 transition-all duration-150 cursor-pointer disabled:cursor-default",
                          optionStyle
                        )}
                      >
                        <span
                          className={cn(
                            "h-7 w-7 rounded-lg font-mono text-xs font-bold flex items-center justify-center shrink-0 mt-0.5 transition-colors",
                            badgeStyle
                          )}
                        >
                          {opt.key}
                        </span>

                        <div className="flex-1 min-w-0 text-sm text-slate-800 dark:text-slate-200 leading-relaxed">
                          <ChatMarkdownRenderer content={opt.text} />
                        </div>

                        {isCurrentRevealed && isCorrectOpt && (
                          <CheckCircle2 className="h-5 w-5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-1" />
                        )}
                        {isCurrentRevealed && isSelected && !isCorrectOpt && (
                          <XCircle className="h-5 w-5 text-rose-600 dark:text-rose-400 shrink-0 mt-1" />
                        )}
                      </button>
                    )
                  })}
                </div>

                {/* Explanation & PDF Target Page Jump */}
                {isCurrentRevealed && (
                  <div
                    className={cn(
                      "rounded-xl border p-4 space-y-2.5 animate-in fade-in-0 duration-150",
                      currentChosenOption &&
                        currentChosenOption.trim().toUpperCase() ===
                          currentQuestion.correct_option.trim().toUpperCase()
                        ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-900/60 dark:bg-emerald-950/25"
                        : "border-amber-200 bg-amber-50/50 dark:border-amber-900/60 dark:bg-amber-950/25"
                    )}
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="text-xs font-bold text-slate-800 dark:text-slate-200">
                        Explanation (Correct Answer: {currentQuestion.correct_option})
                      </span>

                      {currentQuestion.target_page && (
                        <button
                          type="button"
                          onClick={() =>
                            onOpenDocumentAtPage(
                              activeQuiz.document_id,
                              currentQuestion.target_page!
                            )
                          }
                          className="h-7 px-2.5 rounded-lg bg-[#0A77FF]/10 hover:bg-[#0A77FF]/20 text-[#0A77FF] dark:bg-[#0A77FF]/25 dark:text-sky-300 text-xs font-mono font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer tabular-nums"
                        >
                          <BookOpen className="h-3.5 w-3.5 stroke-[2]" />
                          <span>Page {currentQuestion.target_page}</span>
                        </button>
                      )}
                    </div>

                    {currentQuestion.explanation && (
                      <div className="text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed">
                        <ChatMarkdownRenderer
                          content={currentQuestion.explanation}
                        />
                      </div>
                    )}
                  </div>
                )}

                {/* Question Card Footer Navigation */}
                <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-800/80">
                  <button
                    type="button"
                    disabled={safeIdx === 0}
                    onClick={() =>
                      setCurrentQuestionIdx((prev) => Math.max(0, prev - 1))
                    }
                    className="h-9 px-3.5 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 inline-flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <ArrowLeft className="h-3.5 w-3.5 stroke-[2]" />
                    <span>Previous</span>
                  </button>

                  {safeIdx < totalQ - 1 ? (
                    <button
                      type="button"
                      onClick={() =>
                        setCurrentQuestionIdx((prev) =>
                          Math.min(totalQ - 1, prev + 1)
                        )
                      }
                      className="h-9 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-200 text-white dark:text-slate-900 text-xs font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <span>Next Question</span>
                      <ArrowRight className="h-3.5 w-3.5 stroke-[2]" />
                    </button>
                  ) : quizMode === "exam" && !isSubmitted ? (
                    <button
                      type="button"
                      onClick={handleSubmitQuiz}
                      className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-[0_2px_10px_rgba(10,119,255,0.25)] transition-colors cursor-pointer"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5 stroke-[2]" />
                      <span>Submit Quiz</span>
                    </button>
                  ) : showSummaryBanner ? (
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleStartQuiz(activeQuiz, quizMode)}
                        className="h-9 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer"
                      >
                        <RotateCcw className="h-3.5 w-3.5 stroke-[2]" />
                        <span>Retry</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleReturnToLibrary}
                        className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-[0_2px_10px_rgba(10,119,255,0.25)] transition-colors cursor-pointer"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5 stroke-[2]" />
                        <span>Finish & Back to Quizzes</span>
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs font-mono text-slate-400 dark:text-slate-500 tabular-nums">
                      Answer all questions to finish ({answeredCount}/{totalQ})
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ============================================================================
  // PHASE 1: QUIZ LIBRARY + AI QUIZ GENERATOR MODAL
  // ============================================================================
  const bloomPreview = computeBloomPreview(numQuestions)

  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-8">
      <div className="max-w-5xl w-full min-w-0 mx-auto space-y-7">
        {/* Top Heading + Primary Action */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Quizzes & Assessments
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
              Generate Bloom-aligned multiple-choice quizzes from your PDF
              textbooks with direct page citations.
            </p>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            <button
              type="button"
              onClick={() => void loadQuizzes()}
              aria-label="Refresh quiz list"
              title="Refresh"
              className="h-10 px-3 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-2 transition-colors cursor-pointer active:scale-[0.98]"
            >
              <RefreshCw
                className={cn(
                  "h-3.5 w-3.5 stroke-[1.8]",
                  isLoading && "animate-spin"
                )}
              />
              <span className="hidden sm:inline">Refresh</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setGenerateError(null)
                setIsCreateModalOpen(true)
              }}
              className="h-10 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs sm:text-sm font-semibold inline-flex items-center gap-2 shadow-[0_4px_14px_rgba(10,119,255,0.28)] transition-all cursor-pointer active:scale-[0.98]"
            >
              <Plus className="h-4 w-4 stroke-[2.2]" />
              <span>Generate AI Quiz</span>
            </button>
          </div>
        </div>

        {/* Subject Filter Bar */}
        <div
          ref={filterScrollRef}
          role="tablist"
          aria-label="Filter quizzes by subject"
          className="w-full min-w-0 flex items-center gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        >
          <button
            type="button"
            role="tab"
            aria-selected={subjectFilter === "all"}
            onClick={() => setSubjectFilter("all")}
            className={cn(
              "h-8 px-3 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 shrink-0 transition-colors cursor-pointer tabular-nums",
              subjectFilter === "all"
                ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                : "bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
            )}
          >
            <span>All</span>
            <span
              className={cn(
                "font-mono text-[11px]",
                subjectFilter === "all" ? "text-white/85" : "text-slate-400"
              )}
            >
              ({quizzes.length})
            </span>
          </button>

          {subjects.map((subj) => {
            const count = quizzes.filter(
              (q) => resolveQuizSubjectId(q) === subj.id
            ).length
            const isActive = subjectFilter === subj.id
            return (
              <button
                key={subj.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setSubjectFilter(subj.id)}
                className={cn(
                  "h-8 px-3 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 shrink-0 transition-colors cursor-pointer tabular-nums",
                  isActive
                    ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                    : "bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                )}
              >
                <span className="truncate max-w-[160px]">{subj.name}</span>
                <span
                  className={cn(
                    "font-mono text-[11px]",
                    isActive ? "text-white/85" : "text-slate-400"
                  )}
                >
                  ({count})
                </span>
              </button>
            )
          })}

          {uncategorizedCount > 0 && (
            <button
              type="button"
              role="tab"
              aria-selected={subjectFilter === "uncategorized"}
              onClick={() => setSubjectFilter("uncategorized")}
              className={cn(
                "h-8 px-3 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 shrink-0 transition-colors cursor-pointer tabular-nums",
                subjectFilter === "uncategorized"
                  ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                  : "bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
              )}
            >
              <span>Uncategorized</span>
              <span
                className={cn(
                  "font-mono text-[11px]",
                  subjectFilter === "uncategorized"
                    ? "text-white/85"
                    : "text-slate-400"
                )}
              >
                ({uncategorizedCount})
              </span>
            </button>
          )}
        </div>

        {/* Error Alert */}
        {errorMessage && (
          <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/70 dark:bg-rose-950/30 p-4 flex items-center justify-between gap-3 text-xs text-rose-700 dark:text-rose-300">
            <div className="flex items-center gap-2.5">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
            <button
              type="button"
              onClick={() => void loadQuizzes()}
              className="font-semibold underline cursor-pointer shrink-0"
            >
              Retry
            </button>
          </div>
        )}

        {/* Quiz List or Empty / Loading State */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1, 2, 3, 4].map((n) => (
              <div
                key={n}
                className="h-40 rounded-2xl border border-slate-200/70 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-5 animate-pulse flex flex-col justify-between"
              >
                <div className="space-y-2.5">
                  <div className="h-4 w-2/3 rounded bg-slate-200 dark:bg-slate-800" />
                  <div className="h-3 w-1/2 rounded bg-slate-100 dark:bg-slate-800/70" />
                </div>
                <div className="flex items-center justify-between pt-3">
                  <div className="h-6 w-24 rounded bg-slate-100 dark:bg-slate-800" />
                  <div className="h-8 w-36 rounded-xl bg-slate-200 dark:bg-slate-800" />
                </div>
              </div>
            ))}
          </div>
        ) : filteredQuizzes.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300/90 dark:border-slate-800 bg-white/70 dark:bg-slate-900/50 p-10 text-center space-y-4">
            <div className="h-12 w-12 rounded-2xl bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-400 flex items-center justify-center mx-auto">
              <Target className="h-6 w-6 stroke-[1.8]" />
            </div>
            <div className="space-y-1 max-w-md mx-auto">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                No quizzes generated yet
              </h3>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
                Select an uploaded PDF document to automatically generate
                multiple-choice questions with detailed explanations and page
                references.
              </p>
            </div>
            <div className="pt-1">
              <button
                type="button"
                onClick={() => setIsCreateModalOpen(true)}
                className="h-10 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center gap-2 shadow-[0_4px_12px_rgba(10,119,255,0.25)] transition-all cursor-pointer"
              >
                <Sparkles className="h-4 w-4 stroke-[2]" />
                <span>Create First Quiz</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredQuizzes.map((quiz) => {
              const doc = documentMap.get(quiz.document_id)
              const resolvedSubjId = resolveQuizSubjectId(quiz)
              const subj = resolvedSubjId
                ? subjectMap.get(resolvedSubjId)
                : null
              const attempt = attemptSummaries[quiz.id]
              const isDeleting = deletingQuizId === quiz.id
              const qCount = quiz.questions?.length || quiz.total_questions

              return (
                <article
                  key={quiz.id}
                  className="group rounded-2xl border border-slate-200/85 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-2xs hover:shadow-md hover:border-slate-300 dark:hover:border-slate-700 transition-all flex flex-col justify-between gap-4"
                >
                  <div className="space-y-2.5">
                    <div className="flex items-start justify-between gap-2.5">
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          {subj && (
                            <span className="inline-flex items-center rounded-md bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 px-2 py-0.5 text-[11px] font-semibold text-[#0A77FF] dark:text-sky-300">
                              {subj.name}
                            </span>
                          )}
                          <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-mono font-medium text-slate-600 dark:text-slate-300 tabular-nums">
                            {qCount} {qCount === 1 ? "question" : "questions"}
                          </span>
                          <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-mono font-medium text-slate-600 dark:text-slate-300 tabular-nums">
                            <Clock className="h-3 w-3 stroke-[1.8]" />
                            {quiz.time_limit_minutes}m
                          </span>
                        </div>

                        <h3 className="text-base font-bold text-slate-900 dark:text-white leading-snug line-clamp-2">
                          {quiz.title}
                        </h3>
                      </div>

                      <button
                        type="button"
                        disabled={isDeleting}
                        onClick={() => void handleDeleteQuiz(quiz.id)}
                        aria-label={`Delete quiz ${quiz.title}`}
                        title="Delete quiz"
                        className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer shrink-0"
                      >
                        {isDeleting ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4 stroke-[1.8]" />
                        )}
                      </button>
                    </div>

                    <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                      <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                      <span className="truncate">
                        {doc ? doc.title : "Source Document"}
                      </span>
                    </div>
                  </div>

                  {/* Card Footer: Best Attempt + Launch Modes */}
                  <div className="flex items-center justify-between gap-2 pt-3 border-t border-slate-100 dark:border-slate-800/80">
                    <div>
                      {attempt ? (
                        <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200/70 dark:border-emerald-900/60 px-2.5 py-1 text-xs font-mono font-semibold text-emerald-700 dark:text-emerald-300 tabular-nums">
                          <Award className="h-3.5 w-3.5 stroke-[2]" />
                          <span>
                            {attempt.attemptsCount || 1}{" "}
                            {(attempt.attemptsCount || 1) === 1
                              ? "attempt"
                              : "attempts"}{" "}
                            · Best: {attempt.bestScore}/{attempt.totalQuestions}
                          </span>
                        </span>
                      ) : (
                        <span className="text-[11px] font-mono text-slate-400 dark:text-slate-500">
                          Not attempted yet
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        type="button"
                        onClick={() => handleStartQuiz(quiz, "practice")}
                        className="h-8 px-3 rounded-xl border border-slate-200/90 dark:border-slate-800 bg-slate-50 hover:bg-slate-100 dark:bg-slate-800/70 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer active:scale-[0.98]"
                      >
                        <BookOpen className="h-3.5 w-3.5 stroke-[1.8]" />
                        <span>Practice</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => handleStartQuiz(quiz, "exam")}
                        className="h-8 px-3.5 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-2xs transition-colors cursor-pointer active:scale-[0.98]"
                      >
                        <Play className="h-3 w-3 fill-current" />
                        <span>Exam</span>
                      </button>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </div>

      {/* ========================================================================
          MODAL: AI QUIZ GENERATOR
         ======================================================================== */}
      {isCreateModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-quiz-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/55 backdrop-blur-xs animate-in fade-in-0 duration-150"
        >
          <div className="w-full max-w-lg rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="h-8 w-8 rounded-xl bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-400 flex items-center justify-center">
                  <Sparkles className="h-4 w-4 stroke-[2]" />
                </div>
                <div>
                  <h2
                    id="create-quiz-modal-title"
                    className="text-sm font-bold text-slate-900 dark:text-white"
                  >
                    Generate AI Quiz
                  </h2>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500">
                    Bloom&apos;s Taxonomy distribution (40% Remember · 40%
                    Understand · 20% Apply)
                  </p>
                </div>
              </div>

              <button
                type="button"
                disabled={isGenerating}
                onClick={() => setIsCreateModalOpen(false)}
                aria-label="Close modal"
                className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Body */}
            <form onSubmit={handleGenerateQuiz} className="p-6 space-y-5">
              {readyDocuments.length === 0 ? (
                <div className="rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/70 dark:bg-amber-950/30 p-4 space-y-3 text-xs text-amber-800 dark:text-amber-300">
                  <p className="font-semibold">
                    No ready PDF documents available!
                  </p>
                  <p>
                    Please upload and wait for at least one PDF document to
                    finish processing in the Documents section before generating
                    a quiz.
                  </p>
                  {onSwitchToDocuments && (
                    <button
                      type="button"
                      onClick={() => {
                        setIsCreateModalOpen(false)
                        onSwitchToDocuments()
                      }}
                      className="h-8 px-3 rounded-lg bg-amber-600 text-white font-semibold inline-flex items-center gap-1.5 cursor-pointer"
                    >
                      <FileText className="h-3.5 w-3.5" />
                      <span>Go to Documents</span>
                    </button>
                  )}
                </div>
              ) : (
                <>
                  {/* 1. Custom Document Selector (No native Windows <select> border!) */}
                  <div className="space-y-1.5" ref={docDropdownRef}>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Source Document
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setIsDocDropdownOpen((prev) => !prev)}
                        className="w-full h-10 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 hover:bg-slate-100/80 dark:bg-slate-950 dark:hover:bg-slate-900 flex items-center justify-between gap-2 text-xs font-medium text-slate-900 dark:text-white transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                      >
                        <span className="flex items-center gap-2 min-w-0">
                          <FileText className="h-4 w-4 text-[#0A77FF] shrink-0" />
                          <span className="truncate">
                            {selectedDocForModal
                              ? selectedDocForModal.title
                              : "Select a document..."}
                          </span>
                        </span>
                        <span className="flex items-center gap-2 shrink-0">
                          {selectedDocForModal && (
                            <span className="font-mono text-[11px] text-slate-400 tabular-nums">
                              {selectedDocForModal.total_pages} pages
                            </span>
                          )}
                          <ChevronDown
                            className={cn(
                              "h-4 w-4 text-slate-400 transition-transform",
                              isDocDropdownOpen && "rotate-180"
                            )}
                          />
                        </span>
                      </button>

                      {isDocDropdownOpen && (
                        <div className="absolute left-0 right-0 mt-1.5 max-h-52 overflow-y-auto rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-1 shadow-xl z-30">
                          {readyDocuments.map((doc) => {
                            const isChosen =
                              selectedDocForModal?.document_id ===
                              doc.document_id
                            return (
                              <button
                                key={doc.document_id}
                                type="button"
                                onClick={() => handleSelectDocumentInModal(doc)}
                                className={cn(
                                  "w-full px-3 py-2 rounded-lg text-left text-xs flex items-center justify-between gap-2 transition-colors cursor-pointer",
                                  isChosen
                                    ? "bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300 font-semibold"
                                    : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                                )}
                              >
                                <span className="truncate">{doc.title}</span>
                                <span className="flex items-center gap-1.5 shrink-0 font-mono text-[11px] text-slate-400 tabular-nums">
                                  <span>{doc.total_pages}p</span>
                                  {isChosen && (
                                    <Check className="h-3.5 w-3.5 text-[#0A77FF]" />
                                  )}
                                </span>
                              </button>
                            )
                          })}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* 2. Number of Questions (5..10) + Live Bloom Distribution */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        Number of Questions
                      </label>
                      <span className="text-[11px] font-mono text-slate-400 tabular-nums">
                        {bloomPreview.remember} Remember ·{" "}
                        {bloomPreview.understand} Understand ·{" "}
                        {bloomPreview.apply} Apply
                      </span>
                    </div>
                    <div className="grid grid-cols-6 gap-2">
                      {[5, 6, 7, 8, 9, 10].map((count) => {
                        const active = numQuestions === count
                        return (
                          <button
                            key={count}
                            type="button"
                            onClick={() => setNumQuestions(count)}
                            className={cn(
                              "h-9 rounded-xl border font-mono text-xs font-bold tabular-nums transition-all cursor-pointer",
                              active
                                ? "border-[#0A77FF] bg-[#0A77FF] text-white shadow-2xs"
                                : "border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 text-slate-700 dark:text-slate-300 hover:border-[#0A77FF]/40"
                            )}
                          >
                            {count} Qs
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  {/* 3. Page Range [page_start, page_end] */}
                  {selectedDocForModal && (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                          Page Range (1 –{" "}
                          <span className="font-mono tabular-nums">
                            {selectedDocForModal.total_pages}
                          </span>
                          )
                        </label>
                        <button
                          type="button"
                          onClick={() => {
                            setPageStart(1)
                            setPageEnd(
                              Math.max(1, selectedDocForModal.total_pages)
                            )
                          }}
                          className="text-[11px] font-semibold text-[#0A77FF] hover:underline cursor-pointer"
                        >
                          Full Document
                        </button>
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 h-10">
                          <span className="text-xs text-slate-400 shrink-0">
                            From page
                          </span>
                          <input
                            type="number"
                            min={1}
                            max={Math.max(1, selectedDocForModal.total_pages)}
                            value={pageStart}
                            onChange={(e) =>
                              setPageStart(
                                Math.max(1, parseInt(e.target.value, 10) || 1)
                              )
                            }
                            className="w-full bg-transparent text-right font-mono text-xs font-semibold text-slate-900 dark:text-white focus:outline-none tabular-nums"
                          />
                        </div>
                        <div className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 h-10">
                          <span className="text-xs text-slate-400 shrink-0">
                            To page
                          </span>
                          <input
                            type="number"
                            min={1}
                            max={Math.max(1, selectedDocForModal.total_pages)}
                            value={pageEnd}
                            onChange={(e) =>
                              setPageEnd(
                                Math.max(1, parseInt(e.target.value, 10) || 1)
                              )
                            }
                            className="w-full bg-transparent text-right font-mono text-xs font-semibold text-slate-900 dark:text-white focus:outline-none tabular-nums"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 4. Optional Topic Tag & Custom Title */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                        Focus Topic (Optional)
                      </label>
                      <input
                        type="text"
                        value={topicTag}
                        onChange={(e) => setTopicTag(e.target.value)}
                        placeholder="e.g. CNNs, Decision Trees..."
                        maxLength={100}
                        className="w-full h-10 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                        Quiz Title (Optional)
                      </label>
                      <input
                        type="text"
                        value={customTitle}
                        onChange={(e) => setCustomTitle(e.target.value)}
                        placeholder="Leave blank for AI title..."
                        maxLength={255}
                        className="w-full h-10 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                      />
                    </div>
                  </div>

                  {/* 5. Default Mode Selection on Launch */}
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Launch Mode After Generation
                    </label>
                    <div className="grid grid-cols-2 gap-2.5">
                      <button
                        type="button"
                        onClick={() => setInitialLaunchMode("practice")}
                        className={cn(
                          "h-10 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer",
                          initialLaunchMode === "practice"
                            ? "border-[#0A77FF] bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300"
                            : "border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400"
                        )}
                      >
                        <BookOpen className="h-3.5 w-3.5 stroke-[2]" />
                        <span>Practice (Instant Check)</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => setInitialLaunchMode("exam")}
                        className={cn(
                          "h-10 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer",
                          initialLaunchMode === "exam"
                            ? "border-[#0A77FF] bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300"
                            : "border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400"
                        )}
                      >
                        <Clock className="h-3.5 w-3.5 stroke-[2]" />
                        <span>Exam (Timed Test)</span>
                      </button>
                    </div>
                  </div>

                  {generateError && (
                    <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50 dark:bg-rose-950/40 p-3 text-xs text-rose-700 dark:text-rose-300 flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      <span>{generateError}</span>
                    </div>
                  )}

                  {/* Modal Footer */}
                  <div className="flex items-center justify-end gap-2.5 pt-2">
                    <button
                      type="button"
                      disabled={isGenerating}
                      onClick={() => setIsCreateModalOpen(false)}
                      className="h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                    >
                      Cancel
                    </button>

                    <button
                      type="submit"
                      disabled={isGenerating || !selectedDocForModal}
                      className="h-10 px-5 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center gap-2 shadow-[0_4px_14px_rgba(10,119,255,0.3)] disabled:opacity-60 transition-all cursor-pointer"
                    >
                      {isGenerating ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin" />
                          <span>Generating Quiz...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="h-4 w-4 stroke-[2]" />
                          <span>Generate Quiz</span>
                        </>
                      )}
                    </button>
                  </div>
                </>
              )}
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
