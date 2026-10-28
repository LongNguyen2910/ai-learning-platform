"use client"

import * as React from "react"
import {
  FileText,
  Trash2,
  RotateCw,
  Loader2,
  ArrowUpRight,
  FolderOpen,
} from "lucide-react"
import type { DocumentItem, DocumentStatus } from "@/lib/api/documents"
import type { SubjectItem } from "@/lib/api/roadmaps"

interface DocumentListProps {
  documents: DocumentItem[]
  subjects: SubjectItem[]
  isLoading: boolean
  onSelectDocument: (doc: DocumentItem) => void
  onDeleteDocument: (docId: string) => Promise<void>
  onRetryDocument: (docId: string) => Promise<void>
  onAssignSubject: (docId: string, subjectId: string | null) => Promise<void>
}

function formatFileSize(kb?: number): string {
  if (!kb || kb <= 0) return "PDF"
  if (kb < 1024) return `${kb} KB`
  return `${(kb / 1024).toFixed(1)} MB`
}

function formatDate(isoString: string): string {
  try {
    const date = new Date(isoString)
    return date.toLocaleDateString("vi-VN", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    })
  } catch {
    return ""
  }
}

function StatusIndicator({
  status,
  parsedPages,
  totalPages,
}: {
  status: DocumentStatus
  parsedPages: number
  totalPages: number
}) {
  if (status === "ready" || status === "parsed") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400 tabular-nums">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        <span>Sẵn sàng</span>
      </span>
    )
  }

  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-rose-600 dark:text-rose-400">
        <span className="h-1.5 w-1.5 rounded-full bg-rose-500" />
        <span>Lỗi xử lý</span>
      </span>
    )
  }

  const label =
    status === "indexing"
      ? "Đang lập chỉ mục..."
      : status === "parsing" && totalPages > 0
      ? `Đang đọc ${parsedPages}/${totalPages} trang`
      : "Đang xử lý..."

  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[#0A77FF] dark:text-sky-400 tabular-nums">
      <Loader2 className="h-3 w-3 animate-spin" />
      <span>{label}</span>
    </span>
  )
}

