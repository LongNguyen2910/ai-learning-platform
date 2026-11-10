"use client"

import * as React from "react"
import {
  Layers,
  X,
  Check,
  Plus,
  Loader2,
  Sparkles,
  BookOpen,
  Pencil,
  Eye,
  AlertCircle,
  CheckCircle2,
} from "lucide-react"
import { cn } from "@/lib/utils"
import type { DocumentItem } from "@/lib/api/documents"
import type { SubjectItem } from "@/lib/api/roadmaps"
import {
  fetchFlashcardDecks,
  createFlashcardDeck,
  bulkSaveFlashcards,
  type ExtractedFlashcardCandidate,
  type FlashcardDeckSummary,
} from "@/lib/api/flashcards"
import { ChatMarkdownRenderer } from "@/components/dashboard/chat-markdown-renderer"

interface EditableCandidate extends ExtractedFlashcardCandidate {
  localId: string
  selected: boolean
  isEditing: boolean
}

interface FlashcardPreviewModalProps {
  open: boolean
  onClose: () => void
  candidates: ExtractedFlashcardCandidate[]
  sourceLabel?: string
  defaultDocumentId?: string | null
  defaultSubjectId?: string | null
  defaultDeckTitle?: string
  documents?: DocumentItem[]
  subjects?: SubjectItem[]
  onSavedSuccess?: (deckId: string, createdCount: number) => void
}

