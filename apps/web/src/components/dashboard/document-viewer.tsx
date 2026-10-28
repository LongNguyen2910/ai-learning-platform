"use client"

import * as React from "react"
import dynamic from "next/dynamic"
import {
  ArrowLeft,
  Columns2,
  FileText,
  AlignLeft,
  Loader2,
  ExternalLink,
  Sparkles,
  GripVertical,
  Network,
} from "lucide-react"
import {
  fetchDocumentContent,
  fetchDocumentFileBlobUrl,
  type DocumentContentResponse,
  type DocumentItem,
} from "@/lib/api/documents"
import type { ChatCitation } from "@/lib/api/chat"
import type { HighlightedPageTarget } from "@/components/dashboard/pdf-canvas-viewer"
import { AiTutorChatPanel } from "@/components/dashboard/ai-tutor-chat-panel"
import { ChatMarkdownRenderer } from "@/components/dashboard/chat-markdown-renderer"

const PdfCanvasViewer = dynamic(
  () =>
    import("@/components/dashboard/pdf-canvas-viewer").then(
      (mod) => mod.PdfCanvasViewer
    ),
  {
    ssr: false,
    loading: () => (
      <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400">
        <Loader2 className="h-5 w-5 animate-spin text-[#0A77FF]" />
        <span className="text-xs font-medium">Initializing PDF reader...</span>
      </div>
    ),
  }
)

interface DocumentViewerProps {
  document: DocumentItem
  initialPageJump?: { page: number; nonce: number } | null
  onBack: () => void
  onCacheBlobUrl?: (documentId: string, blobUrl: string) => void
  onOpenRoadmapGenerator?: (doc: DocumentItem) => void
}

type ReaderTab = "pdf" | "markdown"

const MIN_SPLIT_PERCENT = 28
const MAX_SPLIT_PERCENT = 72
const DEFAULT_SPLIT_PERCENT = 52