export function DocumentList({
  documents,
  subjects,
  isLoading,
  onSelectDocument,
  onDeleteDocument,
  onRetryDocument,
  onAssignSubject,
}: DocumentListProps) {
  const [busyId, setBusyId] = React.useState<string | null>(null)
  const [assigningId, setAssigningId] = React.useState<string | null>(null)

  const handleDelete = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation()
    setBusyId(docId)
    try {
      await onDeleteDocument(docId)
    } finally {
      setBusyId(null)
    }
  }

  const handleRetry = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation()
    setBusyId(docId)
    try {
      await onRetryDocument(docId)
    } finally {
      setBusyId(null)
    }
  }

  const handleSubjectChange = async (
    e: React.ChangeEvent<HTMLSelectElement>,
    docId: string
  ) => {
    e.stopPropagation()
    const nextSubjectId = e.target.value ? e.target.value : null
    setAssigningId(docId)
    try {
      await onAssignSubject(docId, nextSubjectId)
    } finally {
      setAssigningId(null)
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-2.5">
        {[1, 2, 3].map((item) => (
          <div
            key={item}
            className="h-16 w-full rounded-xl bg-slate-100/80 dark:bg-slate-900/60 animate-pulse border border-slate-200/50 dark:border-slate-800/50"
          />
        ))}
      </div>
    )
  }

  if (documents.length === 0) {
    return (
      <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900/40 py-14 px-6 text-center">
        <div className="mx-auto h-11 w-11 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mb-3">
          <FolderOpen className="h-5 w-5 stroke-[1.75]" />
        </div>
        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
          Không có tài liệu nào trong danh mục này
        </h3>
        <p className="text-xs text-slate-500 dark:text-slate-400 max-w-sm mx-auto mt-1">
          Tải tài liệu PDF lên ở khung trên hoặc chọn bộ lọc môn học khác để xem
          tài liệu.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900/60 divide-y divide-slate-200/70 dark:divide-slate-800/70 overflow-hidden">
      {documents.map((doc) => {
        const isBusy = busyId === doc.document_id
        const isAssigning = assigningId === doc.document_id

        return (
          <div
            key={doc.document_id}
            onClick={() => onSelectDocument(doc)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault()
                onSelectDocument(doc)
              }
            }}
            className="group flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 py-4 hover:bg-slate-50/90 dark:hover:bg-slate-800/40 transition-colors duration-150 cursor-pointer focus-visible:outline-none focus-visible:bg-slate-50 dark:focus-visible:bg-slate-800/50"
          >
            {/* Left: Icon + Title + Metadata */}
            <div className="flex items-center gap-3.5 min-w-0 flex-1">
              <div className="h-10 w-10 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 group-hover:bg-[#0A77FF]/10 group-hover:text-[#0A77FF] dark:group-hover:bg-[#0A77FF]/20 dark:group-hover:text-sky-400 flex items-center justify-center shrink-0 transition-colors">
                <FileText className="h-5 w-5 stroke-[1.75]" />
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-slate-900 dark:text-white truncate group-hover:text-[#0A77FF] dark:group-hover:text-sky-400 transition-colors">
                    {doc.title}
                  </p>
                  <ArrowUpRight className="h-3.5 w-3.5 text-slate-300 dark:text-slate-600 opacity-0 group-hover:opacity-100 group-hover:text-[#0A77FF] transition-all shrink-0" />
                </div>

                <div className="flex items-center gap-2 text-xs text-slate-400 dark:text-slate-500 tabular-nums mt-0.5">
                  <span>{doc.total_pages} trang</span>
                  <span>·</span>
                  <span>{formatFileSize(doc.file_size_kb)}</span>
                  {doc.created_at && (
                    <>
                      <span className="hidden sm:inline">·</span>
                      <span className="hidden sm:inline">
                        {formatDate(doc.created_at)}
                      </span>
                    </>
                  )}
                </div>

                {doc.status === "failed" && doc.error_message && (
                  <p
                    className="text-[11px] text-rose-500 line-clamp-2 max-w-md mt-1 font-medium"
                    title={doc.error_message}
                  >
                    {doc.error_message}
                  </p>
                )}
              </div>
            </div>

            {/* Right: Inline Subject Selector + Status + Actions */}
            <div
              className="flex items-center justify-between sm:justify-end gap-3 shrink-0"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Inline Subject Assignment Dropdown */}
              <select
                aria-label={`Chọn môn học cho ${doc.title}`}
                disabled={isAssigning}
                value={doc.subject_id || ""}
                onChange={(e) => void handleSubjectChange(e, doc.document_id)}
                className="h-7 max-w-[165px] rounded-lg border border-slate-200/80 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-950 px-2 text-[11px] font-medium text-slate-700 dark:text-slate-300 hover:border-slate-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] cursor-pointer truncate"
              >
                <option value="">Chưa phân loại</option>
                {subjects.map((subj) => (
                  <option key={subj.id} value={subj.id}>
                    {subj.name}
                  </option>
                ))}
              </select>

              <StatusIndicator
                status={doc.status}
                parsedPages={doc.parsed_pages}
                totalPages={doc.total_pages}
              />

              <div className="flex items-center gap-1">
                {doc.status === "failed" && (
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={(e) => void handleRetry(e, doc.document_id)}
                    aria-label={`Thử lại ${doc.title}`}
                    title="Thử xử lý lại"
                    className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-[#0A77FF] hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
                  >
                    <RotateCw
                      className={`h-4 w-4 stroke-[1.75] ${
                        isBusy ? "animate-spin" : ""
                      }`}
                    />
                  </button>
                )}

                <button
                  type="button"
                  disabled={isBusy}
                  onClick={(e) => void handleDelete(e, doc.document_id)}
                  aria-label={`Xóa ${doc.title}`}
                  title="Xóa tài liệu"
                  className="h-8 w-8 rounded-lg flex items-center justify-center text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer"
                >
                  {isBusy ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4 stroke-[1.75]" />
                  )}
                </button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
