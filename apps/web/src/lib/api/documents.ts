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
  user_id?: string | null
  subject_id?: string | null
  title: string
  status: DocumentStatus
  file_size_kb?: number
  total_pages: number
  parsed_pages: number
  error_message?: string | null
  created_at: string
  updated_at: string
  /** In-memory blob URL created during upload or authenticated file fetch for instant preview */
  localBlobUrl?: string
}

export interface DocumentUploadResponse {
  document_id: string
  user_id?: string | null
  subject_id?: string | null
  title: string
  status: DocumentStatus
  total_pages: number
  message: string
}

export interface DocumentContentResponse {
  document_id: string
  user_id?: string | null
  title: string
  status: DocumentStatus
  total_pages: number
  full_content: string | null
  pages: ParsedPageMetadata[]
}

const getApiBaseUrl = () =>
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem("auth_token")
}

export function getAuthHeaders(
  extraHeaders: Record<string, string> = {}
): Record<string, string> {
  const headers: Record<string, string> = { ...extraHeaders }
  const token = getAuthToken()
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  return headers
}

function handleUnauthorized(response: Response): void {
  if (response.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("auth_token")
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login"
    }
  }
}

export function getDocumentFileUrl(documentId: string): string {
  return `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}/file`
}

export async function fetchDocumentFileBlobUrl(
  documentId: string
): Promise<string> {
  const response = await fetch(getDocumentFileUrl(documentId), {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/pdf" }),
  })

  if (!response.ok) {
    handleUnauthorized(response)
    throw new Error(`Failed to load PDF file (${response.status})`)
  }

  const blob = await response.blob()
  const pdfBlob =
    blob.type === "application/pdf"
      ? blob
      : new Blob([blob], { type: "application/pdf" })
  return URL.createObjectURL(pdfBlob)
}

export async function fetchDocuments(): Promise<DocumentItem[]> {
  const response = await fetch(`${getApiBaseUrl()}/documents`, {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    handleUnauthorized(response)
    throw new Error(`Failed to load documents (${response.status})`)
  }

  return response.json()
}

export async function uploadDocument(
  file: File,
  title?: string,
  subjectId?: string | null
): Promise<DocumentUploadResponse> {
  const formData = new FormData()
  formData.append("file", file)
  if (title && title.trim()) {
    formData.append("title", title.trim())
  }
  if (subjectId && subjectId.trim()) {
    formData.append("subject_id", subjectId.trim())
  }

  const response = await fetch(`${getApiBaseUrl()}/documents/upload`, {
    method: "POST",
    headers: getAuthHeaders(),
    body: formData,
  })

  if (!response.ok) {
    handleUnauthorized(response)
    const errorData = await response.json().catch(() => null)
    const detail =
      errorData?.detail ||
      errorData?.message ||
      `Upload failed with status ${response.status}`
    throw new Error(detail)
  }

  return response.json()
}

export async function updateDocumentSubject(
  documentId: string,
  subjectId: string | null
): Promise<DocumentItem> {
  const response = await fetch(
    `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}/subject`,
    {
      method: "PATCH",
      headers: getAuthHeaders({
        Accept: "application/json",
        "Content-Type": "application/json",
      }),
      body: JSON.stringify({ subject_id: subjectId || null }),
    }
  )

  if (!response.ok) {
    handleUnauthorized(response)
    const errorData = await response.json().catch(() => null)
    throw new Error(
      errorData?.detail || `Could not update subject (${response.status})`
    )
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
      headers: getAuthHeaders({ Accept: "application/json" }),
      cache: "no-store",
    }
  )

  if (!response.ok) {
    handleUnauthorized(response)
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
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    handleUnauthorized(response)
    throw new Error(`Could not load document content (${response.status})`)
  }

  return response.json()
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(
    `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}`,
    {
      method: "DELETE",
      headers: getAuthHeaders(),
    }
  )

  if (!response.ok) {
    handleUnauthorized(response)
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
      headers: getAuthHeaders(),
    }
  )

  if (!response.ok) {
    handleUnauthorized(response)
    const errorData = await response.json().catch(() => null)
    throw new Error(
      errorData?.detail || `Could not retry document (${response.status})`
    )
  }
}
