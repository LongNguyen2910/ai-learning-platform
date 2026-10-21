import { AuthBrandPanel } from "@/components/auth/auth-brand-panel"

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <main className="min-h-screen w-full flex bg-white dark:bg-slate-950">
      {/* Brand panel on the left (visible on desktop) */}
      <AuthBrandPanel />

      {/* Form container on the right - clean, borderless surface */}
      <section className="flex-1 flex flex-col justify-center items-center px-6 sm:px-10 md:px-14 lg:px-16 py-12 overflow-y-auto">
        <div className="w-full max-w-[420px] mx-auto">
          {children}
        </div>
      </section>
    </main>
  )
}
