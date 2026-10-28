"use client"

import * as React from "react"
import {
  UploadCloud,
  FileUp,
  Loader2,
  AlertCircle,
  CheckCircle2,
} from "lucide-react"
import {
  uploadDocument,
  type DocumentUploadResponse,
} from "@/lib/api/documents"

interface DocumentUploadZoneProps {
  onUploaded: (res: DocumentUploadResponse, file: File) => void
}

export function DocumentUploadZone({ onUploaded }: DocumentUploadZoneProps) {
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const [isDragging, setIsDragging] = React.useState(false)
  const [isUploading, setIsUploading] = React.useState(false)
  const [uploadingFileName, setUploadingFileName] = React.useState<
    string | null
  >(null)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  const [successMessage, setSuccessMessage] = React.useState<string | null>(
    null
  )

  const processFile = async (file: File) => {
    setErrorMessage(null)
    setSuccessMessage(null)

    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setErrorMessage("Chỉ hỗ trợ định dạng tệp PDF (.pdf).")
      return
    }

    const sizeMb = file.size / (1024 * 1024)
    if (sizeMb > 50) {
      setErrorMessage("Dung lượng tệp vượt quá giới hạn tối đa 50 MB.")
      return
    }

    setIsUploading(true)
    setUploadingFileName(file.name)

    try {
      const response = await uploadDocument(file)
      setSuccessMessage(
        `Đã tải lên "${response.title}" (${response.total_pages} trang)`
      )
      onUploaded(response, file)
      setTimeout(() => {
        setSuccessMessage(null)
      }, 4000)
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Không thể tải tài liệu lên. Vui lòng kiểm tra kết nối API."
      )
    } finally {
      setIsUploading(false)
      setUploadingFileName(null)
      if (fileInputRef.current) {
        fileInputRef.current.value = ""
      }
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      void processFile(file)
    }
  }

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (!isUploading) {
      setIsDragging(true)
    }
  }

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    if (isUploading) return

    const file = e.dataTransfer.files?.[0]
    if (file) {
      void processFile(file)
    }
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !isUploading) {
            e.preventDefault()
            fileInputRef.current?.click()
          }
        }}
        aria-label="Upload PDF document"
        className={`group relative rounded-2xl border border-dashed p-6 sm:p-7 transition-all duration-150 cursor-pointer select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] ${
          isDragging
            ? "border-[#0A77FF] bg-[#0A77FF]/[0.04]"
            : "border-slate-300/90 dark:border-slate-800 bg-white dark:bg-slate-900/60 hover:border-[#0A77FF]/60 hover:bg-slate-50/70 dark:hover:bg-slate-900"
        } ${isUploading ? "pointer-events-none opacity-80" : ""}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          onChange={handleFileChange}
          className="hidden"
          disabled={isUploading}
        />

        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex flex-col sm:flex-row items-center gap-4 text-center sm:text-left">
            <div className="h-12 w-12 rounded-2xl bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 text-[#0A77FF] dark:text-sky-400 flex items-center justify-center shrink-0 transition-transform duration-150 group-hover:scale-105">
              {isUploading ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <UploadCloud className="h-5 w-5 stroke-[1.8]" />
              )}
            </div>

            <div className="space-y-1">
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                {isUploading
                  ? `Đang tải lên ${uploadingFileName}...`
                  : "Tải tài liệu học tập lên (PDF)"}
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Kéo thả giáo trình, slide bài giảng hoặc bài tập vào đây, hoặc
                bấm để chọn tệp (tối đa 50 MB)
              </p>
            </div>
          </div>

          <button
            type="button"
            disabled={isUploading}
            onClick={(e) => {
              e.stopPropagation()
              fileInputRef.current?.click()
            }}
            className="h-10 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0066E6] active:scale-[0.98] text-white text-xs font-semibold shadow-[0_4px_14px_-2px_rgba(10,119,255,0.4)] transition-all duration-150 inline-flex items-center gap-2 shrink-0 cursor-pointer disabled:opacity-50"
          >
            {isUploading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Đang tải...</span>
              </>
            ) : (
              <>
                <FileUp className="h-3.5 w-3.5 stroke-[2]" />
                <span>Chọn PDF</span>
              </>
            )}
          </button>
        </div>
      </div>

      {errorMessage && (
        <div
          role="alert"
          className="flex items-center gap-2.5 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200/80 dark:border-rose-900/60 px-4 py-2.5 text-xs font-medium text-rose-600 dark:text-rose-400"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {successMessage && (
        <div
          role="status"
          className="flex items-center gap-2.5 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200/80 dark:border-emerald-900/60 px-4 py-2.5 text-xs font-medium text-emerald-700 dark:text-emerald-400"
        >
          <CheckCircle2 className="h-4 w-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}
    </div>
  )
}
