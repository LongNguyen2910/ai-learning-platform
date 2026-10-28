"use client"

import * as React from "react"
import katex from "katex"
import { BookOpen } from "lucide-react"
import type { ChatCitation } from "@/lib/api/chat"

interface ChatMarkdownRendererProps {
  content: string
  citations?: ChatCitation[]
  onSelectPage?: (pageNumber: number, citation?: ChatCitation) => void
  className?: string
}

/**
 * Normalizes LaTeX math syntax to be KaTeX compatible.
 * Converts TeX primitive equation numbering (\eqno, \leqno) into KaTeX-supported \tag{...}.
 */
function normalizeLatex(formula: string): string {
  if (!formula || (!formula.includes("\\eqno") && !formula.includes("\\leqno"))) {
    return formula
  }
  return formula.replace(
    /\\(?:eqno|leqno)(?:\s*\(([^)]+)\)|\s*\{([^}]+)\}|\s+([0-9a-zA-Z*._-]+))/g,
    (_, p1, p2, p3) => {
      let val = (p1 || p2 || p3 || "").trim()
      if (val.startsWith("(") && val.endsWith(")")) {
        val = val.slice(1, -1).trim()
      }
      return `\\tag{${val}}`
    }
  )
}

function renderLatex(formula: string, displayMode: boolean): string {
  try {
    const cleanFormula = normalizeLatex(formula.trim())
    const effectiveDisplayMode = displayMode || /\\tag\b/.test(cleanFormula)

    return katex.renderToString(cleanFormula, {
      displayMode: effectiveDisplayMode,
      throwOnError: false,
      strict: "ignore",
      output: "htmlAndMathml",
    })
  } catch {
    return formula
  }
}

/**
 * Tokenizes inline text into:
 * - Citation tags: `[[Trang 12]]`, `[[Page 12]]`, `[Trang 12]`
 * - Display math inline: `$$...$$`
 * - Inline math: `$...$`
 * - Inline code: `` `...` ``
 * - Bold: `**...**`
 */