export function DocumentViewer({
  document,
  initialPageJump,
  onBack,
  onCacheBlobUrl,
  onOpenRoadmapGenerator,
}: DocumentViewerProps) {
  const [activeTab, setActiveTab] = React.useState<ReaderTab>("pdf")
  const [isSplitChatOpen, setIsSplitChatOpen] = React.useState(false)
  const [splitRatio, setSplitRatio] = React.useState<number>(
    DEFAULT_SPLIT_PERCENT
  )
  const [isDraggingSplit, setIsDraggingSplit] = React.useState(false)
  const splitContainerRef = React.useRef<HTMLDivElement>(null)

  const [resolvedPdfBlobUrl, setResolvedPdfBlobUrl] = React.useState<
    string | null
  >(document.localBlobUrl ?? null)
  const [isLoadingPdf, setIsLoadingPdf] = React.useState(
    !document.localBlobUrl
  )
  const [pdfError, setPdfError] = React.useState<string | null>(null)
  const [contentData, setContentData] =
    React.useState<DocumentContentResponse | null>(null)
  const [isLoadingContent, setIsLoadingContent] = React.useState(false)
  const [contentError, setContentError] = React.useState<string | null>(null)
  const [currentPage, setCurrentPage] = React.useState<number>(1)
  const [highlightedPage, setHighlightedPage] =
    React.useState<HighlightedPageTarget | null>(null)
  const loadedDocIdRef = React.useRef<string | null>(null)

  const handleSelectCitationPage = React.useCallback(
    (pageNumber: number, citation?: ChatCitation) => {
      setActiveTab("pdf")
      setCurrentPage(pageNumber)
      setHighlightedPage({
        page: pageNumber,
        nonce: Date.now(),
        excerpt: citation?.content,
      })
    },
    []
  )

  // Jump to requested page when navigating from a Roadmap node
  React.useEffect(() => {
    if (!initialPageJump || initialPageJump.page < 1) return
    setActiveTab("pdf")
    setCurrentPage(initialPageJump.page)
    setHighlightedPage({
      page: initialPageJump.page,
      nonce: initialPageJump.nonce,
    })
  }, [initialPageJump])

  // Reset reader state only when switching to a different document ID
  React.useEffect(() => {
    setActiveTab("pdf")
    setContentData(null)
    setContentError(null)
    setCurrentPage(1)
    setHighlightedPage(null)
    loadedDocIdRef.current = null
    setResolvedPdfBlobUrl(document.localBlobUrl ?? null)
    setIsLoadingPdf(!document.localBlobUrl)
    setPdfError(null)
  }, [document.document_id, document.localBlobUrl])

  // Fetch authenticated PDF blob if not already cached in memory
  React.useEffect(() => {
    if (document.localBlobUrl) {
      setResolvedPdfBlobUrl(document.localBlobUrl)
      setIsLoadingPdf(false)
      setPdfError(null)
      return
    }

    let cancelled = false

    const loadPdfBlob = async () => {
      setIsLoadingPdf(true)
      setPdfError(null)
      try {
        const blobUrl = await fetchDocumentFileBlobUrl(document.document_id)
        if (cancelled) {
          URL.revokeObjectURL(blobUrl)
          return
        }
        setResolvedPdfBlobUrl(blobUrl)
        onCacheBlobUrl?.(document.document_id, blobUrl)
      } catch (err) {
        if (!cancelled) {
          setPdfError(
            err instanceof Error ? err.message : "Could not load PDF file."
          )
        }
      } finally {
        if (!cancelled) {
          setIsLoadingPdf(false)
        }
      }
    }

    void loadPdfBlob()
    return () => {
      cancelled = true
    }
  }, [document.document_id, document.localBlobUrl, onCacheBlobUrl])

  // Load parsed markdown when user switches to the Markdown tab (cached once ready/parsed)
  React.useEffect(() => {
    if (activeTab !== "markdown") return

    const isAlreadyFinal =
      contentData &&
      loadedDocIdRef.current === document.document_id &&
      (contentData.status === "ready" || contentData.status === "parsed") &&
      Boolean(contentData.full_content)

    if (isAlreadyFinal) return

    let cancelled = false

    const loadMarkdown = async () => {
      setIsLoadingContent(true)
      setContentError(null)
      try {
        const res = await fetchDocumentContent(document.document_id)
        if (!cancelled) {
          setContentData(res)
          loadedDocIdRef.current = document.document_id
        }
      } catch (err) {
        if (!cancelled) {
          setContentError(
            err instanceof Error
              ? err.message
              : "Could not load parsed content."
          )
        }
      } finally {
        if (!cancelled) {
          setIsLoadingContent(false)
        }
      }
    }

    void loadMarkdown()
    return () => {
      cancelled = true
    }
  }, [activeTab, document.document_id, document.status, contentData])

  // Pointer drag handler for resizable split divider
  const handleStartDrag = (e: React.PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    setIsDraggingSplit(true)
  }

  React.useEffect(() => {
    if (!isDraggingSplit) return

    const handlePointerMove = (e: PointerEvent) => {
      const container = splitContainerRef.current
      if (!container) return
      const rect = container.getBoundingClientRect()
      if (rect.width <= 0) return

      const relativeX = e.clientX - rect.left
      const rawPercent = (relativeX / rect.width) * 100
      const clamped = Math.min(
        MAX_SPLIT_PERCENT,
        Math.max(MIN_SPLIT_PERCENT, rawPercent)
      )
      setSplitRatio(Math.round(clamped * 10) / 10)
    }

    const handlePointerUp = () => {
      setIsDraggingSplit(false)
    }

    window.document.body.style.cursor = "col-resize"
    window.document.body.style.userSelect = "none"
    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)
    window.addEventListener("pointercancel", handlePointerUp)

    return () => {
      window.document.body.style.cursor = ""
      window.document.body.style.userSelect = ""
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
      window.removeEventListener("pointercancel", handlePointerUp)
    }
  }, [isDraggingSplit])

  const leftPaneWidthPercent = isSplitChatOpen ? splitRatio : 100
  const rightPaneWidthPercent = isSplitChatOpen ? 100 - splitRatio : 0

  return (
    <div className="flex-1 flex flex-col min-h-0 h-full bg-slate-50/70 dark:bg-slate-950">
      {/* Unified Reader Control Bar */}
      <div className="h-13 px-4 sm:px-6 border-b border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-950 flex items-center justify-between gap-3 shrink-0">
        {/* Left: Back Button & Document Title */}
        <div className="flex items-center gap-3 min-w-0">
          <button
            type="button"
            onClick={onBack}
            className="h-8 px-2.5 rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white hover:bg-slate-100 dark:bg-slate-900 dark:hover:bg-slate-800 text-xs font-medium text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 active:scale-[0.98]"
          >
            <ArrowLeft className="h-3.5 w-3.5 stroke-[2]" />
            <span>Back</span>
          </button>

          <div className="min-w-0 flex items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-900 dark:text-white truncate">
              {document.title}
            </h2>
            <span className="hidden md:inline-flex items-center rounded-md bg-slate-100 dark:bg-slate-900 px-2 py-0.5 text-[11px] font-mono text-slate-500 dark:text-slate-400 tabular-nums shrink-0">
              {document.total_pages}{" "}
              {document.total_pages === 1 ? "page" : "pages"}
            </span>
          </div>
        </div>

        {/* Right: View Switcher (PDF / Markdown) + Resizable AI Chat Split-View Toggle */}
        <div className="flex items-center gap-2.5 shrink-0">
          {/* Segmented View Control */}
          <div className="inline-flex items-center rounded-xl bg-slate-100 dark:bg-slate-900 p-0.5 border border-slate-200/70 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setActiveTab("pdf")}
              className={`h-7 px-2.5 rounded-[10px] text-xs font-medium inline-flex items-center gap-1.5 transition-all cursor-pointer ${
                activeTab === "pdf"
                  ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-2xs"
                  : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <FileText className="h-3.5 w-3.5 stroke-[1.8]" />
              <span>PDF</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("markdown")}
              className={`h-7 px-2.5 rounded-[10px] text-xs font-medium inline-flex items-center gap-1.5 transition-all cursor-pointer ${
                activeTab === "markdown"
                  ? "bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-2xs"
                  : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
              }`}
            >
              <AlignLeft className="h-3.5 w-3.5 stroke-[1.8]" />
              <span className="hidden sm:inline">Parsed Text</span>
            </button>
          </div>

          {resolvedPdfBlobUrl && (
            <a
              href={resolvedPdfBlobUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open PDF in new tab"
              title="Open PDF in new tab"
              className="hidden sm:inline-flex h-8 w-8 rounded-lg border border-slate-200/80 dark:border-slate-800 items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:hover:bg-slate-900 dark:hover:text-white transition-colors"
            >
              <ExternalLink className="h-3.5 w-3.5 stroke-[1.8]" />
            </a>
          )}

          {onOpenRoadmapGenerator &&
            (document.status === "ready" || document.status === "parsed") && (
              <button
                type="button"
                onClick={() => onOpenRoadmapGenerator(document)}
                title="Tạo lộ trình học tập từ giáo trình này"
                className="hidden sm:inline-flex h-8 px-2.5 rounded-lg border border-slate-200/80 dark:border-slate-800 items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-[#0A77FF] hover:border-[#0A77FF]/40 hover:bg-[#0A77FF]/5 dark:text-slate-300 dark:hover:text-sky-400 transition-colors cursor-pointer active:scale-[0.98]"
              >
                <Network className="h-3.5 w-3.5 stroke-[1.8]" />
                <span>Roadmap</span>
              </button>
            )}

          {/* Primary Split-View AI Tutor Toggle Button */}
          <button
            type="button"
            onClick={() => setIsSplitChatOpen((prev) => !prev)}
            aria-pressed={isSplitChatOpen}
            className={`h-8 px-3.5 rounded-xl text-xs font-semibold inline-flex items-center gap-2 transition-all duration-150 cursor-pointer active:scale-[0.98] ${
              isSplitChatOpen
                ? "bg-indigo-600 text-white shadow-[0_4px_12px_-2px_rgba(79,70,229,0.45)]"
                : "bg-indigo-600/10 hover:bg-indigo-600/15 text-indigo-600 dark:bg-indigo-500/20 dark:text-indigo-300"
            }`}
          >
            <Sparkles className="h-3.5 w-3.5 stroke-[2]" />
            <span>AI Tutor</span>
            <Columns2 className="h-3.5 w-3.5 opacity-80 stroke-[1.8]" />
          </button>
        </div>
      </div>

      {/* Main Content Area: Smooth Animated & Drag-Resizable Split-View */}
      <div
        ref={splitContainerRef}
        className="flex-1 flex flex-col lg:flex-row min-h-0 overflow-hidden relative"
      >
        {/* Left Pane: Document Content */}
        <div
          style={{ width: `${leftPaneWidthPercent}%` }}
          className={`h-full min-h-0 flex flex-col max-lg:!w-full will-change-[width] ${
            isDraggingSplit
              ? "transition-none"
              : "transition-[width] duration-350 ease-[cubic-bezier(0.16,1,0.3,1)]"
          }`}
        >
          {/* Keep PDF viewer mounted in DOM even when viewing Parsed Text tab */}
          <div
            className={
              activeTab === "pdf"
                ? "flex-1 w-full h-full bg-slate-200/60 dark:bg-slate-900 flex flex-col min-h-0"
                : "hidden"
            }
          >
            {isLoadingPdf ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                <span className="text-xs font-medium">
                  Loading PDF document...
                </span>
              </div>
            ) : pdfError ? (
              <div className="p-6">
                <div className="max-w-lg mx-auto rounded-xl border border-rose-200/80 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/30 p-4 text-xs text-rose-600 dark:text-rose-400">
                  {pdfError}
                </div>
              </div>
            ) : resolvedPdfBlobUrl ? (
              <PdfCanvasViewer
                key={document.document_id}
                fileUrl={resolvedPdfBlobUrl}
                title={document.title}
                highlightedPage={highlightedPage}
                onCurrentPageChange={setCurrentPage}
              />
            ) : null}
          </div>

          <div
            className={
              activeTab === "markdown"
                ? "flex-1 overflow-y-auto p-6 sm:p-8 bg-white dark:bg-slate-950"
                : "hidden"
            }
          >
            <div className="max-w-3xl mx-auto">
              {isLoadingContent ? (
                <div className="py-16 flex flex-col items-center justify-center gap-2 text-slate-400">
                  <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                  <span className="text-xs font-medium">
                    Loading extracted Markdown content...
                  </span>
                </div>
              ) : contentError ? (
                <div className="rounded-xl border border-rose-200/80 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/30 p-4 text-xs text-rose-600 dark:text-rose-400">
                  {contentError}
                </div>
              ) : contentData?.full_content ? (
                <article className="prose prose-slate dark:prose-invert max-w-none text-sm leading-relaxed text-slate-800 dark:text-slate-200">
                  <ChatMarkdownRenderer
                    content={contentData.full_content}
                    onSelectPage={handleSelectCitationPage}
                  />
                </article>
              ) : (
                <div className="py-16 text-center space-y-2">
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                    Markdown extraction is still in progress
                  </p>
                  <p className="text-xs text-slate-400 max-w-sm mx-auto">
                    Current status:{" "}
                    <span className="font-mono">{document.status}</span>. You
                    can read the original PDF right away using the PDF tab.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Interactive Drag-to-Resize Splitter Handle (Desktop) */}
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize PDF and AI Tutor panels"
          aria-valuenow={Math.round(splitRatio)}
          aria-valuemin={MIN_SPLIT_PERCENT}
          aria-valuemax={MAX_SPLIT_PERCENT}
          tabIndex={isSplitChatOpen ? 0 : -1}
          title="Drag to resize panels (double-click to reset)"
          onPointerDown={handleStartDrag}
          onDoubleClick={() => setSplitRatio(DEFAULT_SPLIT_PERCENT)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") {
              e.preventDefault()
              setSplitRatio((r) => Math.max(MIN_SPLIT_PERCENT, r - 3))
            } else if (e.key === "ArrowRight") {
              e.preventDefault()
              setSplitRatio((r) => Math.min(MAX_SPLIT_PERCENT, r + 3))
            }
          }}
          className={`hidden lg:flex w-0 z-20 items-center justify-center cursor-col-resize group select-none focus-visible:outline-none transition-opacity duration-300 ${
            isSplitChatOpen
              ? "opacity-100 pointer-events-auto"
              : "opacity-0 pointer-events-none"
          }`}
        >
          <div className="w-2.5 h-full flex items-center justify-center">
            <div
              className={`h-full w-[1px] transition-colors ${
                isDraggingSplit
                  ? "bg-indigo-600"
                  : "bg-slate-200/90 dark:bg-slate-800 group-hover:bg-indigo-600"
              }`}
            />
            <div
              className={`absolute h-7 w-4 rounded-md border flex items-center justify-center shadow-2xs transition-all ${
                isDraggingSplit
                  ? "bg-indigo-600 border-indigo-600 text-white scale-105"
                  : "bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-slate-400 group-hover:border-indigo-600 group-hover:text-indigo-600"
              }`}
            >
              <GripVertical className="h-3.5 w-3.5 stroke-[2]" />
            </div>
          </div>
        </div>

        {/* Right Pane: Smoothly Animated & Resizable AI Tutor Panel */}
        <div
          style={{ width: `${rightPaneWidthPercent}%` }}
          aria-hidden={!isSplitChatOpen}
          className={`min-h-0 shrink-0 overflow-hidden will-change-[width,opacity] ${
            isSplitChatOpen
              ? "max-lg:!w-full h-1/2 lg:h-full opacity-100"
              : "!w-0 h-0 lg:h-full opacity-0 pointer-events-none"
          } ${
            isDraggingSplit
              ? "transition-none"
              : "transition-[width,opacity] duration-350 ease-[cubic-bezier(0.16,1,0.3,1)]"
          }`}
        >
          <div className="h-full w-full min-w-[300px]">
            <AiTutorChatPanel
              document={document}
              currentPage={currentPage}
              onSelectCitationPage={handleSelectCitationPage}
              onClose={() => setIsSplitChatOpen(false)}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
