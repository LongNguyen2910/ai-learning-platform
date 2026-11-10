"use client"

import * as React from "react"
import {
  Layers,
  Plus,
  Sparkles,
  FileText,
  Trash2,
  Loader2,
  CheckCircle2,
  ArrowLeft,
  ArrowRight,
  RotateCcw,
  BookOpen,
  ChevronDown,
  Check,
  X,
  Play,
  RefreshCw,
  AlertCircle,
  Pencil,
  Flame,
  Brain,
  SlidersHorizontal,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { DocumentItem } from "@/lib/api/documents"
import type { SubjectItem } from "@/lib/api/roadmaps"
import {
  fetchFlashcardDecks,
  fetchFlashcardDeckDetail,
  createFlashcardDeck,
  generateFlashcardDeck,
  deleteFlashcardDeck,
  createSingleFlashcard,
  updateSingleFlashcard,
  deleteSingleFlashcard,
  reviewFlashcard,
  type FlashcardDeckSummary,
  type FlashcardDeckDetail,
  type FlashcardItem,
  type FlashcardReviewRating,
} from "@/lib/api/flashcards"
import { ChatMarkdownRenderer } from "@/components/dashboard/chat-markdown-renderer"

export type StudySessionMode = "spaced" | "browse"

interface FlashcardWorkspaceProps {
  documents: DocumentItem[]
  subjects: SubjectItem[]
  onOpenDocumentAtPage: (documentId: string, pageNumber: number) => void
  onSwitchToDocuments?: () => void
}

function isCardDue(dueDateIso: string): boolean {
  if (!dueDateIso) return true
  const dueTime = new Date(dueDateIso).getTime()
  if (Number.isNaN(dueTime)) return true
  return dueTime <= Date.now()
}

function formatDueBadge(dueDateIso: string, intervalDays: number): {
  label: string
  isDue: boolean
} {
  if (!dueDateIso) {
    return { label: "Due Today", isDue: true }
  }
  const now = Date.now()
  const due = new Date(dueDateIso).getTime()
  if (Number.isNaN(due) || due <= now) {
    return { label: "Due Today", isDue: true }
  }
  const diffDays = Math.max(1, Math.ceil((due - now) / (1000 * 60 * 60 * 24)))
  return {
    label: `In ${intervalDays > 0 ? intervalDays : diffDays}d`,
    isDue: false,
  }
}

export function FlashcardWorkspace({
  documents,
  subjects,
  onOpenDocumentAtPage,
  onSwitchToDocuments,
}: FlashcardWorkspaceProps) {
  // Phase 1: Deck Library State
  const [decks, setDecks] = React.useState<FlashcardDeckSummary[]>([])
  const [isLoadingDecks, setIsLoadingDecks] = React.useState(true)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  const [subjectFilter, setSubjectFilter] = React.useState<
    "all" | "uncategorized" | string
  >("all")
  const [deletingDeckId, setDeletingDeckId] = React.useState<string | null>(
    null
  )

  // Manual Deck Creation Modal State
  const [isManualDeckModalOpen, setIsManualDeckModalOpen] =
    React.useState(false)
  const [manualDeckTitle, setManualDeckTitle] = React.useState("")
  const [manualDeckDesc, setManualDeckDesc] = React.useState("")
  const [manualDeckSubjectId, setManualDeckSubjectId] =
    React.useState<string>("")
  const [manualDeckDocId, setManualDeckDocId] = React.useState<string>("")
  const [isSavingManualDeck, setIsSavingManualDeck] = React.useState(false)
  const [manualDeckError, setManualDeckError] = React.useState<string | null>(
    null
  )

  // AI Deck Generation Modal State
  const [isGenerateModalOpen, setIsGenerateModalOpen] = React.useState(false)
  const [selectedDocId, setSelectedDocId] = React.useState<string>("")
  const [isDocDropdownOpen, setIsDocDropdownOpen] = React.useState(false)
  const [numCards, setNumCards] = React.useState<number>(8)
  const [pageStart, setPageStart] = React.useState<number>(1)
  const [pageEnd, setPageEnd] = React.useState<number>(1)
  const [customDeckTitle, setCustomDeckTitle] = React.useState<string>("")
  const [isGenerating, setIsGenerating] = React.useState(false)
  const [generateError, setGenerateError] = React.useState<string | null>(null)

  const docDropdownRef = React.useRef<HTMLDivElement | null>(null)
  const filterScrollRef = React.useRef<HTMLDivElement | null>(null)

  // Deck Card Manager Drawer / View State
  const [managingDeck, setManagingDeck] =
    React.useState<FlashcardDeckDetail | null>(null)
  const [isLoadingDeckDetail, setIsLoadingDeckDetail] = React.useState(false)
  const [isAddingCard, setIsAddingCard] = React.useState(false)
  const [newCardFront, setNewCardFront] = React.useState("")
  const [newCardBack, setNewCardBack] = React.useState("")
  const [newCardPage, setNewCardPage] = React.useState<string>("")
  const [isSavingCard, setIsSavingCard] = React.useState(false)
  const [editingCardId, setEditingCardId] = React.useState<string | null>(null)
  const [editFront, setEditFront] = React.useState("")
  const [editBack, setEditBack] = React.useState("")
  const [editPage, setEditPage] = React.useState<string>("")
  const [deletingCardId, setDeletingCardId] = React.useState<string | null>(
    null
  )
  const [cardManagerError, setCardManagerError] = React.useState<string | null>(
    null
  )

  // Phase 2: Dedicated 3D Study Session State
  const [activeStudyDeck, setActiveStudyDeck] =
    React.useState<FlashcardDeckDetail | null>(null)
  const [studyMode, setStudyMode] = React.useState<StudySessionMode>("spaced")
  const [studyQueue, setStudyQueue] = React.useState<FlashcardItem[]>([])
  const [currentCardIndex, setCurrentCardIndex] = React.useState<number>(0)
  const [isFlipped, setIsFlipped] = React.useState<boolean>(false)
  const [isSubmittingReview, setIsSubmittingReview] =
    React.useState<boolean>(false)
  const [sessionStats, setSessionStats] = React.useState<{
    again: number
    hard: number
    good: number
    easy: number
  }>({ again: 0, hard: 0, good: 0, easy: 0 })
  const [isSessionComplete, setIsSessionComplete] =
    React.useState<boolean>(false)

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

  // Default selected document for AI generator modal
  React.useEffect(() => {
    if (!selectedDocId && readyDocuments.length > 0) {
      const first = readyDocuments[0]
      setSelectedDocId(first.document_id)
      setPageStart(1)
      setPageEnd(Math.max(1, first.total_pages))
    }
  }, [readyDocuments, selectedDocId])

  // Close custom dropdown on outside click
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
  }, [subjects.length, activeStudyDeck, managingDeck])

  const loadDecks = React.useCallback(async () => {
    setIsLoadingDecks(true)
    setErrorMessage(null)
    try {
      const list = await fetchFlashcardDecks()
      setDecks(list)
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Could not load flashcard decks."
      )
    } finally {
      setIsLoadingDecks(false)
    }
  }, [])

  React.useEffect(() => {
    void loadDecks()
  }, [loadDecks])

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

  const resolveDeckSubjectId = React.useCallback(
    (deck: FlashcardDeckSummary): string | null => {
      if (deck.subject_id) return deck.subject_id
      if (deck.document_id) {
        const doc = documentMap.get(deck.document_id)
        if (doc?.subject_id) return doc.subject_id
      }
      return null
    },
    [documentMap]
  )

  const filteredDecks = React.useMemo(() => {
    if (subjectFilter === "all") return decks
    if (subjectFilter === "uncategorized") {
      return decks.filter((d) => !resolveDeckSubjectId(d))
    }
    return decks.filter((d) => resolveDeckSubjectId(d) === subjectFilter)
  }, [decks, subjectFilter, resolveDeckSubjectId])

  const uncategorizedCount = React.useMemo(
    () => decks.filter((d) => !resolveDeckSubjectId(d)).length,
    [decks, resolveDeckSubjectId]
  )

  // Global KPI stats across filtered decks
  const kpiStats = React.useMemo(() => {
    let totalCards = 0
    let dueToday = 0
    let mastered = 0
    for (const d of filteredDecks) {
      totalCards += d.total_cards || 0
      dueToday += d.due_count || 0
      mastered += d.mastered_count || 0
    }
    return {
      totalDecks: filteredDecks.length,
      totalCards,
      dueToday,
      mastered,
    }
  }, [filteredDecks])

  // Launch Study Session
  const handleStartStudySession = React.useCallback(
    async (deckId: string, preferredMode?: StudySessionMode) => {
      setErrorMessage(null)
      setIsLoadingDeckDetail(true)
      try {
        const detail = await fetchFlashcardDeckDetail(deckId)
        const allCards = detail.cards || []
        const dueCards = allCards.filter((c) => isCardDue(c.due_date))

        const resolvedMode: StudySessionMode =
          preferredMode ?? (dueCards.length > 0 ? "spaced" : "browse")
        const queue =
          resolvedMode === "spaced" && dueCards.length > 0
            ? dueCards
            : allCards

        setActiveStudyDeck(detail)
        setManagingDeck(null)
        setStudyMode(resolvedMode)
        setStudyQueue(queue)
        setCurrentCardIndex(0)
        setIsFlipped(false)
        setSessionStats({ again: 0, hard: 0, good: 0, easy: 0 })
        setIsSessionComplete(queue.length === 0)
      } catch (err) {
        setErrorMessage(
          err instanceof Error
            ? err.message
            : "Could not load flashcard study session."
        )
      } finally {
        setIsLoadingDeckDetail(false)
      }
    },
    []
  )

  // Switch mode inside active Study Session
  const handleSwitchStudyMode = React.useCallback(
    (nextMode: StudySessionMode) => {
      if (!activeStudyDeck) return
      const allCards = activeStudyDeck.cards || []
      const dueCards = allCards.filter((c) => isCardDue(c.due_date))
      const queue = nextMode === "spaced" ? dueCards : allCards

      setStudyMode(nextMode)
      setStudyQueue(queue)
      setCurrentCardIndex(0)
      setIsFlipped(false)
      setSessionStats({ again: 0, hard: 0, good: 0, easy: 0 })
      setIsSessionComplete(queue.length === 0)
    },
    [activeStudyDeck]
  )

  // Submit SM-2 Rating
  const handleRateCard = React.useCallback(
    async (rating: FlashcardReviewRating) => {
      if (!activeStudyDeck || isSubmittingReview) return
      const currentCard = studyQueue[currentCardIndex]
      if (!currentCard) return

      setIsSubmittingReview(true)
      try {
        const updatedCard = await reviewFlashcard(currentCard.id, rating)

        // Update card inside activeStudyDeck
        setActiveStudyDeck((prev) => {
          if (!prev) return prev
          const updatedCards = prev.cards.map((c) =>
            c.id === updatedCard.id ? updatedCard : c
          )
          return {
            ...prev,
            cards: updatedCards,
          }
        })

        setSessionStats((prev) => ({
          ...prev,
          [rating]: prev[rating] + 1,
        }))

        if (currentCardIndex < studyQueue.length - 1) {
          setIsFlipped(false)
          setCurrentCardIndex((prev) => prev + 1)
        } else {
          setIsSessionComplete(true)
          void loadDecks()
        }
      } catch (err) {
        setErrorMessage(
          err instanceof Error ? err.message : "Failed to save SM-2 rating."
        )
      } finally {
        setIsSubmittingReview(false)
      }
    },
    [
      activeStudyDeck,
      isSubmittingReview,
      studyQueue,
      currentCardIndex,
      loadDecks,
    ]
  )

  // Keyboard shortcuts during Phase 2 Study Session
  React.useEffect(() => {
    if (!activeStudyDeck || isSessionComplete) return

    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return
      }

      if (e.code === "Space") {
        e.preventDefault()
        setIsFlipped((prev) => !prev)
        return
      }

      if (studyMode === "browse") {
        if (e.key === "ArrowLeft") {
          e.preventDefault()
          setIsFlipped(false)
          setCurrentCardIndex((prev) => Math.max(0, prev - 1))
        } else if (e.key === "ArrowRight") {
          e.preventDefault()
          setIsFlipped(false)
          setCurrentCardIndex((prev) =>
            Math.min(studyQueue.length - 1, prev + 1)
          )
        }
      } else if (studyMode === "spaced" && isFlipped && !isSubmittingReview) {
        if (e.key === "1") {
          e.preventDefault()
          void handleRateCard("again")
        } else if (e.key === "2") {
          e.preventDefault()
          void handleRateCard("hard")
        } else if (e.key === "3") {
          e.preventDefault()
          void handleRateCard("good")
        } else if (e.key === "4") {
          e.preventDefault()
          void handleRateCard("easy")
        }
      }
    }

    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [
    activeStudyDeck,
    isSessionComplete,
    studyMode,
    isFlipped,
    isSubmittingReview,
    studyQueue.length,
    handleRateCard,
  ])

  // Open Deck Card Manager
  const handleOpenCardManager = React.useCallback(async (deckId: string) => {
    setErrorMessage(null)
    setCardManagerError(null)
    setIsLoadingDeckDetail(true)
    try {
      const detail = await fetchFlashcardDeckDetail(deckId)
      setManagingDeck(detail)
      setActiveStudyDeck(null)
      setIsAddingCard(false)
      setEditingCardId(null)
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Could not load deck cards."
      )
    } finally {
      setIsLoadingDeckDetail(false)
    }
  }, [])

  const handleCreateManualDeck = async (e: React.FormEvent) => {
    e.preventDefault()
    const cleanTitle = manualDeckTitle.trim()
    if (!cleanTitle) {
      setManualDeckError("Deck title is required.")
      return
    }
    setIsSavingManualDeck(true)
    setManualDeckError(null)
    try {
      const created = await createFlashcardDeck({
        title: cleanTitle,
        description: manualDeckDesc.trim() || null,
        subject_id: manualDeckSubjectId || null,
        document_id: manualDeckDocId || null,
      })
      await loadDecks()
      setIsManualDeckModalOpen(false)
      setManualDeckTitle("")
      setManualDeckDesc("")
      setManagingDeck(created)
      setIsAddingCard(true)
    } catch (err) {
      setManualDeckError(
        err instanceof Error ? err.message : "Could not create deck."
      )
    } finally {
      setIsSavingManualDeck(false)
    }
  }

  const handleGenerateAiDeck = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedDocForModal) {
      setGenerateError("Please select a ready PDF document.")
      return
    }

    const maxPages = Math.max(1, selectedDocForModal.total_pages)
    const cleanStart = Math.max(1, Math.min(pageStart || 1, maxPages))
    const cleanEnd = Math.max(cleanStart, Math.min(pageEnd || maxPages, maxPages))

    setIsGenerating(true)
    setGenerateError(null)

    try {
      const created = await generateFlashcardDeck({
        document_id: selectedDocForModal.document_id,
        num_cards: numCards,
        page_start: cleanStart,
        page_end: cleanEnd,
        title: customDeckTitle.trim() || null,
      })
      await loadDecks()
      setIsGenerateModalOpen(false)
      setCustomDeckTitle("")
      // Immediately launch study session on newly generated deck
      setActiveStudyDeck(created)
      setStudyMode("spaced")
      setStudyQueue(created.cards || [])
      setCurrentCardIndex(0)
      setIsFlipped(false)
      setSessionStats({ again: 0, hard: 0, good: 0, easy: 0 })
      setIsSessionComplete((created.cards || []).length === 0)
    } catch (err) {
      setGenerateError(
        err instanceof Error
          ? err.message
          : "Failed to generate flashcards from document."
      )
    } finally {
      setIsGenerating(false)
    }
  }

  const handleDeleteDeck = async (deckId: string) => {
    setDeletingDeckId(deckId)
    try {
      await deleteFlashcardDeck(deckId)
      setDecks((prev) => prev.filter((d) => d.id !== deckId))
      if (managingDeck?.id === deckId) {
        setManagingDeck(null)
      }
      if (activeStudyDeck?.id === deckId) {
        setActiveStudyDeck(null)
      }
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? err.message : "Could not delete deck."
      )
    } finally {
      setDeletingDeckId(null)
    }
  }

  // Card Manager CRUD Handlers
  const handleAddCardToDeck = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!managingDeck) return
    if (!newCardFront.trim() || !newCardBack.trim()) {
      setCardManagerError("Both Front and Back fields are required.")
      return
    }
    setIsSavingCard(true)
    setCardManagerError(null)
    try {
      const parsedPage = newCardPage.trim()
        ? Math.max(1, parseInt(newCardPage.trim(), 10) || 1)
        : null
      const created = await createSingleFlashcard(managingDeck.id, {
        front_text: newCardFront.trim(),
        back_text: newCardBack.trim(),
        page_number: parsedPage,
      })
      setManagingDeck((prev) =>
        prev
          ? {
              ...prev,
              total_cards: prev.total_cards + 1,
              due_count: prev.due_count + 1,
              cards: [...prev.cards, created],
            }
          : prev
      )
      setNewCardFront("")
      setNewCardBack("")
      setNewCardPage("")
      setIsAddingCard(false)
      void loadDecks()
    } catch (err) {
      setCardManagerError(
        err instanceof Error ? err.message : "Could not add flashcard."
      )
    } finally {
      setIsSavingCard(false)
    }
  }

  const handleSaveEditedCard = async (cardId: string) => {
    if (!editFront.trim() || !editBack.trim()) {
      setCardManagerError("Both Front and Back fields are required.")
      return
    }
    setIsSavingCard(true)
    setCardManagerError(null)
    try {
      const parsedPage = editPage.trim()
        ? Math.max(1, parseInt(editPage.trim(), 10) || 1)
        : null
      const updated = await updateSingleFlashcard(cardId, {
        front_text: editFront.trim(),
        back_text: editBack.trim(),
        page_number: parsedPage,
      })
      setManagingDeck((prev) =>
        prev
          ? {
              ...prev,
              cards: prev.cards.map((c) => (c.id === cardId ? updated : c)),
            }
          : prev
      )
      setEditingCardId(null)
    } catch (err) {
      setCardManagerError(
        err instanceof Error ? err.message : "Could not update flashcard."
      )
    } finally {
      setIsSavingCard(false)
    }
  }

  const handleDeleteCardFromDeck = async (cardId: string) => {
    setDeletingCardId(cardId)
    setCardManagerError(null)
    try {
      await deleteSingleFlashcard(cardId)
      setManagingDeck((prev) =>
        prev
          ? {
              ...prev,
              total_cards: Math.max(0, prev.total_cards - 1),
              cards: prev.cards.filter((c) => c.id !== cardId),
            }
          : prev
      )
      void loadDecks()
    } catch (err) {
      setCardManagerError(
        err instanceof Error ? err.message : "Could not delete flashcard."
      )
    } finally {
      setDeletingCardId(null)
    }
  }

  // ============================================================================
  // PHASE 2: DEDICATED FULL-SCREEN 3D FLIP STUDY SESSION
  // ============================================================================
  if (activeStudyDeck) {
    const totalInQueue = studyQueue.length
    const safeIdx = Math.min(
      Math.max(0, currentCardIndex),
      Math.max(0, totalInQueue - 1)
    )
    const currentCard = studyQueue[safeIdx] || null
    const sourceDoc = activeStudyDeck.document_id
      ? documentMap.get(activeStudyDeck.document_id)
      : null
    const dueCardsCount = (activeStudyDeck.cards || []).filter((c) =>
      isCardDue(c.due_date)
    ).length
    const totalReviewed =
      sessionStats.again +
      sessionStats.hard +
      sessionStats.good +
      sessionStats.easy

    return (
      <div className="flex-1 min-h-0 flex flex-col bg-[#F8FAFC] dark:bg-slate-950 overflow-hidden">
        {/* Session Top Bar */}
        <div className="h-16 border-b border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 px-6 flex items-center justify-between gap-4 shrink-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white truncate">
                {activeStudyDeck.title}
              </h2>
              <span className="hidden sm:inline-flex items-center gap-1 rounded-md bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 px-2 py-0.5 text-[11px] font-mono font-semibold text-[#0A77FF] dark:text-sky-300 tabular-nums shrink-0">
                {totalInQueue > 0 ? `Card ${safeIdx + 1} / ${totalInQueue}` : "0 cards"}
              </span>
            </div>
            {sourceDoc && (
              <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate">
                Source: {sourceDoc.title}
              </p>
            )}
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            {/* Segmented Mode Switcher: Spaced Repetition vs Browse All */}
            <div className="inline-flex items-center rounded-xl bg-slate-100 dark:bg-slate-800/90 p-0.5 border border-slate-200/70 dark:border-slate-800">
              <button
                type="button"
                onClick={() => handleSwitchStudyMode("spaced")}
                className={cn(
                  "h-8 px-3 rounded-[10px] text-xs font-semibold inline-flex items-center gap-1.5 transition-all cursor-pointer tabular-nums",
                  studyMode === "spaced"
                    ? "bg-white dark:bg-slate-900 text-[#0A77FF] dark:text-sky-400 shadow-2xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                )}
              >
                <Flame className="h-3.5 w-3.5 stroke-[2]" />
                <span>SM-2 Due ({dueCardsCount})</span>
              </button>

              <button
                type="button"
                onClick={() => handleSwitchStudyMode("browse")}
                className={cn(
                  "h-8 px-3 rounded-[10px] text-xs font-semibold inline-flex items-center gap-1.5 transition-all cursor-pointer tabular-nums",
                  studyMode === "browse"
                    ? "bg-white dark:bg-slate-900 text-[#0A77FF] dark:text-sky-400 shadow-2xs"
                    : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                )}
              >
                <BookOpen className="h-3.5 w-3.5 stroke-[2]" />
                <span>Browse All ({activeStudyDeck.cards.length})</span>
              </button>
            </div>

            <button
              type="button"
              onClick={() => {
                setActiveStudyDeck(null)
                void loadDecks()
              }}
              className="h-9 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              <ArrowLeft className="h-3.5 w-3.5 stroke-[2]" />
              <span>Back to Decks</span>
            </button>
          </div>
        </div>

        {/* Study Session Body */}
        <div className="flex-1 overflow-y-auto px-6 py-8 flex flex-col justify-center">
          <div className="max-w-2xl w-full mx-auto space-y-6">
            {isSessionComplete || !currentCard ? (
              /* Session Complete Summary Card */
              <div className="rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-center space-y-6 shadow-xs animate-in fade-in-0 zoom-in-95 duration-150">
                <div className="h-14 w-14 rounded-2xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mx-auto">
                  <CheckCircle2 className="h-7 w-7 stroke-[2]" />
                </div>

                <div className="space-y-1.5">
                  <h3 className="text-xl font-bold text-slate-900 dark:text-white">
                    {activeStudyDeck.cards.length === 0
                      ? "This deck has no cards yet"
                      : "All Due Cards Reviewed!"}
                  </h3>
                  <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 max-w-md mx-auto">
                    {activeStudyDeck.cards.length === 0
                      ? "Add flashcards manually or extract them from Quizzes and AI Tutor conversations."
                      : totalReviewed > 0
                        ? `You completed ${totalReviewed} spaced-repetition reviews in this session. Next review intervals have been updated via SM-2.`
                        : "Every card in this deck is scheduled for a future review date. You can still browse all cards anytime."}
                  </p>
                </div>

                {totalReviewed > 0 && (
                  <div className="grid grid-cols-4 gap-3 max-w-md mx-auto">
                    <div className="rounded-xl border border-rose-200/70 dark:border-rose-900/50 bg-rose-50/50 dark:bg-rose-950/30 p-3">
                      <span className="block text-[11px] font-semibold text-rose-600 dark:text-rose-400">
                        Again
                      </span>
                      <span className="text-lg font-mono font-bold text-rose-700 dark:text-rose-300 tabular-nums">
                        {sessionStats.again}
                      </span>
                    </div>
                    <div className="rounded-xl border border-amber-200/70 dark:border-amber-900/50 bg-amber-50/50 dark:bg-amber-950/30 p-3">
                      <span className="block text-[11px] font-semibold text-amber-600 dark:text-amber-400">
                        Hard
                      </span>
                      <span className="text-lg font-mono font-bold text-amber-700 dark:text-amber-300 tabular-nums">
                        {sessionStats.hard}
                      </span>
                    </div>
                    <div className="rounded-xl border border-sky-200/70 dark:border-sky-900/50 bg-sky-50/50 dark:bg-sky-950/30 p-3">
                      <span className="block text-[11px] font-semibold text-[#0A77FF] dark:text-sky-400">
                        Good
                      </span>
                      <span className="text-lg font-mono font-bold text-[#0A77FF] dark:text-sky-300 tabular-nums">
                        {sessionStats.good}
                      </span>
                    </div>
                    <div className="rounded-xl border border-emerald-200/70 dark:border-emerald-900/50 bg-emerald-50/50 dark:bg-emerald-950/30 p-3">
                      <span className="block text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                        Easy
                      </span>
                      <span className="text-lg font-mono font-bold text-emerald-700 dark:text-emerald-300 tabular-nums">
                        {sessionStats.easy}
                      </span>
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-center gap-3 pt-2 flex-wrap">
                  {activeStudyDeck.cards.length > 0 && (
                    <button
                      type="button"
                      onClick={() => handleSwitchStudyMode("browse")}
                      className="h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-2 transition-colors cursor-pointer"
                    >
                      <BookOpen className="h-4 w-4 text-[#0A77FF]" />
                      <span>Browse All {activeStudyDeck.cards.length} Cards</span>
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => {
                      setActiveStudyDeck(null)
                      void loadDecks()
                    }}
                    className="h-10 px-5 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] text-white text-xs font-semibold inline-flex items-center gap-2 shadow-[0_4px_12px_rgba(10,119,255,0.25)] transition-all cursor-pointer"
                  >
                    <ArrowLeft className="h-4 w-4 stroke-[2]" />
                    <span>Back to Deck Library</span>
                  </button>
                </div>
              </div>
            ) : (
              /* Active 3D Flip Flashcard Stage */
              <>
                {/* Linear Progress Bar */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-mono font-semibold text-slate-500 dark:text-slate-400 tabular-nums">
                      Card {safeIdx + 1} of {totalInQueue}
                    </span>
                    <span className="font-mono text-[11px] text-slate-400 dark:text-slate-500 tabular-nums">
                      EF {currentCard.easiness_factor.toFixed(2)} · Interval{" "}
                      {currentCard.interval_days}d
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-slate-200/80 dark:bg-slate-800 overflow-hidden">
                    <div
                      className="h-full bg-[#0A77FF] transition-all duration-200"
                      style={{
                        width: `${Math.round(
                          ((safeIdx + 1) / Math.max(1, totalInQueue)) * 100
                        )}%`,
                      }}
                    />
                  </div>
                </div>

                {/* 3D Flip Card Container */}
                <div style={{ perspective: "1400px" }} className="w-full">
                  <div
                    role="button"
                    tabIndex={0}
                    aria-label={
                      isFlipped
                        ? "Flashcard Back (Click or press Space to flip to front)"
                        : "Flashcard Front (Click or press Space to reveal answer)"
                    }
                    onClick={() => setIsFlipped((prev) => !prev)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault()
                        setIsFlipped((prev) => !prev)
                      }
                    }}
                    style={{
                      transformStyle: "preserve-3d",
                      transform: isFlipped ? "rotateY(180deg)" : "rotateY(0deg)",
                    }}
                    className="relative grid [grid-template-areas:'card'] w-full cursor-pointer select-none transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] focus-visible:outline-none rounded-2xl focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                  >
                    {/* FRONT FACE */}
                    <div
                      style={{
                        backfaceVisibility: "hidden",
                        WebkitBackfaceVisibility: "hidden",
                        transform: "rotateY(0deg)",
                      }}
                      className={cn(
                        "[grid-area:card] min-h-[340px] w-full rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 p-7 sm:p-9 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow",
                        isFlipped ? "pointer-events-none" : "pointer-events-auto"
                      )}
                    >
                      {/* Front Header Metadata */}
                      <div className="flex items-center justify-between gap-2">
                        <span className="rounded-lg px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wider bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                          Front · Prompt
                        </span>

                        <div
                          className="flex items-center gap-2"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {currentCard.page_number &&
                            activeStudyDeck.document_id && (
                              <button
                                type="button"
                                onClick={() =>
                                  onOpenDocumentAtPage(
                                    activeStudyDeck.document_id!,
                                    currentCard.page_number!
                                  )
                                }
                                className="h-7 px-2.5 rounded-lg bg-[#0A77FF]/10 hover:bg-[#0A77FF]/20 text-[#0A77FF] dark:bg-[#0A77FF]/25 dark:text-sky-300 text-xs font-mono font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer tabular-nums"
                              >
                                <BookOpen className="h-3.5 w-3.5 stroke-[2]" />
                                <span>Page {currentCard.page_number}</span>
                              </button>
                            )}
                        </div>
                      </div>

                      {/* Front Center Content */}
                      <div className="my-auto py-8">
                        <div className="leading-relaxed text-lg sm:text-xl font-semibold text-slate-900 dark:text-white text-center">
                          <ChatMarkdownRenderer
                            content={currentCard.front_text}
                          />
                        </div>
                      </div>

                      {/* Front Bottom Hint */}
                      <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-800/80 text-[11px] font-mono text-slate-400 dark:text-slate-500">
                        <span>Click card or press [Space] to flip</span>
                        <RotateCcw className="h-3.5 w-3.5" />
                      </div>
                    </div>

                    {/* BACK FACE */}
                    <div
                      style={{
                        backfaceVisibility: "hidden",
                        WebkitBackfaceVisibility: "hidden",
                        transform: "rotateY(180deg)",
                      }}
                      className={cn(
                        "[grid-area:card] min-h-[340px] w-full rounded-2xl border border-[#0A77FF]/45 bg-gradient-to-b from-white to-[#0A77FF]/[0.03] dark:from-slate-900 dark:to-[#0A77FF]/[0.08] p-7 sm:p-9 flex flex-col justify-between shadow-sm hover:shadow-md transition-shadow",
                        isFlipped ? "pointer-events-auto" : "pointer-events-none"
                      )}
                    >
                      {/* Back Header Metadata */}
                      <div className="flex items-center justify-between gap-2">
                        <span className="rounded-lg px-2.5 py-1 text-[11px] font-mono font-bold uppercase tracking-wider bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/25 dark:text-sky-300">
                          Back · Answer & Formula
                        </span>

                        <div
                          className="flex items-center gap-2"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {currentCard.page_number &&
                            activeStudyDeck.document_id && (
                              <button
                                type="button"
                                onClick={() =>
                                  onOpenDocumentAtPage(
                                    activeStudyDeck.document_id!,
                                    currentCard.page_number!
                                  )
                                }
                                className="h-7 px-2.5 rounded-lg bg-[#0A77FF]/10 hover:bg-[#0A77FF]/20 text-[#0A77FF] dark:bg-[#0A77FF]/25 dark:text-sky-300 text-xs font-mono font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer tabular-nums"
                              >
                                <BookOpen className="h-3.5 w-3.5 stroke-[2]" />
                                <span>Page {currentCard.page_number}</span>
                              </button>
                            )}
                        </div>
                      </div>

                      {/* Back Center Content */}
                      <div className="my-auto py-8">
                        <div className="leading-relaxed text-base sm:text-lg text-slate-800 dark:text-slate-100">
                          <ChatMarkdownRenderer
                            content={currentCard.back_text}
                          />
                        </div>
                      </div>

                      {/* Back Bottom Hint */}
                      <div className="flex items-center justify-between pt-3 border-t border-slate-100 dark:border-slate-800/80 text-[11px] font-mono text-slate-400 dark:text-slate-500">
                        <span>Click card or press [Space] to flip back</span>
                        <RotateCcw className="h-3.5 w-3.5" />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Controls Below Card: SM-2 Rating Bar OR Browse Navigation */}
                {studyMode === "spaced" ? (
                  isFlipped && (
                    <div className="rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-2xs space-y-2.5 animate-in fade-in-0 slide-in-from-top-2 duration-200">
                      <div className="flex items-center justify-between text-xs px-1">
                        <span className="font-semibold text-slate-700 dark:text-slate-200">
                          How well did you recall this concept?
                        </span>
                        <span className="font-mono text-[11px] text-slate-400">
                          Shortcuts: [1] – [4]
                        </span>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        <button
                          type="button"
                          disabled={isSubmittingReview}
                          onClick={() => void handleRateCard("again")}
                          className="h-12 rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/70 hover:bg-rose-100/80 dark:bg-rose-950/40 dark:hover:bg-rose-950/70 px-3 flex flex-col items-center justify-center transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <span className="text-xs font-bold text-rose-700 dark:text-rose-300">
                            [1] Again
                          </span>
                          <span className="text-[10px] font-mono text-rose-600/80 dark:text-rose-400/80 tabular-nums">
                            Reset · 1d
                          </span>
                        </button>

                        <button
                          type="button"
                          disabled={isSubmittingReview}
                          onClick={() => void handleRateCard("hard")}
                          className="h-12 rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/70 hover:bg-amber-100/80 dark:bg-amber-950/40 dark:hover:bg-amber-950/70 px-3 flex flex-col items-center justify-center transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <span className="text-xs font-bold text-amber-700 dark:text-amber-300">
                            [2] Hard
                          </span>
                          <span className="text-[10px] font-mono text-amber-600/80 dark:text-amber-400/80 tabular-nums">
                            Short interval
                          </span>
                        </button>

                        <button
                          type="button"
                          disabled={isSubmittingReview}
                          onClick={() => void handleRateCard("good")}
                          className="h-12 rounded-xl border border-[#0A77FF]/30 bg-[#0A77FF]/10 hover:bg-[#0A77FF]/15 dark:bg-[#0A77FF]/20 dark:hover:bg-[#0A77FF]/30 px-3 flex flex-col items-center justify-center transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <span className="text-xs font-bold text-[#0A77FF] dark:text-sky-300">
                            [3] Good
                          </span>
                          <span className="text-[10px] font-mono text-[#0A77FF]/80 dark:text-sky-400/80 tabular-nums">
                            Standard SM-2
                          </span>
                        </button>

                        <button
                          type="button"
                          disabled={isSubmittingReview}
                          onClick={() => void handleRateCard("easy")}
                          className="h-12 rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/70 hover:bg-emerald-100/80 dark:bg-emerald-950/40 dark:hover:bg-emerald-950/70 px-3 flex flex-col items-center justify-center transition-colors cursor-pointer disabled:opacity-50"
                        >
                          <span className="text-xs font-bold text-emerald-700 dark:text-emerald-300">
                            [4] Easy
                          </span>
                          <span className="text-[10px] font-mono text-emerald-600/80 dark:text-emerald-400/80 tabular-nums">
                            Boost EF +0.15
                          </span>
                        </button>
                      </div>
                    </div>
                  )
                ) : (
                  /* Browse All Mode Controls */
                  <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-3.5 shadow-2xs">
                    <button
                      type="button"
                      disabled={safeIdx === 0}
                      onClick={() => {
                        setIsFlipped(false)
                        setCurrentCardIndex((prev) => Math.max(0, prev - 1))
                      }}
                      className="h-9 px-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <ArrowLeft className="h-3.5 w-3.5 stroke-[2]" />
                      <span>Previous</span>
                    </button>

                    <span className="text-xs font-mono font-semibold text-slate-500 dark:text-slate-400 tabular-nums">
                      Card {safeIdx + 1} / {totalInQueue}
                    </span>

                    <button
                      type="button"
                      disabled={safeIdx >= totalInQueue - 1}
                      onClick={() => {
                        setIsFlipped(false)
                        setCurrentCardIndex((prev) =>
                          Math.min(totalInQueue - 1, prev + 1)
                        )
                      }}
                      className="h-9 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-200 text-white dark:text-slate-900 text-xs font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <span>Next</span>
                      <ArrowRight className="h-3.5 w-3.5 stroke-[2]" />
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ============================================================================
  // DECK DETAIL / CARD MANAGER VIEW (ADD / EDIT / DELETE INDIVIDUAL CARDS)
  // ============================================================================
  if (managingDeck) {
    const sourceDoc = managingDeck.document_id
      ? documentMap.get(managingDeck.document_id)
      : null
    const cards = managingDeck.cards || []
    const dueCount = cards.filter((c) => isCardDue(c.due_date)).length

    return (
      <div className="flex-1 overflow-y-auto px-6 py-8 bg-[#F8FAFC] dark:bg-slate-950">
        <div className="max-w-5xl mx-auto space-y-6">
          {/* Top Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 dark:border-slate-800 pb-5">
            <div className="space-y-1 min-w-0">
              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => {
                    setManagingDeck(null)
                    void loadDecks()
                  }}
                  className="h-8 px-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer shrink-0"
                >
                  <ArrowLeft className="h-3.5 w-3.5 stroke-[2]" />
                  <span>Decks</span>
                </button>
                <h1 className="text-xl font-bold text-slate-900 dark:text-white truncate">
                  {managingDeck.title}
                </h1>
                <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs font-mono font-semibold text-slate-600 dark:text-slate-300 tabular-nums shrink-0">
                  {cards.length} {cards.length === 1 ? "card" : "cards"}
                </span>
              </div>
              {sourceDoc && (
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Linked Document: {sourceDoc.title}
                </p>
              )}
            </div>

            <div className="flex items-center gap-2.5 shrink-0">
              <button
                type="button"
                onClick={() => {
                  setIsAddingCard((prev) => !prev)
                  setCardManagerError(null)
                }}
                className="h-9 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5 stroke-[2]" />
                <span>Add Card</span>
              </button>

              {cards.length > 0 && (
                <button
                  type="button"
                  onClick={() =>
                    void handleStartStudySession(
                      managingDeck.id,
                      dueCount > 0 ? "spaced" : "browse"
                    )
                  }
                  className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-[0_2px_10px_rgba(10,119,255,0.25)] transition-all cursor-pointer"
                >
                  <Play className="h-3.5 w-3.5 fill-current" />
                  <span>
                    {dueCount > 0
                      ? `Study Due (${dueCount})`
                      : `Study All (${cards.length})`}
                  </span>
                </button>
              )}
            </div>
          </div>

          {cardManagerError && (
            <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-4 py-3 text-xs text-rose-600 dark:text-rose-400 flex items-center gap-2">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{cardManagerError}</span>
            </div>
          )}

          {/* Add New Card Form */}
          {isAddingCard && (
            <form
              onSubmit={handleAddCardToDeck}
              className="rounded-2xl border border-[#0A77FF]/35 bg-white dark:bg-slate-900 p-5 shadow-2xs space-y-4 animate-in fade-in-0 duration-150"
            >
              <div className="flex items-center justify-between">
                <h2 className="text-xs font-bold uppercase tracking-wider text-[#0A77FF] dark:text-sky-400">
                  Add New Flashcard
                </h2>
                <button
                  type="button"
                  onClick={() => setIsAddingCard(false)}
                  className="text-xs text-slate-400 hover:text-slate-600 cursor-pointer"
                >
                  Cancel
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Front (Question / Term / Concept)
                  </label>
                  <textarea
                    rows={3}
                    required
                    value={newCardFront}
                    onChange={(e) => setNewCardFront(e.target.value)}
                    placeholder="e.g. What is the Bayes' Theorem formula?"
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-3 text-xs text-slate-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Back (Answer / Definition / LaTeX Formula)
                  </label>
                  <textarea
                    rows={3}
                    required
                    value={newCardBack}
                    onChange={(e) => setNewCardBack(e.target.value)}
                    placeholder="e.g. $P(A|B) = \frac{P(B|A)P(A)}{P(B)}$"
                    className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-3 text-xs text-slate-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                  />
                </div>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
                <div className="flex items-center gap-2">
                  <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
                    PDF Page Reference (Optional):
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={newCardPage}
                    onChange={(e) => setNewCardPage(e.target.value)}
                    placeholder="e.g. 14"
                    className="h-8 w-24 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-2.5 text-xs font-mono text-slate-900 dark:text-white tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isSavingCard}
                  className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] disabled:opacity-50 text-white text-xs font-semibold inline-flex items-center gap-1.5 cursor-pointer self-end sm:self-center"
                >
                  {isSavingCard ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Check className="h-3.5 w-3.5 stroke-[2]" />
                  )}
                  <span>Save Card</span>
                </button>
              </div>
            </form>
          )}

          {/* Cards List */}
          {cards.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 dark:border-slate-800 bg-white/70 dark:bg-slate-900/50 p-10 text-center space-y-3">
              <Layers className="h-6 w-6 text-slate-400 mx-auto" />
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                  No cards in this deck yet
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Click &ldquo;Add Card&rdquo; above to create your first card.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {cards.map((card, idx) => {
                const isEditing = editingCardId === card.id
                const isDeleting = deletingCardId === card.id
                const dueBadge = formatDueBadge(
                  card.due_date,
                  card.interval_days
                )

                return (
                  <div
                    key={card.id}
                    className="rounded-2xl border border-slate-200/85 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-2xs space-y-3"
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-mono font-bold text-slate-400 tabular-nums">
                          #{idx + 1}
                        </span>
                        <span
                          className={cn(
                            "rounded-md px-2 py-0.5 text-[11px] font-mono font-semibold tabular-nums",
                            dueBadge.isDue
                              ? "bg-amber-500/10 text-amber-700 dark:text-amber-300"
                              : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                          )}
                        >
                          {dueBadge.label}
                        </span>
                        <span className="text-[11px] font-mono text-slate-400 tabular-nums">
                          EF {card.easiness_factor.toFixed(2)} · Reps{" "}
                          {card.repetition_number}
                        </span>
                        {card.page_number && (
                          <button
                            type="button"
                            onClick={() => {
                              if (managingDeck.document_id) {
                                onOpenDocumentAtPage(
                                  managingDeck.document_id,
                                  card.page_number!
                                )
                              }
                            }}
                            className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-mono text-[#0A77FF] dark:text-sky-300 inline-flex items-center gap-1 tabular-nums hover:underline cursor-pointer"
                          >
                            <BookOpen className="h-3 w-3" />
                            <span>Page {card.page_number}</span>
                          </button>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5">
                        {!isEditing ? (
                          <button
                            type="button"
                            onClick={() => {
                              setEditingCardId(card.id)
                              setEditFront(card.front_text)
                              setEditBack(card.back_text)
                              setEditPage(
                                card.page_number ? String(card.page_number) : ""
                              )
                            }}
                            className="h-7 px-2.5 rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-1 cursor-pointer"
                          >
                            <Pencil className="h-3 w-3" />
                            <span>Edit</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setEditingCardId(null)}
                            className="h-7 px-2.5 rounded-lg border border-slate-200 dark:border-slate-800 text-xs font-medium text-slate-500 cursor-pointer"
                          >
                            Cancel
                          </button>
                        )}

                        <button
                          type="button"
                          disabled={isDeleting}
                          onClick={() => void handleDeleteCardFromDeck(card.id)}
                          aria-label="Delete flashcard"
                          className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
                        >
                          {isDeleting ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                    </div>

                    {isEditing ? (
                      <div className="space-y-3 pt-1">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <textarea
                            rows={3}
                            value={editFront}
                            onChange={(e) => setEditFront(e.target.value)}
                            className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 p-2.5 text-xs text-slate-900 dark:text-white"
                          />
                          <textarea
                            rows={3}
                            value={editBack}
                            onChange={(e) => setEditBack(e.target.value)}
                            className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 p-2.5 text-xs text-slate-900 dark:text-white"
                          />
                        </div>
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-slate-500">
                              Page:
                            </span>
                            <input
                              type="number"
                              min={1}
                              value={editPage}
                              onChange={(e) => setEditPage(e.target.value)}
                              className="h-8 w-20 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 px-2 text-xs font-mono tabular-nums"
                            />
                          </div>
                          <button
                            type="button"
                            disabled={isSavingCard}
                            onClick={() => void handleSaveEditedCard(card.id)}
                            className="h-8 px-3.5 rounded-lg bg-[#0A77FF] text-white text-xs font-semibold inline-flex items-center gap-1.5 cursor-pointer"
                          >
                            <Check className="h-3.5 w-3.5" />
                            <span>Save Changes</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <div className="rounded-xl border border-slate-200/70 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 p-3 space-y-1">
                          <span className="block text-[10px] font-mono uppercase tracking-wider text-slate-400">
                            Front
                          </span>
                          <div className="text-xs sm:text-sm font-medium text-slate-900 dark:text-slate-100 leading-relaxed">
                            <ChatMarkdownRenderer content={card.front_text} />
                          </div>
                        </div>

                        <div className="rounded-xl border border-[#0A77FF]/20 bg-[#0A77FF]/[0.03] dark:bg-[#0A77FF]/[0.07] p-3 space-y-1">
                          <span className="block text-[10px] font-mono uppercase tracking-wider text-[#0A77FF] dark:text-sky-400">
                            Back
                          </span>
                          <div className="text-xs sm:text-sm text-slate-800 dark:text-slate-200 leading-relaxed">
                            <ChatMarkdownRenderer content={card.back_text} />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    )
  }

  // ============================================================================
  // PHASE 1: DECK LIBRARY + KPI TELEMETRY + AI GENERATOR & MANUAL DECK MODALS
  // ============================================================================
  return (
    <div className="flex-1 overflow-y-auto overflow-x-hidden px-6 py-8">
      <div className="max-w-5xl w-full min-w-0 mx-auto space-y-7">
        {/* Top Heading + Primary Actions */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Active Recall Flashcards
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
              Master definitions, formulas, and misconceptions with SM-2 spaced
              repetition and direct PDF citations.
            </p>
          </div>

          <div className="flex items-center gap-2.5 shrink-0 flex-wrap">
            <button
              type="button"
              onClick={() => void loadDecks()}
              aria-label="Refresh flashcard decks"
              title="Refresh"
              className="h-10 px-3 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-2 transition-colors cursor-pointer active:scale-[0.98]"
            >
              <RefreshCw
                className={cn(
                  "h-3.5 w-3.5 stroke-[1.8]",
                  (isLoadingDecks || isLoadingDeckDetail) && "animate-spin"
                )}
              />
              <span className="hidden sm:inline">Refresh</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setManualDeckError(null)
                setManualDeckSubjectId(
                  subjectFilter !== "all" && subjectFilter !== "uncategorized"
                    ? subjectFilter
                    : subjects[0]?.id || ""
                )
                setIsManualDeckModalOpen(true)
              }}
              className="h-10 px-3.5 rounded-xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs sm:text-sm font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer active:scale-[0.98]"
            >
              <Plus className="h-4 w-4 stroke-[2]" />
              <span>New Deck</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setGenerateError(null)
                setIsGenerateModalOpen(true)
              }}
              className="h-10 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs sm:text-sm font-semibold inline-flex items-center gap-2 shadow-[0_4px_14px_rgba(10,119,255,0.28)] transition-all cursor-pointer active:scale-[0.98]"
            >
              <Sparkles className="h-4 w-4 stroke-[2]" />
              <span>Generate with AI</span>
            </button>
          </div>
        </div>

        {/* KPI Telemetry Strip (Tabular Nums) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-2xs">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              Total Decks
            </span>
            <span className="mt-1 block text-2xl font-mono font-bold text-slate-900 dark:text-white tabular-nums">
              {kpiStats.totalDecks}
            </span>
          </div>

          <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 shadow-2xs">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
              Total Cards
            </span>
            <span className="mt-1 block text-2xl font-mono font-bold text-slate-900 dark:text-white tabular-nums">
              {kpiStats.totalCards}
            </span>
          </div>

          <div className="rounded-2xl border border-amber-200/80 dark:border-amber-900/50 bg-amber-50/40 dark:bg-amber-950/20 p-4 shadow-2xs">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
              Due Today (SM-2)
            </span>
            <span className="mt-1 block text-2xl font-mono font-bold text-amber-700 dark:text-amber-300 tabular-nums">
              {kpiStats.dueToday}
            </span>
          </div>

          <div className="rounded-2xl border border-emerald-200/80 dark:border-emerald-900/50 bg-emerald-50/40 dark:bg-emerald-950/20 p-4 shadow-2xs">
            <span className="block text-[11px] font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
              Mastered (≥7d)
            </span>
            <span className="mt-1 block text-2xl font-mono font-bold text-emerald-700 dark:text-emerald-300 tabular-nums">
              {kpiStats.mastered}
            </span>
          </div>
        </div>

        {/* Subject Filter Bar */}
        <div
          ref={filterScrollRef}
          role="tablist"
          aria-label="Filter flashcard decks by subject"
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
              ({decks.length})
            </span>
          </button>

          {subjects.map((subj) => {
            const count = decks.filter(
              (d) => resolveDeckSubjectId(d) === subj.id
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
              onClick={() => void loadDecks()}
              className="font-semibold underline cursor-pointer shrink-0"
            >
              Retry
            </button>
          </div>
        )}

        {/* Decks Grid */}
        {isLoadingDecks ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {[1, 2, 3].map((n) => (
              <div
                key={n}
                className="h-48 rounded-2xl border border-slate-200/70 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-5 animate-pulse flex flex-col justify-between"
              >
                <div className="space-y-2.5">
                  <div className="h-4 w-2/3 rounded bg-slate-200 dark:bg-slate-800" />
                  <div className="h-3 w-1/2 rounded bg-slate-100 dark:bg-slate-800/70" />
                </div>
                <div className="h-9 w-full rounded-xl bg-slate-200 dark:bg-slate-800" />
              </div>
            ))}
          </div>
        ) : filteredDecks.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300/90 dark:border-slate-800 bg-white/70 dark:bg-slate-900/50 p-10 text-center space-y-4">
            <div className="h-12 w-12 rounded-2xl bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-400 flex items-center justify-center mx-auto">
              <Brain className="h-6 w-6 stroke-[1.8]" />
            </div>
            <div className="space-y-1 max-w-md mx-auto">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                No flashcard decks yet
              </h3>
              <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
                Generate a deck automatically from any PDF textbook, extract
                flashcards from quiz mistakes, or create a deck manually.
              </p>
            </div>
            <div className="flex items-center justify-center gap-2.5 pt-1">
              <button
                type="button"
                onClick={() => setIsManualDeckModalOpen(true)}
                className="h-10 px-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 cursor-pointer"
              >
                <Plus className="h-4 w-4" />
                <span>Create Manual Deck</span>
              </button>
              <button
                type="button"
                onClick={() => setIsGenerateModalOpen(true)}
                className="h-10 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center gap-2 shadow-[0_4px_12px_rgba(10,119,255,0.25)] transition-all cursor-pointer"
              >
                <Sparkles className="h-4 w-4 stroke-[2]" />
                <span>Generate Deck with AI</span>
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filteredDecks.map((deck) => {
              const doc = deck.document_id
                ? documentMap.get(deck.document_id)
                : null
              const resolvedSubjId = resolveDeckSubjectId(deck)
              const subj = resolvedSubjId
                ? subjectMap.get(resolvedSubjId)
                : null
              const isDeleting = deletingDeckId === deck.id
              const masteryPct =
                deck.total_cards > 0
                  ? Math.round((deck.mastered_count / deck.total_cards) * 100)
                  : 0

              return (
                <article
                  key={deck.id}
                  className="group rounded-2xl border border-slate-200/85 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-2xs hover:shadow-md hover:border-slate-300 dark:hover:border-slate-700 transition-all flex flex-col justify-between gap-4"
                >
                  <div className="space-y-3">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {subj && (
                            <span className="inline-flex items-center rounded-md bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 px-2 py-0.5 text-[11px] font-semibold text-[#0A77FF] dark:text-sky-300">
                              {subj.name}
                            </span>
                          )}
                          <span className="inline-flex items-center rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-mono font-medium text-slate-600 dark:text-slate-300 tabular-nums">
                            {deck.total_cards}{" "}
                            {deck.total_cards === 1 ? "card" : "cards"}
                          </span>
                          {deck.due_count > 0 && (
                            <span className="inline-flex items-center gap-1 rounded-md bg-amber-500/15 px-2 py-0.5 text-[11px] font-mono font-bold text-amber-700 dark:text-amber-300 tabular-nums">
                              <span>{deck.due_count} Due</span>
                            </span>
                          )}
                        </div>

                        <h3 className="text-base font-bold text-slate-900 dark:text-white leading-snug line-clamp-2">
                          {deck.title}
                        </h3>
                      </div>

                      <button
                        type="button"
                        disabled={isDeleting}
                        onClick={() => void handleDeleteDeck(deck.id)}
                        aria-label={`Delete deck ${deck.title}`}
                        title="Delete deck"
                        className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer shrink-0"
                      >
                        {isDeleting ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4 stroke-[1.8]" />
                        )}
                      </button>
                    </div>

                    {deck.description && (
                      <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                        {deck.description}
                      </p>
                    )}

                    {doc && (
                      <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                        <FileText className="h-3.5 w-3.5 shrink-0 text-slate-400" />
                        <span className="truncate">{doc.title}</span>
                      </div>
                    )}

                    {/* Mastery Progress Bar */}
                    <div className="space-y-1 pt-1">
                      <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 tabular-nums">
                        <span>Mastery</span>
                        <span>
                          {deck.mastered_count}/{deck.total_cards} ({masteryPct}
                          %)
                        </span>
                      </div>
                      <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                        <div
                          className="h-full bg-emerald-500 transition-all duration-300"
                          style={{ width: `${masteryPct}%` }}
                        />
                      </div>
                    </div>
                  </div>

                  {/* Card Footer Actions */}
                  <div className="flex items-center justify-between gap-2 pt-3 border-t border-slate-100 dark:border-slate-800/80">
                    <button
                      type="button"
                      onClick={() => void handleOpenCardManager(deck.id)}
                      className="h-8 px-3 rounded-xl border border-slate-200/90 dark:border-slate-800 bg-slate-50 hover:bg-slate-100 dark:bg-slate-800/70 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5 stroke-[1.8]" />
                      <span>Manage</span>
                    </button>

                    <button
                      type="button"
                      disabled={deck.total_cards === 0}
                      onClick={() =>
                        void handleStartStudySession(
                          deck.id,
                          deck.due_count > 0 ? "spaced" : "browse"
                        )
                      }
                      className="h-8 px-3.5 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 disabled:opacity-45 text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-2xs transition-colors cursor-pointer active:scale-[0.98]"
                    >
                      <Play className="h-3 w-3 fill-current" />
                      <span className="tabular-nums">
                        {deck.due_count > 0
                          ? `Study Due (${deck.due_count})`
                          : "Practice All"}
                      </span>
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </div>

      {/* ========================================================================
          MODAL 1: CREATE MANUAL DECK
         ======================================================================== */}
      {isManualDeckModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="create-manual-deck-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/55 backdrop-blur-xs animate-in fade-in-0 duration-150"
          onClick={() => setIsManualDeckModalOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="h-8 w-8 rounded-xl bg-[#0A77FF]/10 text-[#0A77FF] flex items-center justify-center">
                  <Layers className="h-4 w-4 stroke-[2]" />
                </div>
                <h2
                  id="create-manual-deck-title"
                  className="text-sm font-bold text-slate-900 dark:text-white"
                >
                  Create Flashcard Deck
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setIsManualDeckModalOpen(false)}
                className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleCreateManualDeck} className="p-6 space-y-4">
              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Deck Title
                </label>
                <input
                  type="text"
                  required
                  value={manualDeckTitle}
                  onChange={(e) => setManualDeckTitle(e.target.value)}
                  placeholder="e.g. Digital Image Processing Formulas"
                  className="w-full h-10 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Subject (Optional)
                </label>
                <select
                  value={manualDeckSubjectId}
                  onChange={(e) => setManualDeckSubjectId(e.target.value)}
                  className="w-full h-10 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                >
                  <option value="">Uncategorized</option>
                  {subjects.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Linked Document (Optional)
                </label>
                <select
                  value={manualDeckDocId}
                  onChange={(e) => setManualDeckDocId(e.target.value)}
                  className="w-full h-10 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                >
                  <option value="">None</option>
                  {readyDocuments.map((d) => (
                    <option key={d.document_id} value={d.document_id}>
                      {d.title}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Description (Optional)
                </label>
                <textarea
                  rows={2}
                  value={manualDeckDesc}
                  onChange={(e) => setManualDeckDesc(e.target.value)}
                  placeholder="Key theorems and formulas for midterm review..."
                  className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-3 text-xs text-slate-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                />
              </div>

              {manualDeckError && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                  {manualDeckError}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsManualDeckModalOpen(false)}
                  className="h-9 px-4 rounded-xl border border-slate-200 dark:border-slate-800 text-xs font-semibold text-slate-600 dark:text-slate-300 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSavingManualDeck}
                  className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] text-white text-xs font-semibold inline-flex items-center gap-1.5 cursor-pointer"
                >
                  {isSavingManualDeck ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Plus className="h-3.5 w-3.5" />
                  )}
                  <span>Create Deck</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ========================================================================
          MODAL 2: GENERATE AI FLASHCARD DECK FROM PDF
         ======================================================================== */}
      {isGenerateModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="generate-ai-deck-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/55 backdrop-blur-xs animate-in fade-in-0 duration-150"
          onClick={() => !isGenerating && setIsGenerateModalOpen(false)}
        >
          <div
            className="w-full max-w-lg rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="h-8 w-8 rounded-xl bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-400 flex items-center justify-center">
                  <Sparkles className="h-4 w-4 stroke-[2]" />
                </div>
                <div>
                  <h2
                    id="generate-ai-deck-title"
                    className="text-sm font-bold text-slate-900 dark:text-white"
                  >
                    Generate AI Flashcard Deck
                  </h2>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500">
                    Synthesize high-yield terms, concepts &amp; LaTeX formulas
                    with page citations
                  </p>
                </div>
              </div>

              <button
                type="button"
                disabled={isGenerating}
                onClick={() => setIsGenerateModalOpen(false)}
                className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleGenerateAiDeck} className="p-6 space-y-5">
              {readyDocuments.length === 0 ? (
                <div className="rounded-xl border border-amber-200 dark:border-amber-900/60 bg-amber-50/70 dark:bg-amber-950/30 p-4 space-y-3 text-xs text-amber-800 dark:text-amber-300">
                  <p className="font-semibold">
                    No ready PDF documents available!
                  </p>
                  <p>
                    Please upload and wait for at least one PDF document to
                    finish processing in the Documents section.
                  </p>
                  {onSwitchToDocuments && (
                    <button
                      type="button"
                      onClick={() => {
                        setIsGenerateModalOpen(false)
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
                  {/* 1. Source Document Selector */}
                  <div className="space-y-1.5" ref={docDropdownRef}>
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Source Document
                    </label>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={() => setIsDocDropdownOpen((prev) => !prev)}
                        className="w-full h-10 px-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 hover:bg-slate-100/80 dark:bg-slate-950 dark:hover:bg-slate-900 flex items-center justify-between gap-2 text-xs font-medium text-slate-900 dark:text-white transition-colors cursor-pointer"
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
                                onClick={() => {
                                  setSelectedDocId(doc.document_id)
                                  setPageStart(1)
                                  setPageEnd(Math.max(1, doc.total_pages))
                                  setIsDocDropdownOpen(false)
                                }}
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

                  {/* 2. Number of Cards */}
                  <div className="space-y-2">
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Number of Flashcards
                    </label>
                    <div className="grid grid-cols-4 gap-2">
                      {[5, 8, 12, 15].map((count) => {
                        const active = numCards === count
                        return (
                          <button
                            key={count}
                            type="button"
                            onClick={() => setNumCards(count)}
                            className={cn(
                              "h-9 rounded-xl border font-mono text-xs font-bold tabular-nums transition-all cursor-pointer",
                              active
                                ? "border-[#0A77FF] bg-[#0A77FF] text-white shadow-2xs"
                                : "border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 text-slate-700 dark:text-slate-300 hover:border-[#0A77FF]/40"
                            )}
                          >
                            {count} Cards
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  {/* 3. Page Range */}
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

                  {/* 4. Optional Deck Title */}
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Deck Title (Optional)
                    </label>
                    <input
                      type="text"
                      value={customDeckTitle}
                      onChange={(e) => setCustomDeckTitle(e.target.value)}
                      placeholder="Leave blank for automatic title..."
                      maxLength={255}
                      className="w-full h-10 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-white placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                    />
                  </div>

                  {generateError && (
                    <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50 dark:bg-rose-950/40 p-3 text-xs text-rose-700 dark:text-rose-300 flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      <span>{generateError}</span>
                    </div>
                  )}

                  <div className="flex items-center justify-end gap-2.5 pt-2">
                    <button
                      type="button"
                      disabled={isGenerating}
                      onClick={() => setIsGenerateModalOpen(false)}
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
                          <span>Generating Deck...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="h-4 w-4 stroke-[2]" />
                          <span>Generate Flashcards</span>
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
