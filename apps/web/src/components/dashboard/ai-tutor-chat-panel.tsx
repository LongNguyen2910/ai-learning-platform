"use client"

import * as React from "react"
import {
  Sparkles,
  Send,
  X,
  BookOpen,
  HelpCircle,
  Lightbulb,
  Plus,
  Search,
  MessageSquare,
  GraduationCap,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  Loader2,
  Square,
  RotateCcw,
  FileSearch,
  Filter,
  History,
  Trash2,
} from "lucide-react"
import type { DocumentItem } from "@/lib/api/documents"
import {
  fetchChatSessions,
  createChatSession,
  deleteChatSession,
  fetchChatMessages,
  streamChatMessage,
  retrieveDocumentChunks,
  type ChatSession,
  type ChatMessage,
  type ChatCitation,
  type RetrievedChunkDTO,
} from "@/lib/api/chat"
import { ChatMarkdownRenderer } from "@/components/dashboard/chat-markdown-renderer"

interface AiTutorChatPanelProps {
  document: DocumentItem
  currentPage: number
  onSelectCitationPage: (pageNumber: number, citation?: ChatCitation) => void
  onClose: () => void
}

type PanelMode = "chat" | "search"

const SUGGESTED_PROMPTS = [
  {
    icon: BookOpen,
    label: "Tóm tắt nội dung cốt lõi & dẫn nguồn trang",
    prompt:
      "Hãy tóm tắt các định nghĩa, định lý cốt lõi trong tài liệu này và trích dẫn số trang tương ứng.",
    socratic: false,
  },
  {
    icon: Lightbulb,
    label: "Giải thích công thức toán học theo từng bước",
    prompt:
      "Hãy giải thích ý nghĩa và cách áp dụng các công thức toán học quan trọng trong tài liệu.",
    socratic: false,
  },
  {
    icon: GraduationCap,
    label: "Luyện giải bài tập theo Socratic 3 tầng",
    prompt:
      "Hướng dẫn mình giải bài tập áp dụng kiến thức ở trang hiện tại theo phương pháp gợi mở từng bước.",
    socratic: true,
  },
  {
    icon: HelpCircle,
    label: "Đặt câu hỏi kiểm tra mức độ hiểu bài",
    prompt:
      "Hãy đặt cho mình một câu hỏi Socratic để kiểm tra xem mình đã hiểu đúng nội dung trang này chưa.",
    socratic: true,
  },
]

