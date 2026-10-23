"use client"

import * as React from "react"
import { AppSidebar } from "@/components/dashboard/app-sidebar"
import { TopHeader } from "@/components/dashboard/top-header"
import { DocumentUploadZone } from "@/components/dashboard/document-upload-zone"
import { DocumentList } from "@/components/dashboard/document-list"
import { DocumentViewer } from "@/components/dashboard/document-viewer"
import {
  fetchDocuments,
  deleteDocument,
  retryDocument,
  type DocumentItem,
  type DocumentUploadResponse,
} from "@/lib/api/documents"
import { RefreshCw } from "lucide-react"

export function DashboardWorkspace() {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false)
  const [documents, setDocuments] = React.useState<DocumentItem[]>([])
  const [isLoadingDocs, setIsLoadingDocs] = React.useState(true)
  const [selectedDocId, setSelectedDocId] = React.useState<string | null>(null)
  const [lastOpenedDocId, setLastOpenedDocId] = React.useState<string | null>(
    null
  )
  const blobUrlMapRef = React.useRef<Record<string, string>>({})

  const loadDocuments = React.useCallback(async () => {
    try {
      const list = await fetchDocuments()
      setDocuments(
        list.map((doc) => ({
          ...doc,
          localBlobUrl: blobUrlMapRef.current[doc.document_id],
        }))
      )
    } catch {
      // Keep existing state if backend is temporarily unreachable
    } finally {
      setIsLoadingDocs(false)
    }
  }, [])

  const handleManualRefresh = async () => {
    setIsLoadingDocs(true)
    await loadDocuments()
  }

  // Initial load
  React.useEffect(() => {
    void loadDocuments()
  }, [loadDocuments])

  const hasProcessing = React.useMemo(
    () =>
      documents.some(
        (d) =>
          d.status === "uploading" ||
          d.status === "parsing" ||
          d.status === "indexing"
      ),
    [documents]
  )

  // Poll every 3s while any document is still processing
  React.useEffect(() => {
    if (!hasProcessing) return

    const timer = setInterval(() => {
      void loadDocuments()
    }, 3000)

    return () => clearInterval(timer)
  }, [hasProcessing, loadDocuments])

  // Cleanup local object URLs on unmount
  React.useEffect(() => {
    const map = blobUrlMapRef.current
    return () => {
      Object.values(map).forEach((url) => URL.revokeObjectURL(url))
    }
  }, [])

  const handleSelectDocument = React.useCallback((doc: DocumentItem) => {
    setSelectedDocId(doc.document_id)
    setLastOpenedDocId(doc.document_id)
  }, [])

  const handleUploaded = (res: DocumentUploadResponse, file: File) => {
    const blobUrl = URL.createObjectURL(file)
    blobUrlMapRef.current[res.document_id] = blobUrl

    const now = new Date().toISOString()
    const newItem: DocumentItem = {
      document_id: res.document_id,
      title: res.title,
      status: res.status,
      file_size_kb: Math.max(1, Math.round(file.size / 1024)),
      total_pages: res.total_pages,
      parsed_pages: 0,
      created_at: now,
      updated_at: now,
      localBlobUrl: blobUrl,
    }

    setDocuments((prev) => [
      newItem,
      ...prev.filter((d) => d.document_id !== res.document_id),
    ])
  }

  const handleDelete = async (docId: string) => {
    await deleteDocument(docId)
    if (blobUrlMapRef.current[docId]) {
      URL.revokeObjectURL(blobUrlMapRef.current[docId])
      delete blobUrlMapRef.current[docId]
    }
    setDocuments((prev) => prev.filter((d) => d.document_id !== docId))
    if (selectedDocId === docId) {
      setSelectedDocId(null)
    }
    if (lastOpenedDocId === docId) {
      setLastOpenedDocId(null)
    }
  }

  const handleRetry = async (docId: string) => {
    await retryDocument(docId)
    await loadDocuments()
  }

  const activeDocument = React.useMemo(
    () => documents.find((d) => d.document_id === selectedDocId) || null,
    [documents, selectedDocId]
  )

  const cachedViewerDocument = React.useMemo(
    () =>
      activeDocument ||
      documents.find((d) => d.document_id === lastOpenedDocId) ||
      null,
    [activeDocument, documents, lastOpenedDocId]
  )

  return (
    <div className="h-screen w-full overflow-hidden flex bg-[#F8FAFC] dark:bg-slate-950">
      {/* Left Vertical Collapsible Menu */}
      <AppSidebar
        collapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        onSelectDocumentsRoot={() => setSelectedDocId(null)}
      />

      {/* Right Main Area: Top Header + Dynamic Workspace */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <TopHeader
          activeDocumentTitle={activeDocument?.title ?? null}
          onBackToDocuments={() => setSelectedDocId(null)}
        />

        {/* Keep DocumentViewer mounted when returning to document list to eliminate PDF reload lag */}
        {cachedViewerDocument && (
          <main
            className={
              activeDocument
                ? "flex-1 min-h-0 overflow-hidden flex flex-col"
                : "hidden"
            }
          >
            <DocumentViewer
              document={cachedViewerDocument}
              onBack={() => setSelectedDocId(null)}
            />
          </main>
        )}

        <main
          className={
            activeDocument ? "hidden" : "flex-1 overflow-y-auto px-6 py-8"
          }
        >
          <div className="max-w-5xl mx-auto space-y-8">
            {/* Page Heading + Refresh Control */}
            <div className="flex items-end justify-between gap-4">
              <div className="space-y-1">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
                  Study Documents
                </h1>
                <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
                  Upload your course PDFs and open any document to read
                  alongside your AI Tutor.
                </p>
              </div>

              <button
                type="button"
                onClick={() => void handleManualRefresh()}
                aria-label="Refresh document list"
                title="Refresh list"
                className="h-9 px-3 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-2 transition-colors cursor-pointer shrink-0 active:scale-[0.98]"
              >
                <RefreshCw
                  className={`h-3.5 w-3.5 stroke-[1.8] ${
                    isLoadingDocs ? "animate-spin" : ""
                  }`}
                />
                <span className="hidden sm:inline">Refresh</span>
              </button>
            </div>

            {/* 1. Primary Focal Action: Upload PDF Dropzone */}
            <section aria-label="Upload new PDF">
              <DocumentUploadZone onUploaded={handleUploaded} />
            </section>

            {/* 2. Uploaded Documents Library */}
            <section aria-label="Uploaded documents" className="space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  Your Library
                </h2>
                <span className="text-xs font-mono text-slate-400 dark:text-slate-500 tabular-nums">
                  {documents.length}{" "}
                  {documents.length === 1 ? "document" : "documents"}
                </span>
              </div>

              <DocumentList
                documents={documents}
                isLoading={isLoadingDocs}
                onSelectDocument={handleSelectDocument}
                onDeleteDocument={handleDelete}
                onRetryDocument={handleRetry}
              />
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}
