"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Sparkles,
  FileText,
  Network,
  Layers,
  Target,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface NavItem {
  label: string
  href: string
  icon: React.ComponentType<{ className?: string }>
  badge?: string
  disabled?: boolean
}

const NAV_ITEMS: NavItem[] = [
  {
    label: "Documents",
    href: "/dashboard",
    icon: FileText,
  },
  {
    label: "Roadmap",
    href: "#roadmap",
    icon: Network,
    badge: "Soon",
    disabled: true,
  },
  {
    label: "Flashcards",
    href: "#flashcards",
    icon: Layers,
    badge: "Soon",
    disabled: true,
  },
  {
    label: "Quizzes",
    href: "#quizzes",
    icon: Target,
    badge: "Soon",
    disabled: true,
  },
]

interface AppSidebarProps {
  collapsed: boolean
  onToggleCollapse: () => void
  onSelectDocumentsRoot?: () => void
}

export function AppSidebar({
  collapsed,
  onToggleCollapse,
  onSelectDocumentsRoot,
}: AppSidebarProps) {
  const pathname = usePathname()

  return (
    <aside
      aria-label="Primary Sidebar Navigation"
      className={cn(
        "relative flex flex-col border-r border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-950 select-none shrink-0 transition-[width] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)]",
        collapsed ? "w-[72px]" : "w-[260px]"
      )}
    >
      {/* Top Brand Header: App Logo + AI LEARNING PLATFORM */}
      <div
        className={cn(
          "h-16 flex items-center border-b border-slate-200/70 dark:border-slate-800/70 px-4",
          collapsed ? "justify-center" : "justify-start"
        )}
      >
        <Link
          href="/dashboard"
          onClick={() => onSelectDocumentsRoot?.()}
          className="flex items-center gap-3 min-w-0 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] rounded-lg"
          title="AI LEARNING PLATFORM"
        >
          {/* App Emblem (matching AuthBrandPanel) */}
          <div className="h-9 w-9 shrink-0 rounded-xl bg-gradient-to-br from-sky-500 via-blue-600 to-indigo-700 flex items-center justify-center text-white shadow-[0_2px_10px_rgba(10,119,255,0.3)] ring-1 ring-white/20">
            <Sparkles className="h-4 w-4 stroke-[2]" />
          </div>

          {!collapsed && (
            <div className="min-w-0">
              <span className="block text-[15px] font-bold tracking-tight text-slate-900 dark:text-white truncate leading-tight">
                AI LEARNING
              </span>
              <span className="block text-[11px] font-mono uppercase tracking-wider text-slate-400 dark:text-slate-500 truncate mt-0.5">
                PLATFORM
              </span>
            </div>
          )}
        </Link>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 py-4 px-3 space-y-1.5 overflow-y-auto">
        {!collapsed && (
          <div className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
            Study Menu
          </div>
        )}

        {NAV_ITEMS.map((item) => {
          const Icon = item.icon
          const isActive =
            !item.disabled &&
            (pathname === item.href || pathname.startsWith(`${item.href}/`))

          if (item.disabled) {
            return (
              <div
                key={item.label}
                title={`${item.label} (Coming soon)`}
                aria-disabled="true"
                className={cn(
                  "flex items-center rounded-xl text-[15px] font-medium text-slate-400 dark:text-slate-500 cursor-not-allowed opacity-75",
                  collapsed
                    ? "h-11 w-11 mx-auto justify-center"
                    : "h-11 px-3.5 justify-between"
                )}
              >
                <div className="flex items-center gap-3.5 min-w-0">
                  <Icon className="h-5 w-5 shrink-0 stroke-[1.75]" />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                </div>
                {!collapsed && item.badge && (
                  <span className="rounded-md bg-slate-100 dark:bg-slate-900 px-2 py-0.5 text-[11px] font-mono font-medium text-slate-400 dark:text-slate-500 border border-slate-200/60 dark:border-slate-800">
                    {item.badge}
                  </span>
                )}
              </div>
            )
          }

          return (
            <Link
              key={item.label}
              href={item.href}
              onClick={() => onSelectDocumentsRoot?.()}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex items-center rounded-xl text-[15px] font-medium transition-colors duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]",
                collapsed
                  ? "h-11 w-11 mx-auto justify-center"
                  : "h-11 px-3.5 justify-between",
                isActive
                  ? "bg-[#0A77FF]/10 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300 font-semibold"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-slate-100"
              )}
            >
              <div className="flex items-center gap-3.5 min-w-0">
                <Icon
                  className={cn(
                    "h-5 w-5 shrink-0 stroke-[1.8]",
                    isActive
                      ? "text-[#0A77FF] dark:text-sky-400"
                      : "text-slate-500 dark:text-slate-400"
                  )}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </div>
              {!collapsed && isActive && (
                <span className="h-2 w-2 rounded-full bg-[#0A77FF] dark:bg-sky-400" />
              )}
            </Link>
          )
        })}
      </nav>

      {/* Single Collapse / Expand Control */}
      <div className="p-3 border-t border-slate-200/70 dark:border-slate-800/70">
        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={
            collapsed ? "Expand navigation menu" : "Collapse navigation menu"
          }
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "w-full h-10 rounded-xl flex items-center text-sm font-medium text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-100 dark:hover:bg-slate-900 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]",
            collapsed ? "justify-center" : "px-3.5 gap-3"
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-5 w-5 stroke-[1.75]" />
          ) : (
            <>
              <PanelLeftClose className="h-5 w-5 stroke-[1.75]" />
              <span>Collapse sidebar</span>
            </>
          )}
        </button>
      </div>
    </aside>
  )
}
