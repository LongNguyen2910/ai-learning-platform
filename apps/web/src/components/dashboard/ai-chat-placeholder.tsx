"use client"

import * as React from "react"
import {
  Sparkles,
  Send,
  X,
  BookOpen,
  HelpCircle,
  Lightbulb,
} from "lucide-react"
import type { DocumentItem } from "@/lib/api/documents"

interface AiChatPlaceholderProps {
  document: DocumentItem
  onClose: () => void
}

const SUGGESTED_PROMPTS = [
  {
    icon: BookOpen,
    label: "Summarize core concepts",
    prompt: "Can you summarize the core concepts and structure of this document?",
  },
  {
    icon: Lightbulb,
    label: "Explain formulas with Socratic hints",
    prompt: "Walk me through the main mathematical formulas step-by-step.",
  },
  {
    icon: HelpCircle,
    label: "Test my understanding",
    prompt: "Ask me a Socratic question to check my understanding of page 1.",
  },
]

export function AiChatPlaceholder({
  document,
  onClose,
}: AiChatPlaceholderProps) {
  const [inputValue, setInputValue] = React.useState("")
  const [previewBanner, setPreviewBanner] = React.useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputValue.trim()) return
    setPreviewBanner(true)
    setInputValue("")
  }

  return (
    <section
      aria-label="AI Tutor Chat Panel"
      className="h-full w-full flex flex-col bg-white dark:bg-slate-950 border-l border-slate-200/80 dark:border-slate-800/80 select-none"
    >
      {/* Top Chat Header */}
      <div className="h-12 px-4 border-b border-slate-200/80 dark:border-slate-800/80 flex items-center justify-between shrink-0 bg-slate-50/50 dark:bg-slate-900/40">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="h-6 w-6 rounded-lg bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 text-[#0A77FF] dark:text-sky-400 flex items-center justify-center shrink-0">
            <Sparkles className="h-3.5 w-3.5 stroke-[2]" />
          </div>
          <span className="text-xs font-semibold text-slate-900 dark:text-white truncate">
            Socratic AI Tutor
          </span>
          <span className="rounded-md bg-slate-200/70 dark:bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono font-medium text-slate-600 dark:text-slate-400">
            Split-View 50/50
          </span>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close AI Tutor split view"
          title="Close AI Tutor"
          className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors cursor-pointer"
        >
          <X className="h-4 w-4 stroke-[1.8]" />
        </button>
      </div>

      {/* Chat Messages / Empty State Container */}
      <div className="flex-1 overflow-y-auto p-6 flex flex-col justify-center">
        <div className="max-w-sm mx-auto text-center space-y-5">
          <div className="mx-auto h-12 w-12 rounded-2xl bg-gradient-to-br from-sky-500/15 via-blue-600/15 to-indigo-600/15 ring-1 ring-[#0A77FF]/20 text-[#0A77FF] dark:text-sky-400 flex items-center justify-center">
            <Sparkles className="h-5 w-5 stroke-[1.8]" />
          </div>

          <div className="space-y-1.5">
            <h3 className="text-base font-bold tracking-tight text-slate-900 dark:text-white">
              Ask about &ldquo;{document.title}&rdquo;
            </h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
              Your AI Tutor uses 3-tier Socratic scaffolding and cites exact page numbers from this document.
            </p>
          </div>

          {/* Starter Prompt Starters */}
          <div className="space-y-2 text-left pt-1">
            <p className="text-[11px] font-medium text-slate-400 dark:text-slate-500 px-1">
              Suggested study prompts
            </p>
            {SUGGESTED_PROMPTS.map((item) => {
              const Icon = item.icon
              return (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => {
                    setInputValue(item.prompt)
                    setPreviewBanner(false)
                  }}
                  className="w-full flex items-center gap-3 rounded-xl border border-slate-200/80 dark:border-slate-800/80 bg-slate-50/60 dark:bg-slate-900/50 hover:bg-slate-100/80 dark:hover:bg-slate-800/70 hover:border-[#0A77FF]/40 px-3.5 py-2.5 text-xs font-medium text-slate-700 dark:text-slate-200 transition-all duration-150 cursor-pointer text-left active:scale-[0.99]"
                >
                  <Icon className="h-4 w-4 text-[#0A77FF] dark:text-sky-400 shrink-0 stroke-[1.75]" />
                  <span className="truncate">{item.label}</span>
                </button>
              )
            })}
          </div>

          {previewBanner && (
            <div
              role="status"
              className="rounded-xl border border-[#0A77FF]/20 bg-[#0A77FF]/[0.05] p-3 text-left text-xs text-slate-700 dark:text-slate-300 animate-in fade-in-0 duration-150"
            >
              <span className="font-semibold text-[#0A77FF] dark:text-sky-400 block mb-0.5">
                Chat UI Placeholder Ready
              </span>
              Real-time RAG streaming and page citation links will be connected when the Chat module is enabled.
            </div>
          )}
        </div>
      </div>

      {/* Bottom Message Input Bar */}
      <form
        onSubmit={handleSubmit}
        className="p-3.5 border-t border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-950 shrink-0"
      >
        <div className="relative flex items-center">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={`Ask a question about ${document.title}...`}
            aria-label="Ask AI Tutor a question"
            className="h-11 w-full rounded-xl bg-[#F1F4F8] dark:bg-slate-900 pl-4 pr-11 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 border border-transparent focus:border-[#0A77FF]/40 focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:ring-4 focus:ring-[#0A77FF]/10 transition-all duration-150"
          />
          <button
            type="submit"
            disabled={!inputValue.trim()}
            aria-label="Send message"
            className="absolute right-1.5 h-8 w-8 rounded-lg bg-[#0A77FF] hover:bg-[#0066E6] active:scale-[0.97] text-white flex items-center justify-center transition-all duration-150 cursor-pointer disabled:opacity-40 disabled:pointer-events-none"
          >
            <Send className="h-3.5 w-3.5 stroke-[2]" />
          </button>
        </div>
      </form>
    </section>
  )
}