export function FlashcardPreviewModal({
  open,
  onClose,
  candidates,
  sourceLabel = "AI Active Recall Extraction",
  defaultDocumentId = null,
  defaultSubjectId = null,
  defaultDeckTitle = "Study Flashcards",
  documents = [],
  subjects = [],
  onSavedSuccess,
}: FlashcardPreviewModalProps) {
  const [items, setItems] = React.useState<EditableCandidate[]>([])
  const [decks, setDecks] = React.useState<FlashcardDeckSummary[]>([])
  const [isLoadingDecks, setIsLoadingDecks] = React.useState(false)
  const [selectedDeckId, setSelectedDeckId] = React.useState<string>("__new__")
  const [newDeckTitle, setNewDeckTitle] = React.useState(defaultDeckTitle)
  const [isCreatingNewDeckMode, setIsCreatingNewDeckMode] =
    React.useState(false)
  const [isSaving, setIsSaving] = React.useState(false)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  const [savedBanner, setSavedBanner] = React.useState<{
    count: number
    deckTitle: string
  } | null>(null)

  // Initialize editable items when modal opens
  React.useEffect(() => {
    if (!open) return
    setSavedBanner(null)
    setErrorMessage(null)
    setNewDeckTitle(defaultDeckTitle || "Study Flashcards")
    setItems(
      candidates.map((c, idx) => ({
        ...c,
        localId: `cand-${idx}-${Date.now()}`,
        selected: true,
        isEditing: false,
      }))
    )
  }, [open, candidates, defaultDeckTitle])

  // Load user decks and pre-select best match
  React.useEffect(() => {
    if (!open) return
    let cancelled = false
    setIsLoadingDecks(true)

    fetchFlashcardDecks()
      .then((list) => {
        if (cancelled) return
        setDecks(list)

        const docMatch = defaultDocumentId
          ? list.find((d) => d.document_id === defaultDocumentId)
          : undefined
        const subjMatch = defaultSubjectId
          ? list.find((d) => d.subject_id === defaultSubjectId)
          : undefined
        const bestMatch = docMatch || subjMatch || list[0]

        if (bestMatch) {
          setSelectedDeckId(bestMatch.id)
          setIsCreatingNewDeckMode(false)
        } else {
          setSelectedDeckId("__new__")
          setIsCreatingNewDeckMode(true)
        }
      })
      .catch(() => {
        if (cancelled) return
        setDecks([])
        setSelectedDeckId("__new__")
        setIsCreatingNewDeckMode(true)
      })
      .finally(() => {
        if (!cancelled) setIsLoadingDecks(false)
      })

    return () => {
      cancelled = true
    }
  }, [open, defaultDocumentId, defaultSubjectId])

  if (!open) return null

  const selectedItems = items.filter((item) => item.selected)
  const allSelected = items.length > 0 && selectedItems.length === items.length

  const toggleSelectAll = () => {
    const nextVal = !allSelected
    setItems((prev) => prev.map((it) => ({ ...it, selected: nextVal })))
  }

  const toggleItemSelected = (localId: string) => {
    setItems((prev) =>
      prev.map((it) =>
        it.localId === localId ? { ...it, selected: !it.selected } : it
      )
    )
  }

  const toggleItemEditing = (localId: string) => {
    setItems((prev) =>
      prev.map((it) =>
        it.localId === localId ? { ...it, isEditing: !it.isEditing } : it
      )
    )
  }

  const updateItemField = (
    localId: string,
    field: "front_text" | "back_text" | "target_page",
    value: string | number | null
  ) => {
    setItems((prev) =>
      prev.map((it) =>
        it.localId === localId ? { ...it, [field]: value } : it
      )
    )
  }

  const resolveSubjectId = (): string | null => {
    if (defaultSubjectId) return defaultSubjectId
    if (defaultDocumentId) {
      const doc = documents.find((d) => d.document_id === defaultDocumentId)
      if (doc?.subject_id) return doc.subject_id
    }
    return subjects[0]?.id ?? null
  }

  const handleSaveSelectedCards = async () => {
    if (selectedItems.length === 0) {
      setErrorMessage("Please select at least 1 flashcard to save.")
      return
    }

    const invalidCard = selectedItems.find(
      (c) => !c.front_text.trim() || !c.back_text.trim()
    )
    if (invalidCard) {
      setErrorMessage(
        "Every selected flashcard must have both Front and Back text."
      )
      return
    }

    setIsSaving(true)
    setErrorMessage(null)

    try {
      let targetDeckId = selectedDeckId
      let targetDeckName =
        decks.find((d) => d.id === selectedDeckId)?.title || "Deck"

      if (isCreatingNewDeckMode || selectedDeckId === "__new__") {
        const cleanDeckName = newDeckTitle.trim() || "Study Flashcards"
        const createdDeck = await createFlashcardDeck({
          title: cleanDeckName,
          description: `Saved from ${sourceLabel}`,
          subject_id: resolveSubjectId(),
          document_id: defaultDocumentId,
        })
        targetDeckId = createdDeck.id
        targetDeckName = createdDeck.title
      }

      const res = await bulkSaveFlashcards(
        targetDeckId,
        selectedItems.map((it) => ({
          front_text: it.front_text.trim(),
          back_text: it.back_text.trim(),
          page_number: it.target_page ?? null,
        }))
      )

      setSavedBanner({
        count: res.created_count,
        deckTitle: targetDeckName,
      })
      onSavedSuccess?.(targetDeckId, res.created_count)

      setTimeout(() => {
        onClose()
      }, 950)
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Could not save flashcards to deck."
      )
    } finally {
      setIsSaving(false)
    }
  }

  const getCategoryStyle = (cat?: string) => {
    const key = (cat || "concept").toLowerCase()
    if (key === "formula") {
      return {
        label: "Formula",
        className:
          "bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30",
      }
    }
    if (key === "term") {
      return {
        label: "Term",
        className:
          "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/30",
      }
    }
    return {
      label: "Concept",
      className:
        "bg-[#0A77FF]/10 text-[#0A77FF] dark:text-sky-300 border-[#0A77FF]/30",
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="flashcard-preview-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 backdrop-blur-[2px] p-4 animate-in fade-in-0 duration-150"
      onClick={onClose}
    >
      <div
        className="w-full max-w-3xl max-h-[88vh] flex flex-col rounded-2xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-200/80 dark:border-slate-800/80 flex items-center justify-between gap-4 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-xl bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 text-[#0A77FF] dark:text-sky-400 flex items-center justify-center shrink-0">
              <Layers className="h-4 w-4 stroke-[2]" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2
                  id="flashcard-preview-modal-title"
                  className="text-sm font-bold text-slate-900 dark:text-white"
                >
                  Review & Save Flashcards
                </h2>
                <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:text-slate-300">
                  {sourceLabel}
                </span>
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Preview, edit Front/Back content, and choose a target Deck
                before saving.
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close flashcard preview modal"
            className="h-8 w-8 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 dark:hover:text-slate-200 dark:hover:bg-slate-800 flex items-center justify-center transition-colors cursor-pointer shrink-0"
          >
            <X className="h-4 w-4 stroke-[2]" />
          </button>
        </div>

        {/* Target Deck Bar */}
        <div className="px-6 py-3.5 bg-slate-50/80 dark:bg-slate-950/60 border-b border-slate-200/70 dark:border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
          <div className="flex-1 min-w-0 flex flex-col sm:flex-row sm:items-center gap-2.5">
            <label
              htmlFor="flashcard-target-deck-select"
              className="text-xs font-semibold text-slate-700 dark:text-slate-300 shrink-0"
            >
              Target Deck:
            </label>

            {isLoadingDecks ? (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-[#0A77FF]" />
                <span>Loading decks...</span>
              </div>
            ) : !isCreatingNewDeckMode && decks.length > 0 ? (
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <select
                  id="flashcard-target-deck-select"
                  value={selectedDeckId}
                  onChange={(e) => {
                    if (e.target.value === "__new__") {
                      setIsCreatingNewDeckMode(true)
                      setSelectedDeckId("__new__")
                    } else {
                      setSelectedDeckId(e.target.value)
                    }
                  }}
                  className="h-9 flex-1 min-w-0 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 text-xs font-medium text-slate-900 dark:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] cursor-pointer"
                >
                  {decks.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.title} ({d.total_cards} cards)
                    </option>
                  ))}
                  <option value="__new__">+ Create a new Deck...</option>
                </select>

                <button
                  type="button"
                  onClick={() => {
                    setIsCreatingNewDeckMode(true)
                    setSelectedDeckId("__new__")
                  }}
                  className="h-9 px-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer shrink-0"
                >
                  <Plus className="h-3.5 w-3.5 stroke-[2]" />
                  <span>New Deck</span>
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <input
                  id="flashcard-target-deck-select"
                  type="text"
                  value={newDeckTitle}
                  onChange={(e) => setNewDeckTitle(e.target.value)}
                  placeholder="Enter new deck title..."
                  className="h-9 flex-1 min-w-0 rounded-xl border border-[#0A77FF]/50 bg-white dark:bg-slate-900 px-3 text-xs font-medium text-slate-900 dark:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                />
                {decks.length > 0 && (
                  <button
                    type="button"
                    onClick={() => {
                      setIsCreatingNewDeckMode(false)
                      setSelectedDeckId(decks[0].id)
                    }}
                    className="h-9 px-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-600 dark:text-slate-300 cursor-pointer shrink-0"
                  >
                    Use Existing
                  </button>
                )}
              </div>
            )}
          </div>

          {items.length > 1 && (
            <button
              type="button"
              onClick={toggleSelectAll}
              className="text-xs font-semibold text-[#0A77FF] hover:underline cursor-pointer shrink-0 self-end sm:self-center"
            >
              {allSelected ? "Deselect All" : "Select All"}
            </button>
          )}
        </div>

        {/* Scrollable Candidate Cards List */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {errorMessage && (
            <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-4 py-3 text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2">
              <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
              <span>{errorMessage}</span>
            </div>
          )}

          {savedBanner && (
            <div className="rounded-xl border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/80 dark:bg-emerald-950/40 px-4 py-3 text-xs font-semibold text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0" />
              <span>
                Saved {savedBanner.count} flashcard
                {savedBanner.count > 1 ? "s" : ""} to &ldquo;
                {savedBanner.deckTitle}&rdquo;!
              </span>
            </div>
          )}

          {items.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 dark:border-slate-800 p-10 text-center space-y-2">
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                No flashcards to extract
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                You answered all questions correctly — no misconception cards
                were needed.
              </p>
            </div>
          ) : (
            items.map((item, idx) => {
              const catInfo = getCategoryStyle(item.category)
              return (
                <div
                  key={item.localId}
                  className={cn(
                    "rounded-2xl border p-4 transition-all space-y-3",
                    item.selected
                      ? "border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-2xs"
                      : "border-slate-200/50 dark:border-slate-800/50 bg-slate-50/50 dark:bg-slate-950/40 opacity-60"
                  )}
                >
                  {/* Card Top Bar */}
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <div className="flex items-center gap-2.5">
                      <button
                        type="button"
                        onClick={() => toggleItemSelected(item.localId)}
                        aria-label={`Select flashcard ${idx + 1}`}
                        className={cn(
                          "h-5 w-5 rounded-md border flex items-center justify-center transition-colors cursor-pointer",
                          item.selected
                            ? "border-[#0A77FF] bg-[#0A77FF] text-white"
                            : "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900"
                        )}
                      >
                        {item.selected && (
                          <Check className="h-3.5 w-3.5 stroke-[2.5]" />
                        )}
                      </button>

                      <span className="text-xs font-mono font-bold text-slate-500 dark:text-slate-400 tabular-nums">
                        Card #{idx + 1}
                      </span>

                      <span
                        className={cn(
                          "rounded-md border px-2 py-0.5 text-[11px] font-semibold",
                          catInfo.className
                        )}
                      >
                        {catInfo.label}
                      </span>

                      {item.target_page && (
                        <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[11px] font-mono text-slate-600 dark:text-slate-300 inline-flex items-center gap-1 tabular-nums">
                          <BookOpen className="h-3 w-3" />
                          <span>Page {item.target_page}</span>
                        </span>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => toggleItemEditing(item.localId)}
                      className="h-7 px-2.5 rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-1.5 transition-colors cursor-pointer"
                    >
                      {item.isEditing ? (
                        <>
                          <Eye className="h-3.5 w-3.5" />
                          <span>Preview</span>
                        </>
                      ) : (
                        <>
                          <Pencil className="h-3.5 w-3.5" />
                          <span>Edit</span>
                        </>
                      )}
                    </button>
                  </div>

                  {item.trigger_reason && (
                    <p className="text-[11px] text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950/70 rounded-lg px-3 py-1.5 border border-slate-200/60 dark:border-slate-800/70">
                      <span className="font-semibold text-slate-700 dark:text-slate-300">
                        Why this card:{" "}
                      </span>
                      {item.trigger_reason}
                    </p>
                  )}

                  {item.isEditing ? (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                      <div className="space-y-1">
                        <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-400">
                          Front (Question / Term)
                        </label>
                        <textarea
                          rows={3}
                          value={item.front_text}
                          onChange={(e) =>
                            updateItemField(
                              item.localId,
                              "front_text",
                              e.target.value
                            )
                          }
                          className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5 text-xs text-slate-900 dark:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                        />
                      </div>

                      <div className="space-y-1">
                        <label className="block text-[11px] font-semibold text-slate-600 dark:text-slate-400">
                          Back (Answer / Definition / LaTeX Formula)
                        </label>
                        <textarea
                          rows={3}
                          value={item.back_text}
                          onChange={(e) =>
                            updateItemField(
                              item.localId,
                              "back_text",
                              e.target.value
                            )
                          }
                          className="w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5 text-xs text-slate-900 dark:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                      <div className="rounded-xl border border-slate-200/70 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50 p-3 space-y-1">
                        <span className="block text-[10px] font-mono uppercase tracking-wider text-slate-400">
                          Front
                        </span>
                        <div className="text-xs sm:text-sm font-medium text-slate-900 dark:text-slate-100 leading-relaxed">
                          <ChatMarkdownRenderer content={item.front_text} />
                        </div>
                      </div>

                      <div className="rounded-xl border border-[#0A77FF]/20 bg-[#0A77FF]/[0.03] dark:bg-[#0A77FF]/[0.07] p-3 space-y-1">
                        <span className="block text-[10px] font-mono uppercase tracking-wider text-[#0A77FF] dark:text-sky-400">
                          Back
                        </span>
                        <div className="text-xs sm:text-sm text-slate-800 dark:text-slate-200 leading-relaxed">
                          <ChatMarkdownRenderer content={item.back_text} />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-slate-200/80 dark:border-slate-800/80 bg-slate-50/60 dark:bg-slate-950/50 flex items-center justify-between gap-3 shrink-0">
          <span className="text-xs font-mono text-slate-500 dark:text-slate-400 tabular-nums">
            Selected {selectedItems.length} / {items.length} cards
          </span>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={onClose}
              className="h-9 px-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors cursor-pointer"
            >
              Cancel
            </button>

            {items.length > 0 && (
              <button
                type="button"
                disabled={isSaving || selectedItems.length === 0}
                onClick={() => void handleSaveSelectedCards()}
                className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] disabled:opacity-50 text-white text-xs font-semibold inline-flex items-center gap-1.5 shadow-[0_2px_10px_rgba(10,119,255,0.25)] transition-all cursor-pointer active:scale-[0.98]"
              >
                {isSaving ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Saving...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="h-3.5 w-3.5 stroke-[2]" />
                    <span>
                      Save {selectedItems.length} Card
                      {selectedItems.length === 1 ? "" : "s"} to Deck
                    </span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
