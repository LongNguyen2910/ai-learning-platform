import { getAuthHeaders } from "@/lib/api/documents"

export type ChatMode = "socratic" | "normal" | "refusal"

export interface ChatCitation {
  chunk_id: string
  page_number: number
  score: number
  citation_tag: string
  content?: string
  has_formula?: boolean
  has_image?: boolean
}

export interface RetrievedChunkDTO {
  chunk_id: string
  page_number: number
  chunk_index: number
  score: number
  content: string
  has_formula: boolean
  has_image: boolean
  citation_tag: string
}

export interface RAGChunkSearchRequest {
  query: string
  page_number?: number | null
  similarity_top_k?: number
  score_threshold?: number
}

export interface RAGChunkSearchResponse {
  document_id: string
  query: string
  total_retrieved: number
  chunks: RetrievedChunkDTO[]
}

export interface ChatSession {
  id: string
  document_id: string
  title: string
  created_at?: string | null
}

export interface ChatMessage {
  id: string
  session_id: string
  sender: "user" | "assistant"
  content: string
  socratic_tier: number
  citations: ChatCitation[]
  created_at?: string | null
  /** Client-only metadata for active session indicators */
  mode?: ChatMode
  solved?: boolean
  isStreaming?: boolean
  isError?: boolean
  retrievedChunks?: ChatCitation[]
}

export interface ChatRequestPayload {
  content: string
  socratic_enabled?: boolean
  new_question?: boolean
  requested_tier?: number | null
  page_number?: number | null
}

export interface SSEMetaData {
  session_id: string
  mode: ChatMode
  socratic_tier: number
  previous_tier: number
  is_new_question?: boolean
  homework_detected: boolean
  jailbreak_detected: boolean
}

export interface SSECitationsData {
  chunks: ChatCitation[]
}

export interface SSETokenData {
  text: string
}

export interface SSEDoneData {
  message_id: string
  socratic_tier: number
  solved: boolean
  citations?: ChatCitation[]
}

export interface SSEErrorData {
  message: string
}

export interface StreamChatCallbacks {
  onMeta?: (data: SSEMetaData) => void
  onCitations?: (data: SSECitationsData) => void
  onToken?: (data: SSETokenData) => void
  onDone?: (data: SSEDoneData) => void
  onError?: (data: SSEErrorData) => void
  signal?: AbortSignal
}

const getApiBaseUrl = () =>
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"

function handleUnauthorized(response: Response): void {
  if (response.status === 401 && typeof window !== "undefined") {
    localStorage.removeItem("auth_token")
    if (!window.location.pathname.startsWith("/login")) {
      window.location.href = "/login"
    }
  }
}

export async function fetchChatSessions(
  documentId: string,
  limit = 20
): Promise<ChatSession[]> {
  const url = new URL(`${getApiBaseUrl()}/chat/sessions`)
  url.searchParams.set("document_id", documentId)
  url.searchParams.set("limit", String(limit))

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    handleUnauthorized(response)
    throw new Error(`Không thể tải danh sách hội thoại (${response.status})`)
  }

  return response.json()
}

export async function createChatSession(
  documentId: string,
  title = "Hội thoại mới"
): Promise<ChatSession> {
  const response = await fetch(`${getApiBaseUrl()}/chat/sessions`, {
    method: "POST",
    headers: getAuthHeaders({
      "Content-Type": "application/json",
      Accept: "application/json",
    }),
    body: JSON.stringify({
      document_id: documentId,
      title,
    }),
  })

  if (!response.ok) {
    handleUnauthorized(response)
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Không thể khởi tạo phiên chat (${response.status})`
    )
  }

  return response.json()
}

export async function deleteChatSession(sessionId: string): Promise<void> {
  const response = await fetch(
    `${getApiBaseUrl()}/chat/sessions/${encodeURIComponent(sessionId)}`,
    {
      method: "DELETE",
      headers: getAuthHeaders(),
    }
  )

  if (!response.ok) {
    handleUnauthorized(response)
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Không thể xóa phiên hội thoại (${response.status})`
    )
  }
}

