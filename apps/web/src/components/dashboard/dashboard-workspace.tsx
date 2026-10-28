"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import {
  AppSidebar,
  type SidebarSection,
} from "@/components/dashboard/app-sidebar"
import { TopHeader } from "@/components/dashboard/top-header"
import { DocumentUploadZone } from "@/components/dashboard/document-upload-zone"
import { DocumentList } from "@/components/dashboard/document-list"
import { DocumentViewer } from "@/components/dashboard/document-viewer"
import { RoadmapWorkspace } from "@/components/dashboard/roadmap-workspace"
import {
  fetchDocuments,
  deleteDocument,
  retryDocument,
  updateDocumentSubject,
  getAuthToken,
  type DocumentItem,
  type DocumentUploadResponse,
} from "@/lib/api/documents"
import {
  fetchSubjects,
  createSubject,
  deleteSubject,
  type SubjectItem,
} from "@/lib/api/roadmaps"
import {
  RefreshCw,
  Network,
  Plus,
  Check,
  X,
  Trash2,
  Loader2,
  ChevronLeft,
  ChevronRight,
} from "lucide-react"

export type LibraryFilterMode = "all" | "uncategorized" | string

export function DashboardWorkspace() {
  const router = useRouter()
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false)
  const [activeSection, setActiveSection] =
    React.useState<SidebarSection>("documents")
  const [documents, setDocuments] = React.useState<DocumentItem[]>([])
  const [subjects, setSubjects] = React.useState<SubjectItem[]>([])
  const [isLoadingDocs, setIsLoadingDocs] = React.useState(true)

  // Library subject filter & inline subject creation/deletion
  const [libraryFilter, setLibraryFilter] =
    React.useState<LibraryFilterMode>("all")
  const [isCreatingSubject, setIsCreatingSubject] = React.useState(false)
  const [newSubjectName, setNewSubjectName] = React.useState("")
  const [isSavingSubject, setIsSavingSubject] = React.useState(false)
  const [deletingSubjectId, setDeletingSubjectId] = React.useState<
    string | null
  >(null)

  // Horizontal scroll & drag-to-scroll for Subject filter bar
  const subjectScrollRef = React.useRef<HTMLDivElement | null>(null)
  const [canScrollLeft, setCanScrollLeft] = React.useState(false)
  const [canScrollRight, setCanScrollRight] = React.useState(false)
  const [isDraggingSubjects, setIsDraggingSubjects] = React.useState(false)
  const dragStateRef = React.useRef<{
    isDown: boolean
    startX: number
    scrollLeft: number
    hasDragged: boolean
  }>({
    isDown: false,
    startX: 0,
    scrollLeft: 0,
    hasDragged: false,
  })

  const updateSubjectScrollButtons = React.useCallback(() => {
    const el = subjectScrollRef.current
    if (!el) return
    setCanScrollLeft(el.scrollLeft > 2)
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 2)
  }, [])

  React.useEffect(() => {
    updateSubjectScrollButtons()
    window.addEventListener("resize", updateSubjectScrollButtons)
    return () =>
      window.removeEventListener("resize", updateSubjectScrollButtons)
  }, [subjects, documents.length, activeSection, updateSubjectScrollButtons])

  const scrollSubjectBarBy = (deltaX: number) => {
    const el = subjectScrollRef.current
    if (!el) return
    el.scrollBy({ left: deltaX, behavior: "smooth" })
  }

  const handleSubjectBarMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = subjectScrollRef.current
    if (!el || e.button !== 0) return
    dragStateRef.current = {
      isDown: true,
      startX: e.pageX - el.offsetLeft,
      scrollLeft: el.scrollLeft,
      hasDragged: false,
    }
  }

  const handleSubjectBarMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const el = subjectScrollRef.current
    if (!el || !dragStateRef.current.isDown) return
    const x = e.pageX - el.offsetLeft
    const walk = x - dragStateRef.current.startX
    if (Math.abs(walk) > 5) {
      dragStateRef.current.hasDragged = true
      if (!isDraggingSubjects) setIsDraggingSubjects(true)
      e.preventDefault()
      el.scrollLeft = dragStateRef.current.scrollLeft - walk * 1.25
      updateSubjectScrollButtons()
    }
  }

  const stopSubjectBarDragging = () => {
    if (!dragStateRef.current.isDown) return
    dragStateRef.current.isDown = false
    setIsDraggingSubjects(false)
  }

  const handleSubjectBarClickCapture = (
    e: React.MouseEvent<HTMLDivElement>
  ) => {
    if (dragStateRef.current.hasDragged) {
      e.stopPropagation()
      e.preventDefault()
      dragStateRef.current.hasDragged = false
    }
  }

  const handleSubjectBarWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    const el = subjectScrollRef.current
    if (!el) return
    if (el.scrollWidth > el.clientWidth && Math.abs(e.deltaY) > 0) {
      el.scrollLeft += e.deltaY
      updateSubjectScrollButtons()
    }
  }

  const [selectedDocId, setSelectedDocId] = React.useState<string | null>(null)
  const [lastOpenedDocId, setLastOpenedDocId] = React.useState<string | null>(
    null
  )
  const [preselectedRoadmapSubjectId, setPreselectedRoadmapSubjectId] =
    React.useState<string | null>(null)
  const [initialPageJump, setInitialPageJump] = React.useState<{
    page: number
    nonce: number
  } | null>(null)

  const blobUrlMapRef = React.useRef<Record<string, string>>({})

  const handleCacheBlobUrl = React.useCallback(
    (docId: string, blobUrl: string) => {
      blobUrlMapRef.current[docId] = blobUrl
      setDocuments((prev) =>
        prev.map((doc) =>
          doc.document_id === docId ? { ...doc, localBlobUrl: blobUrl } : doc
        )
      )
    },
    []
  )

  const loadWorkspaceData = React.useCallback(async () => {
    try {
      const [docList, subjList] = await Promise.all([
        fetchDocuments(),
        fetchSubjects().catch(() => []),
      ])
      setDocuments(
        docList.map((doc) => ({
          ...doc,
          localBlobUrl: blobUrlMapRef.current[doc.document_id],
        }))
      )
      setSubjects(subjList)
    } catch {
      // Keep existing state if backend is temporarily unreachable
    } finally {
      setIsLoadingDocs(false)
    }
  }, [])

  const handleManualRefresh = async () => {
    setIsLoadingDocs(true)
    await loadWorkspaceData()
  }

  // Initial auth check & load
  React.useEffect(() => {
    if (!getAuthToken()) {
      router.replace("/login")
      return
    }
    void loadWorkspaceData()
  }, [loadWorkspaceData, router])

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
      void loadWorkspaceData()
    }, 3000)

    return () => clearInterval(timer)
  }, [hasProcessing, loadWorkspaceData])

  // Cleanup local object URLs on unmount
  React.useEffect(() => {
    const map = blobUrlMapRef.current
    return () => {
      Object.values(map).forEach((url) => URL.revokeObjectURL(url))
    }
  }, [])

  const handleSelectDocument = React.useCallback((doc: DocumentItem) => {
    setActiveSection("documents")
    setSelectedDocId(doc.document_id)
    setLastOpenedDocId(doc.document_id)
  }, [])

  const handleOpenDocumentAtPage = React.useCallback(
    (documentId: string, pageNumber = 1) => {
      setActiveSection("documents")
      setSelectedDocId(documentId)
      setLastOpenedDocId(documentId)
      setInitialPageJump({
        page: pageNumber,
        nonce: Date.now(),
      })
    },
    []
  )

  const handleCreateSubject = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = newSubjectName.trim()
    if (!trimmed) return

    setIsSavingSubject(true)
    try {
      const created = await createSubject({
        name: trimmed,
        color_hex: "#0A77FF",
      })
      setSubjects((prev) => [
        created,
        ...prev.filter((s) => s.id !== created.id),
      ])
      setLibraryFilter(created.id)
      setNewSubjectName("")
      setIsCreatingSubject(false)
    } finally {
      setIsSavingSubject(false)
    }
  }

  const handleDeleteSubject = async (
    e: React.MouseEvent,
    subjectId: string
  ) => {
    e.stopPropagation()
    setDeletingSubjectId(subjectId)
    try {
      await deleteSubject(subjectId)
      setSubjects((prev) => prev.filter((s) => s.id !== subjectId))
      setDocuments((prev) =>
        prev.map((d) =>
          d.subject_id === subjectId ? { ...d, subject_id: null } : d
        )
      )
      if (libraryFilter === subjectId) {
        setLibraryFilter("all")
      }
      if (preselectedRoadmapSubjectId === subjectId) {
        setPreselectedRoadmapSubjectId(null)
      }
    } finally {
      setDeletingSubjectId(null)
    }
  }

  const handleAssignDocumentSubject = React.useCallback(
    async (docId: string, subjectId: string | null) => {
      const updated = await updateDocumentSubject(docId, subjectId)
      setDocuments((prev) =>
        prev.map((d) =>
          d.document_id === docId
            ? { ...d, subject_id: updated.subject_id ?? subjectId }
            : d
        )
      )
    },
    []
  )

  const handleUploaded = (res: DocumentUploadResponse, file: File) => {
    const blobUrl = URL.createObjectURL(file)
    blobUrlMapRef.current[res.document_id] = blobUrl

    const now = new Date().toISOString()
    const newItem: DocumentItem = {
      document_id: res.document_id,
      user_id: res.user_id,
      subject_id: res.subject_id ?? null,
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
    await loadWorkspaceData()
  }

  const filteredDocuments = React.useMemo(() => {
    if (libraryFilter === "all") return documents
    if (libraryFilter === "uncategorized") {
      return documents.filter((d) => !d.subject_id)
    }
    return documents.filter((d) => d.subject_id === libraryFilter)
  }, [documents, libraryFilter])

  const uncategorizedCount = React.useMemo(
    () => documents.filter((d) => !d.subject_id).length,
    [documents]
  )

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

  const isShowingReader =
    activeSection === "documents" && Boolean(activeDocument)

  const selectedFilterSubject = React.useMemo(
    () =>
      libraryFilter !== "all" && libraryFilter !== "uncategorized"
        ? subjects.find((s) => s.id === libraryFilter) || null
        : null,
    [libraryFilter, subjects]
  )

  return (
    <div className="h-screen w-full overflow-hidden flex bg-[#F8FAFC] dark:bg-slate-950">
      {/* Left Vertical Collapsible Menu */}
      <AppSidebar
        collapsed={sidebarCollapsed}
        activeSection={activeSection}
        onToggleCollapse={() => setSidebarCollapsed((prev) => !prev)}
        onSelectSection={(sec) => setActiveSection(sec)}
        onSelectDocumentsRoot={() => setSelectedDocId(null)}
      />

      {/* Right Main Area: Top Header + Dynamic Workspace */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        <TopHeader
          activeSection={activeSection}
          activeDocumentTitle={
            activeSection === "documents"
              ? activeDocument?.title ?? null
              : null
          }
          onBackToDocuments={() => {
            setActiveSection("documents")
            setSelectedDocId(null)
          }}
        />

        {/* Keep DocumentViewer mounted when returning to document list or Roadmap to eliminate PDF reload lag */}
        {cachedViewerDocument && (
          <main
            className={
              isShowingReader
                ? "flex-1 min-h-0 overflow-hidden flex flex-col"
                : "hidden"
            }
          >
            <DocumentViewer
              document={cachedViewerDocument}
              initialPageJump={initialPageJump}
              onBack={() => setSelectedDocId(null)}
              onCacheBlobUrl={handleCacheBlobUrl}
              onOpenRoadmapGenerator={(doc) => {
                if (doc.subject_id) {
                  setPreselectedRoadmapSubjectId(doc.subject_id)
                }
                setActiveSection("roadmap")
              }}
            />
          </main>
        )}

        {/* Roadmap Generator & Outline Workspace */}
        <main
          className={
            activeSection === "roadmap"
              ? "flex-1 min-h-0 overflow-hidden flex flex-col"
              : "hidden"
          }
        >
          <RoadmapWorkspace
            documents={documents}
            subjects={subjects}
            preselectedSubjectId={preselectedRoadmapSubjectId}
            onOpenDocumentAtPage={handleOpenDocumentAtPage}
            onSwitchToDocuments={(filterSubjId) => {
              if (filterSubjId) {
                setLibraryFilter(filterSubjId)
              }
              setActiveSection("documents")
              setSelectedDocId(null)
            }}
          />
        </main>

        {/* Documents Library Workspace */}
        <main
          className={
            activeSection === "documents" && !activeDocument
              ? "flex-1 overflow-y-auto overflow-x-hidden px-6 py-8"
              : "hidden"
          }
        >
          <div className="max-w-5xl w-full min-w-0 mx-auto space-y-8">
            {/* Page Heading + Refresh Control */}
            <div className="flex items-end justify-between gap-4">
              <div className="space-y-1">
                <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
                  Study Documents
                </h1>
                <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400">
                  Upload PDF textbooks and assign them to subjects to study with
                  AI Tutor or synthesize into a unified study roadmap.
                </p>
              </div>

              <button
                type="button"
                onClick={() => void handleManualRefresh()}
                aria-label="Refresh document list"
                title="Refresh"
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

            {/* 2. Uploaded Documents Library + Subject Management & Filter Bar */}
            <section
              aria-label="Uploaded documents"
              className="space-y-3.5 min-w-0"
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                    Your Library
                  </h2>
                  <span className="text-xs font-mono text-slate-400 dark:text-slate-500 tabular-nums">
                    {filteredDocuments.length}{" "}
                    {filteredDocuments.length === 1 ? "document" : "documents"}
                  </span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {selectedFilterSubject && (
                    <button
                      type="button"
                      onClick={() => {
                        setPreselectedRoadmapSubjectId(selectedFilterSubject.id)
                        setActiveSection("roadmap")
                      }}
                      className="h-8 px-3 rounded-lg bg-[#0A77FF]/10 hover:bg-[#0A77FF]/15 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300 text-xs font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer active:scale-[0.97]"
                    >
                      <Network className="h-3.5 w-3.5 stroke-[1.8]" />
                      <span>
                        Generate Roadmap for {selectedFilterSubject.name}
                      </span>
                    </button>
                  )}

                  {!isCreatingSubject ? (
                    <button
                      type="button"
                      onClick={() => setIsCreatingSubject(true)}
                      className="h-8 px-3 rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-[#0A77FF]/40 hover:text-[#0A77FF] text-xs font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-1.5 transition-colors cursor-pointer active:scale-[0.97]"
                    >
                      <Plus className="h-3.5 w-3.5 stroke-[2]" />
                      <span>New Subject</span>
                    </button>
                  ) : (
                    <form
                      onSubmit={handleCreateSubject}
                      className="flex items-center gap-1.5"
                    >
                      <input
                        type="text"
                        autoFocus
                        value={newSubjectName}
                        onChange={(e) => setNewSubjectName(e.target.value)}
                        placeholder="Subject name (e.g. Calculus 1)..."
                        className="h-8 w-44 sm:w-52 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-2.5 text-xs text-slate-900 dark:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                      />
                      <button
                        type="submit"
                        disabled={isSavingSubject || !newSubjectName.trim()}
                        aria-label="Save subject"
                        className="h-8 px-2.5 rounded-lg bg-[#0A77FF] text-white text-xs font-semibold inline-flex items-center gap-1 disabled:opacity-50 cursor-pointer"
                      >
                        {isSavingSubject ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Check className="h-3.5 w-3.5" />
                        )}
                        <span>Save</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setIsCreatingSubject(false)
                          setNewSubjectName("")
                        }}
                        aria-label="Cancel creating subject"
                        className="h-8 w-8 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-center text-slate-400 hover:text-slate-700 cursor-pointer"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </form>
                  )}
                </div>
              </div>

              {/* Unified Subject Filter Bar with Drag-to-Scroll, Wheel Scroll & Arrow Controls */}
              <div className="relative flex items-center gap-1.5 min-w-0 w-full">
                {canScrollLeft && (
                  <button
                    type="button"
                    onClick={() => scrollSubjectBarBy(-240)}
                    aria-label="Scroll subjects left"
                    title="Scroll left"
                    className="h-8 w-8 rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 flex items-center justify-center shrink-0 shadow-2xs transition-colors cursor-pointer active:scale-[0.96]"
                  >
                    <ChevronLeft className="h-4 w-4 stroke-[2]" />
                  </button>
                )}

                <div
                  ref={subjectScrollRef}
                  role="tablist"
                  aria-label="Filter documents by subject"
                  onScroll={updateSubjectScrollButtons}
                  onWheel={handleSubjectBarWheel}
                  onMouseDown={handleSubjectBarMouseDown}
                  onMouseMove={handleSubjectBarMouseMove}
                  onMouseUp={stopSubjectBarDragging}
                  onMouseLeave={stopSubjectBarDragging}
                  onClickCapture={handleSubjectBarClickCapture}
                  className={`flex-1 min-w-0 flex items-center gap-1.5 overflow-x-auto pb-1.5 select-none [&::-webkit-scrollbar]:h-1.5 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-slate-200 dark:[&::-webkit-scrollbar-thumb]:bg-slate-800 hover:[&::-webkit-scrollbar-thumb]:bg-slate-300 dark:hover:[&::-webkit-scrollbar-thumb]:bg-slate-700 ${
                    isDraggingSubjects ? "cursor-grabbing" : "cursor-grab"
                  }`}
                >
                  <button
                    type="button"
                    role="tab"
                    aria-selected={libraryFilter === "all"}
                    onClick={() => setLibraryFilter("all")}
                    className={`h-8 px-3 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 shrink-0 transition-colors cursor-pointer tabular-nums ${
                      libraryFilter === "all"
                        ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                        : "bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                    }`}
                  >
                    <span>All</span>
                    <span
                      className={`font-mono text-[11px] ${
                        libraryFilter === "all"
                          ? "text-white/85"
                          : "text-slate-400"
                      }`}
                    >
                      ({documents.length})
                    </span>
                  </button>

                  {subjects.map((subj) => {
                    const count = documents.filter(
                      (d) => d.subject_id === subj.id
                    ).length
                    const isActive = libraryFilter === subj.id
                    const isDeletingSubj = deletingSubjectId === subj.id

                    return (
                      <div
                        key={subj.id}
                        className={`h-8 pl-3 pr-1.5 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 shrink-0 transition-colors tabular-nums ${
                          isActive
                            ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                            : "bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                        }`}
                      >
                        <button
                          type="button"
                          role="tab"
                          aria-selected={isActive}
                          onClick={() => setLibraryFilter(subj.id)}
                          className="inline-flex items-center gap-1.5 h-full cursor-pointer focus-visible:outline-none"
                        >
                          <span className="truncate max-w-[160px]">
                            {subj.name}
                          </span>
                          <span
                            className={`font-mono text-[11px] ${
                              isActive ? "text-white/85" : "text-slate-400"
                            }`}
                          >
                            ({count})
                          </span>
                        </button>

                        <button
                          type="button"
                          disabled={isDeletingSubj}
                          onClick={(e) => void handleDeleteSubject(e, subj.id)}
                          aria-label={`Delete subject ${subj.name}`}
                          title={`Delete subject ${subj.name}`}
                          className={`h-5 w-5 rounded flex items-center justify-center transition-colors cursor-pointer ${
                            isActive
                              ? "text-white/75 hover:text-white hover:bg-white/20"
                              : "text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40"
                          }`}
                        >
                          {isDeletingSubj ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Trash2 className="h-3 w-3 stroke-[1.8]" />
                          )}
                        </button>
                      </div>
                    )
                  })}

                  <button
                    type="button"
                    role="tab"
                    aria-selected={libraryFilter === "uncategorized"}
                    onClick={() => setLibraryFilter("uncategorized")}
                    className={`h-8 px-3 rounded-lg text-xs font-medium inline-flex items-center gap-1.5 shrink-0 transition-colors cursor-pointer tabular-nums ${
                      libraryFilter === "uncategorized"
                        ? "bg-[#0A77FF] text-white font-semibold shadow-2xs"
                        : "bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                    }`}
                  >
                    <span>Uncategorized</span>
                    <span
                      className={`font-mono text-[11px] ${
                        libraryFilter === "uncategorized"
                          ? "text-white/85"
                          : "text-slate-400"
                      }`}
                    >
                      ({uncategorizedCount})
                    </span>
                  </button>
                </div>

                {canScrollRight && (
                  <button
                    type="button"
                    onClick={() => scrollSubjectBarBy(240)}
                    aria-label="Scroll subjects right"
                    title="Scroll right"
                    className="h-8 w-8 rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 flex items-center justify-center shrink-0 shadow-2xs transition-colors cursor-pointer active:scale-[0.96]"
                  >
                    <ChevronRight className="h-4 w-4 stroke-[2]" />
                  </button>
                )}
              </div>

              <DocumentList
                documents={filteredDocuments}
                subjects={subjects}
                isLoading={isLoadingDocs}
                onSelectDocument={handleSelectDocument}
                onDeleteDocument={handleDelete}
                onRetryDocument={handleRetry}
                onAssignSubject={handleAssignDocumentSubject}
              />
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}
