export type DocumentStatus =
  | "uploading"
  | "parsing"
  | "parsed"
  | "indexing"
  | "ready"
  | "failed"

export interface ParsedPageMetadata {
  page_number: number
  has_formula: boolean
  has_image: boolean
  char_count: number
  file_path: string
}

export interface DocumentItem {
  document_id: string
  title: string
  status: DocumentStatus
  file_size_kb?: number
  total_pages: number
  parsed_pages: number
  error_message?: string | null
  created_at: string
  updated_at: string
  /** Optional in-memory blob URL created during session upload for instant preview */
  localBlobUrl?: string
}

export interface DocumentUploadResponse {
  document_id: string
  title: string
  status: DocumentStatus
  total_pages: number
  message: string
}

export interface DocumentContentResponse {
  document_id: string
  title: string
  status: DocumentStatus
  total_pages: number
  full_content: string | null
  pages: ParsedPageMetadata[]
}

const getApiBaseUrl = () =>
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export function getDocumentFileUrl(documentId: string): string {
  return `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}/file`
}

export async function fetchDocuments(): Promise<DocumentItem[]> {
  const response = await fetch(`${getApiBaseUrl()}/documents`, {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error(`Failed to load documents (${response.status})`)
  }

  return response.json()
}

export async function uploadDocument(
  file: File,
  title?: string
): Promise<DocumentUploadResponse> {
  const formData = new FormData()
  formData.append("file", file)
  if (title && title.trim()) {
    formData.append("title", title.trim())
  }

  const response = await fetch(`${getApiBaseUrl()}/documents/upload`, {
    method: "POST",
    body: formData,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => null)
    const detail =
      errorData?.detail ||
      errorData?.message ||
      `Upload failed with status ${response.status}`
    throw new Error(detail)
  }

  return response.json()
}

export async function fetchDocumentStatus(
  documentId: string
): Promise<DocumentItem> {
  const response = await fetch(
    `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}/status`,
    {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    }
  )

  if (!response.ok) {
    throw new Error(`Status check failed (${response.status})`)
  }

  return response.json()
}

export async function fetchDocumentContent(
  documentId: string,
  page?: number
): Promise<DocumentContentResponse> {
  const url = new URL(
    `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}/content`
  )
  if (page !== undefined) {
    url.searchParams.set("page", String(page))
  }

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: { Accept: "application/json" },
    cache: "no-store",
  })

  if (!response.ok) {
    throw new Error(`Could not load document content (${response.status})`)
  }

  return response.json()
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(
    `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}`,
    {
      method: "DELETE",
    }
  )

  if (!response.ok) {
    const errorData = await response.json().catch(() => null)
    throw new Error(
      errorData?.detail || `Could not delete document (${response.status})`
    )
  }
}

export async function retryDocument(
  documentId: string,
  force = false
): Promise<void> {
  const response = await fetch(
    `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}/retry?force=${force}`,
    {
      method: "POST",
    }
  )

  if (!response.ok) {
    const errorData = await response.json().catch(() => null)
    throw new Error(
      errorData?.detail || `Could not retry document (${response.status})`
    )
  }
}
