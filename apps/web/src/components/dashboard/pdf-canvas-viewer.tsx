"use client"

import * as React from "react"
import { Document, Page, pdfjs } from "react-pdf"
import {
  Loader2,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  ChevronUp,
  ChevronDown,
} from "lucide-react"

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs"

export interface HighlightedPageTarget {
  page: number
  nonce: number
  excerpt?: string
}

interface PdfCanvasViewerProps {
  fileUrl: string
  title: string
  highlightedPage?: HighlightedPageTarget | null
  onCurrentPageChange?: (page: number) => void
}

/**
 * Fixed high-DPI base render width so pdf.js rasterizes each page only ONCE.
 * All split-view animations, drag-resizing, and zoom adjustments scale purely
 * via CSS without ever re-triggering pdf.js canvas rendering or causing flashes.
 */
const BASE_RENDER_WIDTH = 960
const DEFAULT_MAX_DISPLAY_WIDTH = 880

export const PdfCanvasViewer = React.memo(function PdfCanvasViewer({
  fileUrl,
  title,
  highlightedPage,
  onCurrentPageChange,
}: PdfCanvasViewerProps) {
  const scrollContainerRef = React.useRef<HTMLDivElement>(null)
  const pageRefs = React.useRef<Record<number, HTMLDivElement | null>>({})

  const [loadedDoc, setLoadedDoc] = React.useState<{
    url: string
    numPages: number
  }>({ url: "", numPages: 0 })
  const [zoom, setZoom] = React.useState<number>(1)
  const [currentPage, setCurrentPage] = React.useState<number>(1)
  const [activeHighlightPage, setActiveHighlightPage] = React.useState<
    number | null
  >(null)

  // Synchronously ensure we never render stale page numbers from a previous PDF
  const activeNumPages = loadedDoc.url === fileUrl ? loadedDoc.numPages : 0

  // Notify parent when currentPage changes (outside of state updater to avoid setstate-in-render)
  React.useEffect(() => {
    onCurrentPageChange?.(currentPage)
  }, [currentPage, onCurrentPageChange])

  const handleZoomOut = () =>
    setZoom((prev) => Math.max(0.6, Math.round((prev - 0.15) * 100) / 100))
  const handleZoomIn = () =>
    setZoom((prev) => Math.min(2.0, Math.round((prev + 0.15) * 100) / 100))
  const handleZoomReset = () => setZoom(1)

  const scrollToPage = React.useCallback(
    (targetPage: number, smooth = true) => {
      if (activeNumPages <= 0) return
      const clamped = Math.max(1, Math.min(activeNumPages, targetPage))
      const pageEl = pageRefs.current[clamped]
      if (pageEl) {
        pageEl.scrollIntoView({
          behavior: smooth ? "smooth" : "auto",
          block: "start",
        })
        setCurrentPage(clamped)
      }
    },
    [activeNumPages]
  )

  // Handle citation click -> auto scroll to page + temporary visual highlight
  React.useEffect(() => {
    if (!highlightedPage || activeNumPages <= 0) return
    const target = Math.max(1, Math.min(activeNumPages, highlightedPage.page))

    const scrollTimer = window.setTimeout(() => {
      scrollToPage(target, true)
      setActiveHighlightPage(target)
    }, 40)

    const clearHighlightTimer = window.setTimeout(() => {
      setActiveHighlightPage((prev) => (prev === target ? null : prev))
    }, 3800)

    return () => {
      window.clearTimeout(scrollTimer)
      window.clearTimeout(clearHighlightTimer)
    }
  }, [highlightedPage, activeNumPages, scrollToPage])

  // Track which page is currently most visible while scrolling
  const handleScroll = React.useCallback(() => {
    const container = scrollContainerRef.current
    if (!container || activeNumPages <= 0) return

    const containerRect = container.getBoundingClientRect()
    const viewportMidY = containerRect.top + containerRect.height * 0.35

    let closestPage = 1
    let minDistance = Number.POSITIVE_INFINITY

    for (let p = 1; p <= activeNumPages; p++) {
      const el = pageRefs.current[p]
      if (!el) continue
      const rect = el.getBoundingClientRect()
      if (rect.top <= viewportMidY && rect.bottom >= viewportMidY) {
        closestPage = p
        break
      }
      const dist = Math.abs(rect.top - viewportMidY)
      if (dist < minDistance) {
        minDistance = dist
        closestPage = p
      }
    }

    setCurrentPage((prev) => (prev !== closestPage ? closestPage : prev))
  }, [activeNumPages])

  const maxDisplayWidth = Math.round(DEFAULT_MAX_DISPLAY_WIDTH * zoom)

  return (
    <div
      ref={scrollContainerRef}
      onScroll={handleScroll}
      aria-label={`PDF Viewer - ${title}`}
      className="relative flex-1 w-full h-full overflow-y-auto overflow-x-auto bg-slate-200/70 dark:bg-slate-900/90 scroll-smooth"
    >
      <div className="min-h-full py-6 px-4 sm:px-6 flex flex-col items-center">
        <Document
          key={fileUrl}
          file={fileUrl}
          onLoadSuccess={({ numPages }) => {
            setLoadedDoc({ url: fileUrl, numPages })
            setCurrentPage(1)
          }}
          loading={
            <div className="py-24 flex flex-col items-center justify-center gap-2 text-slate-500">
              <Loader2 className="h-5 w-5 animate-spin text-[#0A77FF]" />
              <span className="text-xs font-medium">Rendering PDF pages...</span>
            </div>
          }
          error={
            <div className="my-12 max-w-md rounded-xl border border-rose-200/80 dark:border-rose-900/50 bg-rose-50/80 dark:bg-rose-950/40 p-4 text-xs text-rose-600 dark:text-rose-400">
              Could not render PDF document. Try opening it in a new tab.
            </div>
          }
          className="flex flex-col items-center gap-6 w-full"
        >
          {activeNumPages > 0 &&
            Array.from({ length: activeNumPages }, (_, idx) => {
              const pageNumber = idx + 1
              const isHighlighted = activeHighlightPage === pageNumber

              return (
                <div
                  key={`${fileUrl}_page_${pageNumber}`}
                  ref={(el) => {
                    pageRefs.current[pageNumber] = el
                  }}
                  data-page-number={pageNumber}
                  style={{
                    width: zoom > 1 ? `${maxDisplayWidth}px` : "100%",
                    maxWidth: `${maxDisplayWidth}px`,
                  }}
                  className={`relative bg-white rounded-sm overflow-hidden transition-shadow duration-300 [&_.react-pdf__Page]:!w-full [&_.react-pdf__Page]:!min-w-0 [&_.react-pdf__Page]:!bg-white [&_canvas]:!w-full [&_canvas]:!h-auto [&_canvas]:block ${
                    isHighlighted
                      ? "ring-3 ring-indigo-600 shadow-[0_0_32px_rgba(79,70,229,0.42)]"
                      : "shadow-[0_4px_20px_-2px_rgba(15,23,42,0.12)] ring-1 ring-slate-900/5"
                  }`}
                >
                  <Page
                    pageNumber={pageNumber}
                    width={BASE_RENDER_WIDTH}
                    renderTextLayer={false}
                    renderAnnotationLayer={false}
                    loading={
                      <div className="w-full aspect-[1/1.414] bg-white animate-pulse" />
                    }
                  />
                </div>
              )
            })}
        </Document>
      </div>

      {/* Floating Bottom Page Navigation & Zoom Pill */}
      {activeNumPages > 0 && (
        <div className="sticky bottom-4 left-0 right-0 flex justify-center pointer-events-none z-10">
          <div className="pointer-events-auto inline-flex items-center gap-1 rounded-full bg-slate-900/85 dark:bg-slate-800/90 backdrop-blur-md text-white px-2.5 py-1 shadow-lg ring-1 ring-white/10 text-xs">
            <button
              type="button"
              onClick={() => scrollToPage(currentPage - 1)}
              disabled={currentPage <= 1}
              aria-label="Previous page"
              title="Trang trước"
              className="h-6 w-6 rounded-full hover:bg-white/15 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-35 disabled:pointer-events-none"
            >
              <ChevronUp className="h-3.5 w-3.5" />
            </button>

            <span className="px-1.5 font-mono text-[11px] text-slate-200 tabular-nums">
              Trang {currentPage} / {activeNumPages}
            </span>

            <button
              type="button"
              onClick={() => scrollToPage(currentPage + 1)}
              disabled={currentPage >= activeNumPages}
              aria-label="Next page"
              title="Trang tiếp"
              className="h-6 w-6 rounded-full hover:bg-white/15 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-35 disabled:pointer-events-none mr-1 border-r border-white/15 pr-1"
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </button>

            <button
              type="button"
              onClick={handleZoomOut}
              aria-label="Zoom out"
              title="Thu nhỏ"
              className="h-6 w-6 rounded-full hover:bg-white/15 flex items-center justify-center transition-colors cursor-pointer"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={handleZoomReset}
              aria-label="Reset zoom to fit width"
              title="Đặt lại tỷ lệ 100%"
              className="px-1.5 h-6 rounded-md hover:bg-white/15 font-mono text-[11px] tabular-nums inline-flex items-center gap-1 transition-colors cursor-pointer"
            >
              <span>{Math.round(zoom * 100)}%</span>
              {zoom !== 1 && <RotateCcw className="h-2.5 w-2.5 opacity-80" />}
            </button>
            <button
              type="button"
              onClick={handleZoomIn}
              aria-label="Zoom in"
              title="Phóng to"
              className="h-6 w-6 rounded-full hover:bg-white/15 flex items-center justify-center transition-colors cursor-pointer"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
})
