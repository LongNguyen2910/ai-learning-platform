"use client"

import * as React from "react"
import { Document, Page, pdfjs } from "react-pdf"
import { Loader2, ZoomIn, ZoomOut, RotateCcw } from "lucide-react"

pdfjs.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.mjs"

interface PdfCanvasViewerProps {
  fileUrl: string
  title: string
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
}: PdfCanvasViewerProps) {
  const [loadedDoc, setLoadedDoc] = React.useState<{
    url: string
    numPages: number
  }>({ url: "", numPages: 0 })
  const [zoom, setZoom] = React.useState<number>(1)

  // Synchronously ensure we never render stale page numbers from a previous PDF
  const activeNumPages = loadedDoc.url === fileUrl ? loadedDoc.numPages : 0

  const handleZoomOut = () =>
    setZoom((prev) => Math.max(0.6, Math.round((prev - 0.15) * 100) / 100))
  const handleZoomIn = () =>
    setZoom((prev) => Math.min(2.0, Math.round((prev + 0.15) * 100) / 100))
  const handleZoomReset = () => setZoom(1)

  const maxDisplayWidth = Math.round(DEFAULT_MAX_DISPLAY_WIDTH * zoom)

  return (
    <div
      aria-label={`PDF Viewer - ${title}`}
      className="relative flex-1 w-full h-full overflow-y-auto overflow-x-auto bg-slate-200/70 dark:bg-slate-900/90"
    >
      <div className="min-h-full py-6 px-4 sm:px-6 flex flex-col items-center">
        <Document
          key={fileUrl}
          file={fileUrl}
          onLoadSuccess={({ numPages }) =>
            setLoadedDoc({ url: fileUrl, numPages })
          }
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
          className="flex flex-col items-center gap-5 w-full"
        >
          {activeNumPages > 0 &&
            Array.from({ length: activeNumPages }, (_, idx) => {
              const pageNumber = idx + 1
              return (
                <div
                  key={`${fileUrl}_page_${pageNumber}`}
                  style={{
                    width: zoom > 1 ? `${maxDisplayWidth}px` : "100%",
                    maxWidth: `${maxDisplayWidth}px`,
                  }}
                  className="relative bg-white shadow-[0_4px_20px_-2px_rgba(15,23,42,0.12)] ring-1 ring-slate-900/5 rounded-sm overflow-hidden [&_.react-pdf__Page]:!w-full [&_.react-pdf__Page]:!min-w-0 [&_.react-pdf__Page]:!bg-white [&_canvas]:!w-full [&_canvas]:!h-auto [&_canvas]:block"
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

      {/* Floating Bottom Zoom & Page Pill */}
      {activeNumPages > 0 && (
        <div className="sticky bottom-4 left-0 right-0 flex justify-center pointer-events-none z-10">
          <div className="pointer-events-auto inline-flex items-center gap-1 rounded-full bg-slate-900/85 dark:bg-slate-800/90 backdrop-blur-md text-white px-2.5 py-1 shadow-lg ring-1 ring-white/10 text-xs">
            <span className="px-2 font-mono text-[11px] text-slate-300 tabular-nums border-r border-white/15">
              {activeNumPages} {activeNumPages === 1 ? "page" : "pages"}
            </span>
            <button
              type="button"
              onClick={handleZoomOut}
              aria-label="Zoom out"
              title="Zoom out"
              className="h-6 w-6 rounded-full hover:bg-white/15 flex items-center justify-center transition-colors cursor-pointer"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={handleZoomReset}
              aria-label="Reset zoom to fit width"
              title="Reset to Fit Width"
              className="px-1.5 h-6 rounded-md hover:bg-white/15 font-mono text-[11px] tabular-nums inline-flex items-center gap-1 transition-colors cursor-pointer"
            >
              <span>{Math.round(zoom * 100)}%</span>
              {zoom !== 1 && <RotateCcw className="h-2.5 w-2.5 opacity-80" />}
            </button>
            <button
              type="button"
              onClick={handleZoomIn}
              aria-label="Zoom in"
              title="Zoom in"
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