const INLINE_TOKEN_REGEX =
  /(\[\[\s*(?:Trang|Page)\s+\d+(?:\s*[,;-]\s*\d+)*\s*\]\]|\[\s*Trang\s+\d+\s*\]|\$\$[\s\S]+?\$\$|\$(?:\\.|[^$\n])+?\$|`[^`\n]+`|\*\*[^*\n]+\*\*)/gi

export const ChatMarkdownRenderer = React.memo(function ChatMarkdownRenderer({
  content,
  citations = [],
  onSelectPage,
  className = "",
}: ChatMarkdownRendererProps) {
  const citationByPage = React.useMemo(() => {
    const map = new Map<number, ChatCitation>()
    for (const c of citations) {
      if (!map.has(c.page_number) || c.score > (map.get(c.page_number)?.score ?? 0)) {
        map.set(c.page_number, c)
      }
    }
    return map
  }, [citations])

  const renderInlineNodes = React.useCallback(
    (text: string, keyPrefix: string): React.ReactNode[] => {
      if (!text) return []
      const parts = text.split(INLINE_TOKEN_REGEX)
      const nodes: React.ReactNode[] = []

      parts.forEach((part, idx) => {
        if (!part) return
        const key = `${keyPrefix}-${idx}`

        // 1. Citation tag: [[Trang X]] or [Trang X]
        const citationMatch = part.match(
          /^\[\[?\s*(?:Trang|Page)\s+(\d+(?:\s*[,;-]\s*\d+)*)\s*\]?\]$/i
        )
        if (citationMatch) {
          const pageNums = citationMatch[1]
            .split(/[,;-]/)
            .map((s) => parseInt(s.trim(), 10))
            .filter((n) => !Number.isNaN(n) && n >= 1)

          if (pageNums.length > 0) {
            pageNums.forEach((pageNum, pIdx) => {
              const matchedCitation = citationByPage.get(pageNum)
              const scorePercent = matchedCitation
                ? Math.round(matchedCitation.score * 100)
                : null
              const tooltip = matchedCitation?.content
                ? `Trang ${pageNum}${scorePercent ? ` (${scorePercent}% liên quan)` : ""}: "${matchedCitation.content.slice(0, 180)}..."`
                : `Nhấn để cuộn PDF tới Trang ${pageNum}`

              nodes.push(
                <button
                  key={`${key}-p-${pIdx}`}
                  type="button"
                  onClick={() => onSelectPage?.(pageNum, matchedCitation)}
                  title={tooltip}
                  className="inline-flex items-center gap-1 rounded-full text-[11px] font-semibold bg-indigo-100 text-indigo-700 hover:bg-indigo-200 dark:bg-indigo-950/90 dark:text-indigo-300 dark:hover:bg-indigo-900 px-2 py-0.5 mx-0.5 align-baseline cursor-pointer ring-1 ring-indigo-500/20 shadow-2xs transition-all duration-150 active:scale-95 select-none"
                >
                  <BookOpen className="h-2.5 w-2.5 stroke-[2.2] shrink-0" />
                  <span>Trang {pageNum}</span>
                </button>
              )
            })
            return
          }
        }

        // 2. Display math inside paragraph: $$...$$
        if (part.startsWith("$$") && part.endsWith("$$") && part.length > 4) {
          const formula = part.slice(2, -2)
          const html = renderLatex(formula, true)
          nodes.push(
            <span
              key={key}
              className="block my-2 overflow-x-auto py-1 text-center"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          )
          return
        }

        // 3. Inline math: $...$
        if (part.startsWith("$") && part.endsWith("$") && part.length > 2) {
          const formula = part.slice(1, -1)
          const hasTag = /\\(?:tag|eqno|leqno)\b/.test(formula)
          const isDisplay = hasTag
          const html = renderLatex(formula, isDisplay)
          nodes.push(
            <span
              key={key}
              className={
                isDisplay
                  ? "block my-2 overflow-x-auto py-1 text-center"
                  : "inline-block align-middle mx-0.5"
              }
              dangerouslySetInnerHTML={{ __html: html }}
            />
          )
          return
        }

        // 4. Inline code: `...`
        if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
          nodes.push(
            <code
              key={key}
              className="px-1.5 py-0.5 mx-0.5 rounded-md bg-slate-200/75 dark:bg-slate-800 font-mono text-[11px] text-indigo-700 dark:text-indigo-300"
            >
              {part.slice(1, -1)}
            </code>
          )
          return
        }

        // 5. Bold text: **...**
        if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
          nodes.push(
            <strong
              key={key}
              className="font-semibold text-slate-900 dark:text-white"
            >
              {renderInlineNodes(part.slice(2, -2), `${key}-b`)}
            </strong>
          )
          return
        }

        nodes.push(<React.Fragment key={key}>{part}</React.Fragment>)
      })

      return nodes
    },
    [citationByPage, onSelectPage]
  )

  const blocks = React.useMemo(() => {
    if (!content) return []

    // Split out fenced code blocks and multi-line $$...$$ display math first
    const segments = content.split(/(```[\s\S]*?```|\$\$[\s\S]*?\$\$)/g)
    const renderedBlocks: React.ReactNode[] = []

    segments.forEach((segment, segIdx) => {
      if (!segment.trim()) return

      // Fenced code block
      if (segment.startsWith("```") && segment.endsWith("```")) {
        const lines = segment.slice(3, -3).split("\n")
        const firstLine = lines[0]?.trim() ?? ""
        const codeContent =
          /^[a-zA-Z0-9_-]+$/.test(firstLine) && lines.length > 1
            ? lines.slice(1).join("\n")
            : lines.join("\n")

        renderedBlocks.push(
          <pre
            key={`code-${segIdx}`}
            className="my-2.5 p-3 rounded-xl bg-slate-900 text-slate-100 font-mono text-[11.5px] leading-relaxed overflow-x-auto border border-slate-800"
          >
            <code>{codeContent.trim()}</code>
          </pre>
        )
        return
      }

      // Multi-line display math block $$...$$
      if (segment.startsWith("$$") && segment.endsWith("$$")) {
        const formula = segment.slice(2, -2)
        const html = renderLatex(formula, true)
        renderedBlocks.push(
          <div
            key={`math-${segIdx}`}
            className="my-2.5 py-2 px-3 rounded-xl bg-slate-100/70 dark:bg-slate-900/60 overflow-x-auto text-center border border-slate-200/60 dark:border-slate-800/60"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        )
        return
      }

      // Standard Markdown lines
      const lines = segment.split(/\r?\n/)
      let listItems: { type: "ul" | "ol"; items: string[] } | null = null

      const flushList = (keySuffix: string) => {
        if (!listItems) return
        const currentList = listItems
        listItems = null
        if (currentList.type === "ul") {
          renderedBlocks.push(
            <ul
              key={`ul-${segIdx}-${keySuffix}`}
              className="my-1.5 pl-4 space-y-1 list-disc marker:text-indigo-500"
            >
              {currentList.items.map((item, i) => (
                <li key={i} className="leading-relaxed">
                  {renderInlineNodes(item, `ul-${segIdx}-${keySuffix}-${i}`)}
                </li>
              ))}
            </ul>
          )
        } else {
          renderedBlocks.push(
            <ol
              key={`ol-${segIdx}-${keySuffix}`}
              className="my-1.5 pl-4 space-y-1 list-decimal marker:text-indigo-500 marker:font-semibold"
            >
              {currentList.items.map((item, i) => (
                <li key={i} className="leading-relaxed">
                  {renderInlineNodes(item, `ol-${segIdx}-${keySuffix}-${i}`)}
                </li>
              ))}
            </ol>
          )
        }
      }

      lines.forEach((rawLine, lineIdx) => {
        const line = rawLine.trim()
        if (!line) {
          flushList(String(lineIdx))
          return
        }

        // Heading ### / ## / #
        const headingMatch = line.match(/^(#{1,3})\s+(.+)$/)
        if (headingMatch) {
          flushList(String(lineIdx))
          const level = headingMatch[1].length
          const text = headingMatch[2]
          const sizeClass =
            level === 1
              ? "text-sm font-bold"
              : level === 2
                ? "text-[13px] font-bold"
                : "text-xs font-semibold"
          renderedBlocks.push(
            <h4
              key={`h-${segIdx}-${lineIdx}`}
              className={`${sizeClass} text-slate-900 dark:text-white mt-2.5 mb-1`}
            >
              {renderInlineNodes(text, `h-${segIdx}-${lineIdx}`)}
            </h4>
          )
          return
        }

        // Unordered list item (- or * or •)
        const ulMatch = line.match(/^[-*•]\s+(.+)$/)
        if (ulMatch) {
          if (listItems && listItems.type !== "ul") {
            flushList(String(lineIdx))
          }
          if (!listItems) {
            listItems = { type: "ul", items: [] }
          }
          listItems.items.push(ulMatch[1])
          return
        }

        // Ordered list item (1. or 1))
        const olMatch = line.match(/^\d+[.)]\s+(.+)$/)
        if (olMatch) {
          if (listItems && listItems.type !== "ol") {
            flushList(String(lineIdx))
          }
          if (!listItems) {
            listItems = { type: "ol", items: [] }
          }
          listItems.items.push(olMatch[1])
          return
        }

        // Blockquote (> ...)
        if (line.startsWith(">")) {
          flushList(String(lineIdx))
          const quoteText = line.replace(/^>\s*/, "")
          renderedBlocks.push(
            <blockquote
              key={`q-${segIdx}-${lineIdx}`}
              className="my-2 pl-3 border-l-2 border-indigo-500/60 italic text-slate-600 dark:text-slate-300"
            >
              {renderInlineNodes(quoteText, `q-${segIdx}-${lineIdx}`)}
            </blockquote>
          )
          return
        }

        // Regular paragraph line
        flushList(String(lineIdx))
        renderedBlocks.push(
          <p key={`p-${segIdx}-${lineIdx}`} className="leading-relaxed my-1">
            {renderInlineNodes(line, `p-${segIdx}-${lineIdx}`)}
          </p>
        )
      })

      flushList("end")
    })

    return renderedBlocks
  }, [content, renderInlineNodes])

  return (
    <div className={`space-y-1 break-words ${className}`}>{blocks}</div>
  )
})