function getTierBadgeInfo(tier: number, mode?: string, solved?: boolean) {
  if (solved) {
    return {
      label: "Hoàn thành bài tập",
      className:
        "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/80 dark:text-emerald-300 ring-1 ring-emerald-500/20",
    }
  }
  if (mode === "refusal") {
    return {
      label: "Bảo vệ Sư phạm",
      className:
        "bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 ring-1 ring-amber-500/25",
    }
  }
  if (tier === 1) {
    return {
      label: "Socratic Tầng 1 • Gợi mở Lý thuyết",
      className:
        "bg-indigo-100 text-indigo-700 dark:bg-indigo-950/80 dark:text-indigo-300 ring-1 ring-indigo-500/20",
    }
  }
  if (tier === 2) {
    return {
      label: "Socratic Tầng 2 • Ví dụ Tương tự",
      className:
        "bg-violet-100 text-violet-700 dark:bg-violet-950/80 dark:text-violet-300 ring-1 ring-violet-500/20",
    }
  }
  if (tier === 3) {
    return {
      label: "Socratic Tầng 3 • Dẫn dắt Từng bước",
      className:
        "bg-sky-100 text-sky-700 dark:bg-sky-950/80 dark:text-sky-300 ring-1 ring-sky-500/20",
    }
  }
  return {
    label: "Hỏi đáp Lý thuyết",
    className:
      "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  }
}

export function AiTutorChatPanel({
  document,
  currentPage,
  onSelectCitationPage,
  onClose,
}: AiTutorChatPanelProps) {
  const [panelMode, setPanelMode] = React.useState<PanelMode>("chat")

  // Sessions & messages state
  const [sessions, setSessions] = React.useState<ChatSession[]>([])
  const [activeSessionId, setActiveSessionId] = React.useState<string | null>(
    null
  )
  const [deletingSessionId, setDeletingSessionId] = React.useState<
    string | null
  >(null)
  const [isSessionMenuOpen, setIsSessionMenuOpen] = React.useState(false)
  const [messages, setMessages] = React.useState<ChatMessage[]>([])
  const [isLoadingHistory, setIsLoadingHistory] = React.useState(false)
  const [isStreaming, setIsStreaming] = React.useState(false)
  const [chatError, setChatError] = React.useState<string | null>(null)

  // Socratic & composer state
  const [socraticEnabled, setSocraticEnabled] = React.useState(false)
  const [currentTier, setCurrentTier] = React.useState<number>(0)
  const [lastSolved, setLastSolved] = React.useState(false)
  const [isNewQuestionFlag, setIsNewQuestionFlag] = React.useState(false)
  const [limitToCurrentPage, setLimitToCurrentPage] = React.useState(false)
  const [inputValue, setInputValue] = React.useState("")
  const [lastBlockedPrompt, setLastBlockedPrompt] = React.useState<
    string | null
  >(null)
  const [expandedSourceMsgIds, setExpandedSourceMsgIds] = React.useState<
    Record<string, boolean>
  >({})

  // Direct RAG Citation Search state
  const [searchQuery, setSearchQuery] = React.useState("")
  const [searchPageOnly, setSearchPageOnly] = React.useState(false)
  const [searchResults, setSearchResults] = React.useState<
    RetrievedChunkDTO[] | null
  >(null)
  const [isSearchingChunks, setIsSearchingChunks] = React.useState(false)
  const [searchError, setSearchError] = React.useState<string | null>(null)

  const messagesEndRef = React.useRef<HTMLDivElement>(null)
  const abortControllerRef = React.useRef<AbortController | null>(null)

  // Auto-scroll chat to bottom when messages update
  const scrollToBottom = React.useCallback((smooth = true) => {
    messagesEndRef.current?.scrollIntoView({
      behavior: smooth ? "smooth" : "auto",
      block: "end",
    })
  }, [])

  React.useEffect(() => {
    if (panelMode === "chat") {
      scrollToBottom(true)
    }
  }, [messages, panelMode, scrollToBottom])

  // Load sessions for current document when document_id changes
  React.useEffect(() => {
    let cancelled = false
    abortControllerRef.current?.abort()
    setIsStreaming(false)
    setChatError(null)
    setMessages([])
    setActiveSessionId(null)
    setCurrentTier(0)
    setLastSolved(false)
    setLastBlockedPrompt(null)
    setSearchResults(null)
    setSearchError(null)
    setSearchQuery("")

    const loadDocSessions = async () => {
      setIsLoadingHistory(true)
      try {
        const list = await fetchChatSessions(document.document_id)
        if (cancelled) return
        setSessions(list)
        if (list.length > 0) {
          const latest = list[0]
          setActiveSessionId(latest.id)
          const history = await fetchChatMessages(latest.id, 60)
          if (cancelled) return
          setMessages(history)
          // Restore last assistant socratic_tier from history
          for (let i = history.length - 1; i >= 0; i--) {
            if (history[i].sender === "assistant") {
              const t = history[i].socratic_tier || 0
              setCurrentTier(t)
              if (t > 0) setSocraticEnabled(true)
              break
            }
          }
        }
      } catch {
        // Session will be created lazily on first message
      } finally {
        if (!cancelled) {
          setIsLoadingHistory(false)
        }
      }
    }

    void loadDocSessions()
    return () => {
      cancelled = true
      abortControllerRef.current?.abort()
    }
  }, [document.document_id])

  const handleSelectSession = async (session: ChatSession) => {
    setIsSessionMenuOpen(false)
    if (session.id === activeSessionId) return
    abortControllerRef.current?.abort()
    setIsStreaming(false)
    setActiveSessionId(session.id)
    setChatError(null)
    setLastSolved(false)
    setLastBlockedPrompt(null)
    setIsLoadingHistory(true)
    try {
      const history = await fetchChatMessages(session.id, 60)
      setMessages(history)
      let restoredTier = 0
      for (let i = history.length - 1; i >= 0; i--) {
        if (history[i].sender === "assistant") {
          restoredTier = history[i].socratic_tier || 0
          break
        }
      }
      setCurrentTier(restoredTier)
      if (restoredTier > 0) {
        setSocraticEnabled(true)
      }
    } catch (err) {
      setChatError(
        err instanceof Error ? err.message : "Không thể tải lịch sử hội thoại."
      )
    } finally {
      setIsLoadingHistory(false)
    }
  }

  const handleCreateNewSession = async () => {
    setIsSessionMenuOpen(false)
    abortControllerRef.current?.abort()
    setIsStreaming(false)
    setChatError(null)
    setLastSolved(false)
    setCurrentTier(0)
    setLastBlockedPrompt(null)
    try {
      const created = await createChatSession(
        document.document_id,
        `Hội thoại #${sessions.length + 1}`
      )
      setSessions((prev) => [created, ...prev])
      setActiveSessionId(created.id)
      setMessages([])
    } catch (err) {
      setChatError(
        err instanceof Error ? err.message : "Không thể tạo hội thoại mới."
      )
    }
  }

  const handleDeleteSession = async (
    targetSessionId: string,
    e?: React.MouseEvent
  ) => {
    e?.stopPropagation()
    if (deletingSessionId) return
    setDeletingSessionId(targetSessionId)
    setChatError(null)

    try {
      await deleteChatSession(targetSessionId)
      const remaining = sessions.filter((s) => s.id !== targetSessionId)
      setSessions(remaining)

      if (activeSessionId === targetSessionId) {
        abortControllerRef.current?.abort()
        setIsStreaming(false)
        setLastSolved(false)
        setLastBlockedPrompt(null)

        if (remaining.length > 0) {
          const nextSession = remaining[0]
          setActiveSessionId(nextSession.id)
          setIsLoadingHistory(true)
          try {
            const history = await fetchChatMessages(nextSession.id, 60)
            setMessages(history)
            let restoredTier = 0
            for (let i = history.length - 1; i >= 0; i--) {
              if (history[i].sender === "assistant") {
                restoredTier = history[i].socratic_tier || 0
                break
              }
            }
            setCurrentTier(restoredTier)
            if (restoredTier > 0) {
              setSocraticEnabled(true)
            }
          } finally {
            setIsLoadingHistory(false)
          }
        } else {
          setActiveSessionId(null)
          setMessages([])
          setCurrentTier(0)
          setIsSessionMenuOpen(false)
        }
      }
    } catch (err) {
      setChatError(
        err instanceof Error ? err.message : "Không thể xóa phiên hội thoại."
      )
    } finally {
      setDeletingSessionId(null)
    }
  }

  const sendMessage = React.useCallback(
    async (
      rawText: string,
      options?: {
        forceSocratic?: boolean
        newQuestion?: boolean
        requestedTier?: number | null
      }
    ) => {
      const text = rawText.trim()
      if (!text || isStreaming) return

      const effectiveSocratic =
        options?.forceSocratic !== undefined
          ? options.forceSocratic
          : socraticEnabled
      if (options?.forceSocratic !== undefined) {
        setSocraticEnabled(options.forceSocratic)
      }

      const effectiveNewQuestion =
        options?.newQuestion !== undefined
          ? options.newQuestion
          : isNewQuestionFlag

      setInputValue("")
      setIsNewQuestionFlag(false)
      setChatError(null)
      setLastSolved(false)
      setLastBlockedPrompt(null)
      setIsStreaming(true)

      let sessionId = activeSessionId
      try {
        if (!sessionId) {
          const shortTitle =
            text.length > 42 ? `${text.slice(0, 42).trim()}...` : text
          const created = await createChatSession(
            document.document_id,
            shortTitle
          )
          sessionId = created.id
          setActiveSessionId(created.id)
          setSessions((prev) => [created, ...prev])
        }
      } catch (err) {
        setIsStreaming(false)
        setChatError(
          err instanceof Error
            ? err.message
            : "Không thể khởi tạo phiên trò chuyện với tài liệu này."
        )
        return
      }

      const tempUserMsgId = `user-${Date.now()}`
      const tempAssistantMsgId = `assistant-${Date.now() + 1}`

      const userMsg: ChatMessage = {
        id: tempUserMsgId,
        session_id: sessionId,
        sender: "user",
        content: text,
        socratic_tier: 0,
        citations: [],
        created_at: new Date().toISOString(),
      }

      const placeholderAssistant: ChatMessage = {
        id: tempAssistantMsgId,
        session_id: sessionId,
        sender: "assistant",
        content: "",
        socratic_tier: effectiveSocratic ? Math.max(currentTier, 1) : 0,
        citations: [],
        retrievedChunks: [],
        mode: effectiveSocratic ? "socratic" : "normal",
        isStreaming: true,
        created_at: new Date().toISOString(),
      }

      setMessages((prev) => [...prev, userMsg, placeholderAssistant])

      const controller = new AbortController()
      abortControllerRef.current = controller

      try {
        await streamChatMessage(
          sessionId,
          {
            content: text,
            socratic_enabled: effectiveSocratic,
            new_question: effectiveNewQuestion,
            requested_tier: options?.requestedTier ?? null,
            page_number: limitToCurrentPage ? currentPage : null,
          },
          {
            signal: controller.signal,
            onMeta: (meta) => {
              if (meta.mode === "refusal") {
                setLastBlockedPrompt(text)
              }
              setCurrentTier(meta.socratic_tier)
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === tempAssistantMsgId
                    ? {
                        ...m,
                        mode: meta.mode,
                        socratic_tier: meta.socratic_tier,
                      }
                    : m
                )
              )
            },
            onCitations: (citData) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === tempAssistantMsgId
                    ? {
                        ...m,
                        retrievedChunks: citData.chunks,
                        citations: citData.chunks,
                      }
                    : m
                )
              )
            },
            onToken: (tokenData) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === tempAssistantMsgId
                    ? {
                        ...m,
                        content: m.content + tokenData.text,
                      }
                    : m
                )
              )
            },
            onDone: (doneData) => {
              setCurrentTier(doneData.socratic_tier)
              if (doneData.solved) {
                setLastSolved(true)
              }
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === tempAssistantMsgId
                    ? {
                        ...m,
                        id: doneData.message_id || m.id,
                        socratic_tier: doneData.socratic_tier,
                        solved: doneData.solved,
                        citations:
                          doneData.citations && doneData.citations.length > 0
                            ? doneData.citations
                            : m.citations,
                        isStreaming: false,
                      }
                    : m
                )
              )
            },
            onError: (errData) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === tempAssistantMsgId
                    ? {
                        ...m,
                        content:
                          m.content ||
                          errData.message ||
                          "Gia sư AI tạm thời gián đoạn kết nối.",
                        isStreaming: false,
                        isError: true,
                      }
                    : m
                )
              )
            },
          }
        )
      } catch (err) {
        if ((err as Error)?.name === "AbortError") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === tempAssistantMsgId ? { ...m, isStreaming: false } : m
            )
          )
        } else {
          const message =
            err instanceof Error
              ? err.message
              : "Kết nối tới AI Tutor bị gián đoạn."
          setChatError(message)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === tempAssistantMsgId
                ? {
                    ...m,
                    content: m.content || message,
                    isStreaming: false,
                    isError: true,
                  }
                : m
            )
          )
        }
      } finally {
        setIsStreaming(false)
        abortControllerRef.current = null
      }
    },
    [
      activeSessionId,
      currentPage,
      currentTier,
      document.document_id,
      isNewQuestionFlag,
      isStreaming,
      limitToCurrentPage,
      socraticEnabled,
    ]
  )

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    void sendMessage(inputValue)
  }

  const handleStopStreaming = () => {
    abortControllerRef.current?.abort()
    setIsStreaming(false)
  }

  const handleSearchChunks = async (e: React.FormEvent) => {
    e.preventDefault()
    const q = searchQuery.trim()
    if (q.length < 2) {
      setSearchError("Vui lòng nhập ít nhất 2 ký tự để tra cứu ngữ nghĩa.")
      return
    }
    setIsSearchingChunks(true)
    setSearchError(null)
    try {
      const res = await retrieveDocumentChunks(document.document_id, {
        query: q,
        page_number: searchPageOnly ? currentPage : null,
        similarity_top_k: 6,
        score_threshold: 0.45,
      })
      setSearchResults(res.chunks)
    } catch (err) {
      setSearchError(
        err instanceof Error
          ? err.message
          : "Không thể tra cứu trích dẫn từ tài liệu."
      )
    } finally {
      setIsSearchingChunks(false)
    }
  }

  const toggleExpandSources = (msgId: string) => {
    setExpandedSourceMsgIds((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }))
  }

  const isDocNotReady = document.status !== "ready"

  return (
    <section
      aria-label="AI Tutor & Document Citations Panel"
      className="h-full w-full flex flex-col bg-white dark:bg-slate-950 border-l border-slate-200/80 dark:border-slate-800/80"
    >
      {/* 1. Top Header: Mode Tabs + Session Selector + Close */}
      <div className="h-12 px-3.5 border-b border-slate-200/80 dark:border-slate-800/80 flex items-center justify-between gap-2 shrink-0 bg-slate-50/70 dark:bg-slate-900/50">
        {/* Left: Mode Switcher (AI Chat vs RAG Citation Search) */}
        <div className="flex items-center gap-1.5 min-w-0 flex-1 overflow-hidden">
          <div className="inline-flex items-center rounded-xl bg-slate-200/70 dark:bg-slate-800/90 p-0.5 max-w-full min-w-0 overflow-hidden">
            <button
              type="button"
              onClick={() => setPanelMode("chat")}
              title="Gia sư AI"
              className={`h-7 px-2.5 rounded-[10px] text-xs font-semibold inline-flex items-center gap-1.5 min-w-0 overflow-hidden transition-all cursor-pointer ${
                panelMode === "chat"
                  ? "bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-2xs"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              <MessageSquare className="h-3.5 w-3.5 stroke-[2] shrink-0" />
              <span className="truncate">Gia sư AI</span>
            </button>

            <button
              type="button"
              onClick={() => setPanelMode("search")}
              title="Tra cứu trích dẫn"
              className={`h-7 px-2.5 rounded-[10px] text-xs font-semibold inline-flex items-center gap-1.5 min-w-0 overflow-hidden transition-all cursor-pointer ${
                panelMode === "search"
                  ? "bg-white dark:bg-slate-900 text-indigo-600 dark:text-indigo-400 shadow-2xs"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              <FileSearch className="h-3.5 w-3.5 stroke-[2] shrink-0" />
              <span className="truncate">Tra cứu trích dẫn</span>
            </button>
          </div>
        </div>

        {/* Right: Session History + New Chat + Close */}
        <div className="flex items-center gap-1 shrink-0 relative">
          {panelMode === "chat" && (
            <>
              {sessions.length > 0 && (
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setIsSessionMenuOpen((prev) => !prev)}
                    title="Lịch sử phiên hội thoại"
                    className="h-7 px-2 rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-[11px] font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-1 transition-colors cursor-pointer"
                  >
                    <History className="h-3 w-3 stroke-[2]" />
                    <span className="hidden sm:inline max-w-[90px] truncate">
                      {sessions.find((s) => s.id === activeSessionId)?.title ||
                        "Phiên chat"}
                    </span>
                    <ChevronDown className="h-3 w-3 opacity-70" />
                  </button>

                  {isSessionMenuOpen && (
                    <div className="absolute right-0 top-8 z-30 w-64 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl py-1.5 text-xs">
                      <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                        Phiên hội thoại ({sessions.length})
                      </div>
                      <div className="max-h-52 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800/60">
                        {sessions.map((s) => (
                          <div
                            key={s.id}
                            className={`px-2.5 py-1.5 flex items-center justify-between gap-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors ${
                              s.id === activeSessionId
                                ? "bg-indigo-50/80 dark:bg-indigo-950/40 text-indigo-600 dark:text-indigo-300 font-semibold"
                                : "text-slate-700 dark:text-slate-300"
                            }`}
                          >
                            <button
                              type="button"
                              onClick={() => void handleSelectSession(s)}
                              className="flex-1 min-w-0 text-left truncate py-0.5 cursor-pointer"
                            >
                              {s.title}
                            </button>
                            <button
                              type="button"
                              disabled={deletingSessionId === s.id}
                              onClick={(e) => void handleDeleteSession(s.id, e)}
                              title="Xóa phiên hội thoại này"
                              aria-label={`Xóa ${s.title}`}
                              className="h-6 w-6 rounded-md flex items-center justify-center text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/60 dark:hover:text-rose-400 transition-colors shrink-0 cursor-pointer disabled:opacity-40"
                            >
                              {deletingSessionId === s.id ? (
                                <Loader2 className="h-3 w-3 animate-spin" />
                              ) : (
                                <Trash2 className="h-3.5 w-3.5 stroke-[1.9]" />
                              )}
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <button
                type="button"
                onClick={() => void handleCreateNewSession()}
                title="Bắt đầu hội thoại mới"
                className="h-7 px-2 rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-[11px] font-medium text-slate-700 dark:text-slate-200 inline-flex items-center gap-1 whitespace-nowrap shrink-0 transition-colors cursor-pointer"
              >
                <Plus className="h-3.5 w-3.5 stroke-[2] shrink-0" />
                <span className="hidden sm:inline">Mới</span>
              </button>

              {activeSessionId && (
                <button
                  type="button"
                  disabled={deletingSessionId === activeSessionId}
                  onClick={() => void handleDeleteSession(activeSessionId)}
                  title="Xóa phiên hội thoại đang mở"
                  aria-label="Xóa phiên hội thoại đang mở"
                  className="h-7 w-7 rounded-lg border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-rose-50 hover:border-rose-200 hover:text-rose-600 dark:hover:bg-rose-950/40 dark:hover:border-rose-900/60 dark:hover:text-rose-400 text-slate-400 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-40"
                >
                  {deletingSessionId === activeSessionId ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5 stroke-[1.9]" />
                  )}
                </button>
              )}
            </>
          )}

          <button
            type="button"
            onClick={onClose}
            aria-label="Close AI Tutor split view"
            title="Đóng AI Tutor"
            className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer"
          >
            <X className="h-4 w-4 stroke-[1.8]" />
          </button>
        </div>
      </div>

      {/* Document indexing warning if not ready yet */}
      {isDocNotReady && (
        <div className="px-3.5 py-2 bg-amber-50 dark:bg-amber-950/40 border-b border-amber-200/70 dark:border-amber-900/50 flex items-center gap-2 text-[11px] text-amber-800 dark:text-amber-300">
          <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0 text-amber-600" />
          <span>
            Tài liệu đang ở trạng thái{" "}
            <strong className="font-mono">{document.status}</strong>. Trích dẫn
            trang RAG sẽ chính xác nhất sau khi xử lý xong (`ready`).
          </span>
        </div>
      )}

      {/* ====================================================================
          MODE 1: CONVERSATIONAL AI TUTOR (SOCRATIC 3-TIER + RAG CITATIONS)
         ==================================================================== */}
      {panelMode === "chat" ? (
        <>
          {/* Socratic Mode Control Bar & 3-Tier Visual Progress */}
          <div className="px-3.5 py-2.5 border-b border-slate-200/70 dark:border-slate-800/70 bg-slate-50/40 dark:bg-slate-900/30 space-y-2 shrink-0">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <div
                  className={`h-6 w-6 rounded-lg flex items-center justify-center shrink-0 transition-colors ${
                    socraticEnabled
                      ? "bg-indigo-600 text-white shadow-xs"
                      : "bg-slate-200/80 dark:bg-slate-800 text-slate-500"
                  }`}
                >
                  <GraduationCap className="h-3.5 w-3.5 stroke-[2]" />
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-semibold text-slate-900 dark:text-white truncate">
                      Chế độ Socratic Gia sư
                    </span>
                    <span
                      className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold uppercase tracking-wide ${
                        socraticEnabled
                          ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300"
                          : "bg-slate-200/70 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                      }`}
                    >
                      {socraticEnabled ? "BẬT" : "TẮT"}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate">
                    {socraticEnabled
                      ? "Gợi mở 3 tầng (Lý thuyết → Bài mẫu → Từng bước), không giải hộ"
                      : "Giải thích lý thuyết nhanh • Chặn giải hộ bài tập trực tiếp"}
                  </p>
                </div>
              </div>

              {/* Toggle Switch */}
              <button
                type="button"
                role="switch"
                aria-checked={socraticEnabled}
                onClick={() => setSocraticEnabled((prev) => !prev)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  socraticEnabled
                    ? "bg-indigo-600"
                    : "bg-slate-300 dark:bg-slate-700"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                    socraticEnabled ? "translate-x-5" : "translate-x-0"
                  }`}
                />
              </button>
            </div>

            {/* Sequential Socratic Actions when in an active problem */}
            {socraticEnabled && currentTier > 0 && (
              <div className="flex items-center justify-between gap-1.5 pt-0.5">
                <div className="flex items-center gap-1.5 flex-wrap">
                  {currentTier < 3 && (
                    <button
                      type="button"
                      disabled={isStreaming}
                      onClick={() =>
                        void sendMessage(
                          "Mình vẫn chưa hiểu rõ, bạn gợi ý thêm bằng ví dụ hoặc bước cụ thể hơn giúp mình nhé!",
                          {
                            forceSocratic: true,
                            requestedTier: Math.min(currentTier + 1, 3),
                          }
                        )
                      }
                      className="h-6 px-2.5 rounded-md bg-indigo-100/80 hover:bg-indigo-200/80 dark:bg-indigo-950/80 dark:hover:bg-indigo-900 text-indigo-700 dark:text-indigo-300 text-[11px] font-medium inline-flex items-center gap-1 transition-colors cursor-pointer disabled:opacity-50"
                    >
                      <Lightbulb className="h-3 w-3" />
                      <span>Gợi ý sâu hơn (Lên Tầng {currentTier + 1})</span>
                    </button>
                  )}
                  <button
                    type="button"
                    disabled={isStreaming}
                    onClick={() => {
                      setIsNewQuestionFlag(true)
                      setCurrentTier(1)
                      setLastSolved(false)
                    }}
                    className={`h-6 px-2.5 rounded-md text-[11px] font-medium inline-flex items-center gap-1 transition-colors cursor-pointer ${
                      isNewQuestionFlag
                        ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300 ring-1 ring-amber-400/40"
                        : "bg-slate-200/70 hover:bg-slate-300/70 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
                    }`}
                  >
                    <RotateCcw className="h-3 w-3" />
                    <span>
                      {isNewQuestionFlag
                        ? "Câu tiếp theo sẽ về Tầng 1"
                        : "Đổi sang bài tập mới"}
                    </span>
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {isLoadingHistory ? (
              <div className="h-full flex flex-col items-center justify-center gap-2 text-slate-400">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                <span className="text-xs font-medium">
                  Đang tải lịch sử hội thoại...
                </span>
              </div>
            ) : messages.length === 0 ? (
              <div className="min-h-full flex flex-col justify-center py-4">
                <div className="max-w-sm mx-auto text-center space-y-4">
                  <div className="mx-auto h-11 w-11 rounded-2xl bg-gradient-to-br from-indigo-500/15 via-blue-600/15 to-sky-500/15 ring-1 ring-indigo-500/20 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
                    <Sparkles className="h-5 w-5 stroke-[1.8]" />
                  </div>

                  <div className="space-y-1">
                    <h3 className="text-sm font-bold tracking-tight text-slate-900 dark:text-white">
                      Học cùng AI Gia sư • &ldquo;{document.title}&rdquo;
                    </h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                      Mọi định lý và công thức đều được trích dẫn kèm thẻ{" "}
                      <span className="inline-flex items-center rounded-full bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 px-2 py-0.5 text-[10px] font-semibold">
                        Trang X
                      </span>{" "}
                      — nhấn vào thẻ để cuộn PDF tới đúng trang sách.
                    </p>
                  </div>

                  {/* Starter Prompts */}
                  <div className="space-y-2 text-left pt-1">
                    <p className="text-[11px] font-medium text-slate-400 dark:text-slate-500 px-1">
                      Gợi ý câu hỏi bắt đầu
                    </p>
                    {SUGGESTED_PROMPTS.map((item) => {
                      const Icon = item.icon
                      return (
                        <button
                          key={item.label}
                          type="button"
                          onClick={() => {
                            void sendMessage(item.prompt, {
                              forceSocratic: item.socratic,
                            })
                          }}
                          className="w-full flex items-center gap-3 rounded-xl border border-slate-200/80 dark:border-slate-800/80 bg-slate-50/60 dark:bg-slate-900/50 hover:bg-indigo-50/50 dark:hover:bg-slate-800/80 hover:border-indigo-500/40 px-3.5 py-2.5 text-xs font-medium text-slate-700 dark:text-slate-200 transition-all duration-150 cursor-pointer text-left active:scale-[0.99]"
                        >
                          <Icon className="h-4 w-4 text-indigo-600 dark:text-indigo-400 shrink-0 stroke-[1.8]" />
                          <span className="flex-1 truncate">{item.label}</span>
                          {item.socratic && (
                            <span className="rounded-md bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 px-1.5 py-0.5 text-[10px] font-semibold shrink-0">
                              Socratic
                            </span>
                          )}
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>
            ) : (
              messages.map((msg) => {
                if (msg.sender === "user") {
                  return (
                    <div key={msg.id} className="flex justify-end">
                      <div className="max-w-[85%] rounded-2xl rounded-tr-xs bg-indigo-600 text-white px-3.5 py-2.5 text-xs leading-relaxed shadow-xs">
                        <p className="whitespace-pre-wrap break-words">
                          {msg.content}
                        </p>
                      </div>
                    </div>
                  )
                }

                const badge = getTierBadgeInfo(
                  msg.socratic_tier,
                  msg.mode,
                  msg.solved
                )
                const allCitations =
                  msg.citations && msg.citations.length > 0
                    ? msg.citations
                    : msg.retrievedChunks || []

                // Deduplicate citations by page_number for clean pill display
                const uniquePageCitations = Array.from(
                  allCitations
                    .reduce((map, c) => {
                      const existing = map.get(c.page_number)
                      if (!existing || c.score > existing.score) {
                        map.set(c.page_number, c)
                      }
                      return map
                    }, new Map<number, ChatCitation>())
                    .values()
                ).sort((a, b) => a.page_number - b.page_number)

                const isRefusal =
                  msg.mode === "refusal" ||
                  msg.content.includes("Chế độ Socratic Gia sư")
                const isExpanded = Boolean(expandedSourceMsgIds[msg.id])

                return (
                  <div key={msg.id} className="flex justify-start">
                    <div
                      className={`w-full rounded-2xl rounded-tl-xs border p-3.5 text-xs space-y-2.5 shadow-2xs ${
                        msg.isError
                          ? "border-rose-200 dark:border-rose-900/60 bg-rose-50/50 dark:bg-rose-950/30 text-rose-700 dark:text-rose-300"
                          : isRefusal && msg.socratic_tier === 0
                            ? "border-amber-200/90 dark:border-amber-900/60 bg-amber-50/40 dark:bg-amber-950/20 text-slate-800 dark:text-slate-200"
                            : "border-slate-200/80 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-900/70 text-slate-800 dark:text-slate-200"
                      }`}
                    >
                      {/* Assistant Message Header: Tutor Identity + Socratic Tier Badge */}
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          <div className="h-5 w-5 rounded-md bg-indigo-600/10 dark:bg-indigo-500/20 text-indigo-600 dark:text-indigo-400 flex items-center justify-center">
                            {isRefusal && msg.socratic_tier === 0 ? (
                              <ShieldAlert className="h-3 w-3 stroke-[2.2] text-amber-600" />
                            ) : (
                              <Sparkles className="h-3 w-3 stroke-[2.2]" />
                            )}
                          </div>
                          <span className="font-semibold text-[11px] text-slate-900 dark:text-white">
                            AI Tutor
                          </span>
                        </div>

                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${badge.className}`}
                        >
                          {badge.label}
                        </span>
                      </div>

                      {/* Message Content with KaTeX & Inline [[Trang X]] Citations */}
                      {msg.content ? (
                        <ChatMarkdownRenderer
                          content={msg.content}
                          citations={allCitations}
                          onSelectPage={onSelectCitationPage}
                        />
                      ) : msg.isStreaming ? (
                        <div className="py-2 flex items-center gap-2 text-slate-400">
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-600" />
                          <span className="text-[11px]">
                            Đang truy xuất tài liệu & suy luận...
                          </span>
                        </div>
                      ) : null}

                      {/* 1-Click CTA when Homework Guardrail Refuses Direct Solution */}
                      {isRefusal &&
                        msg.socratic_tier === 0 &&
                        !msg.isStreaming && (
                          <div className="pt-1">
                            <button
                              type="button"
                              onClick={() => {
                                const promptToRetry =
                                  lastBlockedPrompt ||
                                  [...messages]
                                    .reverse()
                                    .find((m) => m.sender === "user")?.content
                                setSocraticEnabled(true)
                                if (promptToRetry) {
                                  void sendMessage(promptToRetry, {
                                    forceSocratic: true,
                                    newQuestion: true,
                                  })
                                }
                              }}
                              className="w-full py-2 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs inline-flex items-center justify-center gap-2 shadow-xs transition-all cursor-pointer active:scale-[0.99]"
                            >
                              <GraduationCap className="h-4 w-4" />
                              <span>
                                Bật Chế độ Socratic & Nhận gợi ý Tầng 1 ngay
                              </span>
                            </button>
                          </div>
                        )}

                      {/* Citations Footer & Source Excerpt Drawer */}
                      {uniquePageCitations.length > 0 && (
                        <div className="pt-2 border-t border-slate-200/70 dark:border-slate-800/80 space-y-2">
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                Nguồn trích dẫn:
                              </span>
                              {uniquePageCitations.map((cit) => (
                                <button
                                  key={cit.chunk_id || cit.page_number}
                                  type="button"
                                  onClick={() =>
                                    onSelectCitationPage(cit.page_number, cit)
                                  }
                                  title={
                                    cit.content
                                      ? `Nhấn để mở Trang ${cit.page_number}: "${cit.content.slice(0, 140)}..."`
                                      : `Nhấn để cuộn PDF tới Trang ${cit.page_number}`
                                  }
                                  className="inline-flex items-center gap-1 rounded-full text-[11px] font-semibold bg-indigo-100 text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-950/90 dark:text-indigo-300 dark:hover:bg-indigo-900 px-2.5 py-0.5 cursor-pointer ring-1 ring-indigo-500/20 transition-all active:scale-95"
                                >
                                  <BookOpen className="h-3 w-3 stroke-[2]" />
                                  <span>Trang {cit.page_number}</span>
                                </button>
                              ))}
                            </div>

                            {allCitations.some((c) => Boolean(c.content)) && (
                              <button
                                type="button"
                                onClick={() => toggleExpandSources(msg.id)}
                                className="text-[11px] font-medium text-indigo-600 dark:text-indigo-400 hover:underline inline-flex items-center gap-0.5 cursor-pointer"
                              >
                                <span>
                                  {isExpanded
                                    ? "Ẩn đoạn trích"
                                    : `Xem đoạn trích (${allCitations.length})`}
                                </span>
                                {isExpanded ? (
                                  <ChevronUp className="h-3 w-3" />
                                ) : (
                                  <ChevronDown className="h-3 w-3" />
                                )}
                              </button>
                            )}
                          </div>

                          {/* Expandable Retrieved Chunks Preview */}
                          {isExpanded && (
                            <div className="space-y-2 pt-1">
                              {allCitations.map((chunk, idx) => (
                                <div
                                  key={chunk.chunk_id || idx}
                                  className="rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-950 p-2.5 space-y-1.5"
                                >
                                  <div className="flex items-center justify-between gap-2">
                                    <button
                                      type="button"
                                      onClick={() =>
                                        onSelectCitationPage(
                                          chunk.page_number,
                                          chunk
                                        )
                                      }
                                      className="inline-flex items-center gap-1 rounded-full bg-indigo-100 dark:bg-indigo-950 text-indigo-700 dark:text-indigo-300 px-2 py-0.5 text-[10px] font-semibold hover:bg-indigo-200 cursor-pointer"
                                    >
                                      <BookOpen className="h-2.5 w-2.5" />
                                      <span>
                                        Mở Trang {chunk.page_number} trên PDF
                                      </span>
                                    </button>
                                  </div>
                                  {chunk.content && (
                                    <div className="text-[11px] text-slate-600 dark:text-slate-300 line-clamp-4">
                                      <ChatMarkdownRenderer
                                        content={chunk.content}
                                        onSelectPage={onSelectCitationPage}
                                      />
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })
            )}

            {chatError && (
              <div className="rounded-xl border border-rose-200/80 dark:border-rose-900/50 bg-rose-50/70 dark:bg-rose-950/40 p-3 text-xs text-rose-600 dark:text-rose-400">
                {chatError}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Bottom Message Composer */}
          <form
            onSubmit={handleFormSubmit}
            className="p-3 border-t border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-950 shrink-0 space-y-2"
          >
            {/* Scope Filter Bar */}
            <div className="flex items-center justify-between gap-2 px-0.5">
              <button
                type="button"
                onClick={() => setLimitToCurrentPage((prev) => !prev)}
                className={`h-6 px-2.5 rounded-full text-[11px] font-medium inline-flex items-center gap-1.5 transition-colors cursor-pointer ${
                  limitToCurrentPage
                    ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300 ring-1 ring-indigo-500/25"
                    : "bg-slate-100 hover:bg-slate-200/70 dark:bg-slate-900 text-slate-600 dark:text-slate-400"
                }`}
              >
                <Filter className="h-3 w-3" />
                <span>
                  {limitToCurrentPage
                    ? `Chỉ tra cứu Trang ${currentPage}`
                    : "Tra cứu toàn bộ tài liệu"}
                </span>
              </button>

              <span className="text-[10px] text-slate-400 font-mono">
                Đang xem: Trang {currentPage}/{document.total_pages}
              </span>
            </div>

            <div className="relative flex items-end gap-2">
              <textarea
                rows={1}
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault()
                    if (inputValue.trim() && !isStreaming) {
                      void sendMessage(inputValue)
                    }
                  }
                }}
                placeholder={
                  socraticEnabled
                    ? "Nhập đề bài tập hoặc bước giải của bạn để Gia sư gợi mở..."
                    : `Đặt câu hỏi về "${document.title}"...`
                }
                aria-label="Ask AI Tutor a question"
                className="min-h-[42px] max-h-28 w-full resize-none rounded-xl bg-[#F1F4F8] dark:bg-slate-900 py-2.5 pl-3.5 pr-11 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 border border-transparent focus:border-indigo-500/40 focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:ring-4 focus:ring-indigo-500/10 transition-all duration-150"
              />

              {isStreaming ? (
                <button
                  type="button"
                  onClick={handleStopStreaming}
                  aria-label="Stop generating"
                  title="Dừng phản hồi"
                  className="absolute right-1.5 bottom-1.5 h-8 w-8 rounded-lg bg-rose-600 hover:bg-rose-700 text-white flex items-center justify-center transition-colors cursor-pointer"
                >
                  <Square className="h-3.5 w-3.5 fill-current" />
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!inputValue.trim()}
                  aria-label="Send message"
                  title="Gửi tin nhắn (Enter)"
                  className="absolute right-1.5 bottom-1.5 h-8 w-8 rounded-lg bg-indigo-600 hover:bg-indigo-700 active:scale-[0.97] text-white flex items-center justify-center transition-all duration-150 cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
                >
                  <Send className="h-3.5 w-3.5 stroke-[2]" />
                </button>
              )}
            </div>
          </form>
        </>
      ) : (
        /* ====================================================================
           MODE 2: DIRECT SEMANTIC RAG CITATION SEARCH
           ==================================================================== */
        <div className="flex-1 flex flex-col min-h-0">
          <form
            onSubmit={handleSearchChunks}
            className="p-3.5 border-b border-slate-200/80 dark:border-slate-800/80 bg-slate-50/40 dark:bg-slate-900/30 space-y-2.5 shrink-0"
          >
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-800 dark:text-slate-200 block">
                Tra cứu ngữ nghĩa & Trích dẫn tài liệu (Qdrant RAG)
              </label>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Tìm nhanh đoạn văn bản, định lý hoặc công thức LaTeX trong giáo
                trình và nhảy thẳng tới trang PDF.
              </p>
            </div>

            <div className="relative flex items-center">
              <Search className="absolute left-3 h-3.5 w-3.5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Nhập khái niệm, định lý hoặc công thức cần tìm..."
                className="h-9 w-full rounded-xl bg-white dark:bg-slate-900 pl-9 pr-20 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 border border-slate-200 dark:border-slate-800 focus:border-indigo-500 focus:outline-none focus:ring-3 focus:ring-indigo-500/15"
              />
              <button
                type="submit"
                disabled={isSearchingChunks || searchQuery.trim().length < 2}
                className="absolute right-1 h-7 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-[11px] font-semibold transition-colors cursor-pointer disabled:opacity-40"
              >
                {isSearchingChunks ? "Đang tìm..." : "Tìm kiếm"}
              </button>
            </div>

            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => setSearchPageOnly((prev) => !prev)}
                className={`h-6 px-2.5 rounded-full text-[11px] font-medium inline-flex items-center gap-1.5 transition-colors cursor-pointer ${
                  searchPageOnly
                    ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300 ring-1 ring-indigo-500/25"
                    : "bg-slate-200/70 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
                }`}
              >
                <Filter className="h-3 w-3" />
                <span>
                  {searchPageOnly
                    ? `Chỉ tìm trong Trang ${currentPage}`
                    : "Tìm trên toàn bộ các trang"}
                </span>
              </button>
            </div>
          </form>

          {/* Search Results List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {isSearchingChunks ? (
              <div className="py-16 flex flex-col items-center justify-center gap-2 text-slate-400">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-600" />
                <span className="text-xs font-medium">
                  Đang truy xuất các đoạn trích liên quan từ Qdrant...
                </span>
              </div>
            ) : searchError ? (
              <div className="rounded-xl border border-rose-200 dark:border-rose-900/50 bg-rose-50/70 dark:bg-rose-950/30 p-3.5 text-xs text-rose-600 dark:text-rose-400">
                {searchError}
              </div>
            ) : searchResults === null ? (
              <div className="py-14 text-center space-y-2 max-w-xs mx-auto">
                <FileSearch className="h-8 w-8 text-slate-300 dark:text-slate-700 mx-auto stroke-[1.6]" />
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Nhập từ khóa hoặc câu hỏi để tra cứu
                </p>
                <p className="text-[11px] text-slate-400">
                  Hệ thống sẽ tìm các đoạn văn bản có độ tương đồng ngữ nghĩa cao
                  nhất kèm số trang chính xác.
                </p>
              </div>
            ) : searchResults.length === 0 ? (
              <div className="py-14 text-center space-y-2 max-w-xs mx-auto">
                <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Không tìm thấy đoạn trích nào vượt ngưỡng tương đồng
                </p>
                <p className="text-[11px] text-slate-400">
                  Hãy thử diễn đạt câu hỏi cụ thể hơn hoặc bỏ bộ lọc trang hiện
                  tại.
                </p>
              </div>
            ) : (
              searchResults.map((chunk) => (
                <div
                  key={chunk.chunk_id}
                  className="rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-900/60 p-3.5 space-y-2.5 hover:border-indigo-500/40 transition-colors"
                >
                  <div className="flex items-center justify-between gap-2 flex-wrap">
                    <button
                      type="button"
                      onClick={() =>
                        onSelectCitationPage(chunk.page_number, {
                          chunk_id: chunk.chunk_id,
                          page_number: chunk.page_number,
                          score: chunk.score,
                          citation_tag: chunk.citation_tag,
                          content: chunk.content,
                          has_formula: chunk.has_formula,
                          has_image: chunk.has_image,
                        })
                      }
                      className="inline-flex items-center gap-1.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-950 dark:text-indigo-300 px-3 py-1 cursor-pointer ring-1 ring-indigo-500/20 transition-all active:scale-95"
                    >
                      <BookOpen className="h-3.5 w-3.5 stroke-[2]" />
                      <span>Trang {chunk.page_number}</span>
                    </button>
                  </div>

                  <div className="text-xs text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-950 rounded-xl p-3 border border-slate-200/60 dark:border-slate-800/70">
                    <ChatMarkdownRenderer
                      content={chunk.content}
                      onSelectPage={onSelectCitationPage}
                    />
                  </div>

                  <div className="flex items-center justify-between gap-2 pt-0.5">
                    <button
                      type="button"
                      onClick={() =>
                        onSelectCitationPage(chunk.page_number, {
                          chunk_id: chunk.chunk_id,
                          page_number: chunk.page_number,
                          score: chunk.score,
                          citation_tag: chunk.citation_tag,
                          content: chunk.content,
                        })
                      }
                      className="text-[11px] font-semibold text-indigo-600 dark:text-indigo-400 hover:underline cursor-pointer"
                    >
                      Cuộn PDF tới Trang {chunk.page_number} →
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setPanelMode("chat")
                        void sendMessage(
                          `Giải thích giúp mình nội dung ở [[Trang ${chunk.page_number}]]: "${chunk.content.slice(0, 220)}..."`
                        )
                      }}
                      className="h-7 px-2.5 rounded-lg bg-indigo-600/10 hover:bg-indigo-600/20 text-indigo-700 dark:text-indigo-300 text-[11px] font-semibold inline-flex items-center gap-1 transition-colors cursor-pointer"
                    >
                      <Sparkles className="h-3 w-3" />
                      <span>Hỏi Gia sư đoạn này</span>
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </section>
  )
}
