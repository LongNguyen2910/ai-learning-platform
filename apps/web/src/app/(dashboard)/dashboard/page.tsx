import type { Metadata } from "next"
import { DashboardWorkspace } from "@/components/dashboard/dashboard-workspace"

export const metadata: Metadata = {
  title: "My Workspace | AI Learning Platform",
  description:
    "Upload study documents, view PDFs, and learn with Socratic AI Split-View.",
}

export default function DashboardPage() {
  return <DashboardWorkspace />
}
