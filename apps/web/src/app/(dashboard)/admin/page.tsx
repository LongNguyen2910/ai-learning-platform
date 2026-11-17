"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { ArrowLeft } from "lucide-react"
import { AdminUsersWorkspace } from "@/components/dashboard/admin-users-workspace"
import { getAuthToken } from "@/lib/api/documents"

export default function AdminUsersPage() {
  const router = useRouter()

  React.useEffect(() => {
    if (!getAuthToken()) {
      router.replace("/login")
    }
  }, [router])

  return (
    <div className="h-screen w-full overflow-hidden flex flex-col bg-[#F8FAFC] dark:bg-slate-950">
      <header className="h-14 w-full border-b border-slate-200/80 dark:border-slate-800/80 bg-white/95 dark:bg-slate-950/95 backdrop-blur-sm px-6 flex items-center justify-between shrink-0">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 text-xs font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors cursor-pointer group"
        >
          <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
          <span>Back to Dashboard</span>
        </Link>

        <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 dark:text-slate-500">
          AI Learning · Administration
        </span>
      </header>

      <AdminUsersWorkspace />
    </div>
  )
}
