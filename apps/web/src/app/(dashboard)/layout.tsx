import { PomodoroWidget } from "@/components/dashboard/pomodoro-widget"

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <>
      {children}
      <PomodoroWidget />
    </>
  )
}