export async function fetchChatMessages(
  sessionId: string,
  limit = 50
): Promise<ChatMessage[]> {
  const url = new URL(
    `${getApiBaseUrl()}/chat/sessions/${encodeURIComponent(sessionId)}/messages`
  )
  url.searchParams.set("limit", String(limit))

  const response = await fetch(url.toString(), {
    method: "GET",
    headers: getAuthHeaders({ Accept: "application/json" }),
    cache: "no-store",
  })

  if (!response.ok) {
    handleUnauthorized(response)
    throw new Error(`Không thể tải lịch sử tin nhắn (${response.status})`)
  }

  return response.json()
}

export async function retrieveDocumentChunks(
  documentId: string,
  payload: RAGChunkSearchRequest
): Promise<RAGChunkSearchResponse> {
  const response = await fetch(
    `${getApiBaseUrl()}/chat/documents/${encodeURIComponent(documentId)}/retrieval`,
    {
      method: "POST",
      headers: getAuthHeaders({
        "Content-Type": "application/json",
        Accept: "application/json",
      }),
      body: JSON.stringify({
        query: payload.query,
        page_number: payload.page_number ?? null,
        similarity_top_k: payload.similarity_top_k ?? 5,
        score_threshold: payload.score_threshold ?? 0.5,
      }),
    }
  )

  if (!response.ok) {
    handleUnauthorized(response)
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Tra cứu trích dẫn thất bại (${response.status})`
    )
  }

  return response.json()
}

function dispatchSSEBlock(block: string, callbacks: StreamChatCallbacks): void {
  const lines = block.split(/\r?\n/)
  let eventName = "message"
  const dataLines: string[] = []

  for (const line of lines) {
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim()
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trim())
    }
  }

  if (dataLines.length === 0) return
  const rawJson = dataLines.join("\n")

  try {
    const parsed = JSON.parse(rawJson)
    switch (eventName) {
      case "meta":
        callbacks.onMeta?.(parsed as SSEMetaData)
        break
      case "citations":
        callbacks.onCitations?.(parsed as SSECitationsData)
        break
      case "token":
        callbacks.onToken?.(parsed as SSETokenData)
        break
      case "done":
        callbacks.onDone?.(parsed as SSEDoneData)
        break
      case "error":
        callbacks.onError?.(parsed as SSEErrorData)
        break
      default:
        break
    }
  } catch {
    // Ignore malformed SSE frame
  }
}

export async function streamChatMessage(
  sessionId: string,
  payload: ChatRequestPayload,
  callbacks: StreamChatCallbacks
): Promise<void> {
  const response = await fetch(
    `${getApiBaseUrl()}/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`,
    {
      method: "POST",
      headers: getAuthHeaders({
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      }),
      body: JSON.stringify({
        content: payload.content,
        socratic_enabled: Boolean(payload.socratic_enabled),
        new_question: Boolean(payload.new_question),
        requested_tier: payload.requested_tier ?? null,
        page_number: payload.page_number ?? null,
      }),
      signal: callbacks.signal,
    }
  )

  if (!response.ok) {
    handleUnauthorized(response)
    const err = await response.json().catch(() => null)
    throw new Error(
      err?.detail || `Không thể gửi tin nhắn (${response.status})`
    )
  }

  if (!response.body) {
    throw new Error("Trình duyệt không hỗ trợ luồng dữ liệu (ReadableStream).")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder("utf-8")
  let buffer = ""

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ""

      for (const block of blocks) {
        if (block.trim()) {
          dispatchSSEBlock(block, callbacks)
        }
      }
    }

    buffer += decoder.decode()
    if (buffer.trim()) {
      dispatchSSEBlock(buffer, callbacks)
    }
  } finally {
    reader.releaseLock()
  }
}
