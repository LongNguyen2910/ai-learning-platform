"use client"

import * as React from "react"
import {
  ArrowLeft,
  Columns2,
  FileText,
  AlignLeft,
  Loader2,
  ExternalLink,
  Sparkles,
} from "lucide-react"
import {
  fetchDocumentContent,
  fetchDocumentFileBlobUrl,
  type DocumentContentResponse,
  type DocumentItem,
} from "@/lib/api/documents"
import { AiChatPlaceholder } from "@/components/dashboard/ai-chat-placeholder"

interface DocumentViewerProps {
  document: DocumentItem
  onBack: () => void
  onCacheBlobUrl?: (documentId: string, blobUrl: string) => void
}

type ReaderTab = "pdf" | "markdown"

export function DocumentViewer({
  document,
  onBack,
  onCacheBlobUrl,
}: DocumentViewerProps) {
  const [activeTab, setActiveTab] = React.useState<ReaderTab>("pdf")
  const [isSplitChatOpen, setIsSplitChatOpen] = React.useState(false)
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
  const loadedDocIdRef = React.useRef<string | null>(null)

  // Reset reader state only when switching to a different document ID
  React.useEffect(() => {
    setActiveTab("pdf")
    setContentData(null)
    setContentError(null)
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

    // Skip network fetch if we already cached the completed markdown for this document
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

  const pdfViewerUrl = resolvedPdfBlobUrl
    ? `${resolvedPdfBlobUrl}#view=FitH`
    : null

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

        {/* Right: View Switcher (PDF / Markdown) + 50/50 AI Chat Split-View Toggle */}
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

          {/* Primary 50/50 Split-View AI Tutor Toggle Button */}
          <button
            type="button"
            onClick={() => setIsSplitChatOpen((prev) => !prev)}
            aria-pressed={isSplitChatOpen}
            className={`h-8 px-3.5 rounded-xl text-xs font-semibold inline-flex items-center gap-2 transition-all duration-150 cursor-pointer active:scale-[0.98] ${
              isSplitChatOpen
                ? "bg-[#0A77FF] text-white shadow-[0_4px_12px_-2px_rgba(10,119,255,0.45)]"
                : "bg-[#0A77FF]/10 hover:bg-[#0A77FF]/15 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300"
            }`}
          >
            <Sparkles className="h-3.5 w-3.5 stroke-[2]" />
            <span>AI Tutor</span>
            <Columns2 className="h-3.5 w-3.5 opacity-80 stroke-[1.8]" />
          </button>
        </div>
      </div>

      {/* Main Content Area: 100% Full Width OR 50/50 Split-View */}
      <div className="flex-1 flex flex-col lg:flex-row min-h-0 overflow-hidden">
        {/* Left Pane: Document Content (100% when chat closed, 50% when chat open) */}
        <div
          className={`h-full min-h-0 flex flex-col ${
            isSplitChatOpen ? "w-full lg:w-1/2" : "w-full"
          }`}
        >
          {/* Keep PDF iframe mounted in DOM even when viewing Parsed Text tab to avoid reload lag */}
          <div
            className={
              activeTab === "pdf"
                ? "flex-1 w-full h-full bg-slate-200/60 dark:bg-slate-900 flex flex-col"
                : "hidden"
            }
          >
            {isLoadingPdf ? (
              <div className="flex-1 flex flex-col items-center justify-center gap-2 text-slate-400">
                <Loader2 className="h-5 w-5 animate-spin text-[#0A77FF]" />
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
            ) : pdfViewerUrl ? (
              <iframe
                key={`${document.document_id}-${isSplitChatOpen ? "split" : "full"}`}
                src={pdfViewerUrl}
                title={`PDF Viewer - ${document.title}`}
                className="w-full h-full border-0"
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
                  <Loader2 className="h-5 w-5 animate-spin text-[#0A77FF]" />
                  <span className="text-xs font-medium">
                    Loading extracted Markdown content...
                  </span>
                </div>
              ) : contentError ? (
                <div className="rounded-xl border border-rose-200/80 dark:border-rose-900/50 bg-rose-50/60 dark:bg-rose-950/30 p-4 text-xs text-rose-600 dark:text-rose-400">
                  {contentError}
                </div>
              ) : contentData?.full_content ? (
                <article className="prose prose-slate dark:prose-invert max-w-none">
                  <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-slate-800 dark:text-slate-200 bg-transparent p-0 border-0">
                    {contentData.full_content}
                  </pre>
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

        {/* Right Pane: 50% AI Tutor Split-View Placeholder */}
        {isSplitChatOpen && (
          <div className="w-full lg:w-1/2 h-1/2 lg:h-full min-h-0 shrink-0 animate-in fade-in-0 slide-in-from-right-4 duration-200">
            <AiChatPlaceholder
              document={document}
              onClose={() => setIsSplitChatOpen(false)}
            />
          </div>
        )}
      </div>
    </div>
  )
}
