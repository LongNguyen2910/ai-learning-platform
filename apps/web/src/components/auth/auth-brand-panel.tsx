import { Sparkles, ArrowUpRight, Cpu } from "lucide-react"

export function AuthBrandPanel() {
  return (
    <div className="relative hidden w-full lg:flex lg:w-[48%] xl:w-[46%] flex-col justify-between overflow-hidden bg-gradient-to-br from-sky-600 via-blue-600 to-indigo-900 p-10 xl:p-14 text-white select-none">
      {/* 1. Ethereal Sky & Cyan Glow Ambient Lights */}
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute -top-40 -left-40 h-[520px] w-[520px] rounded-full bg-gradient-to-br from-cyan-400/35 via-sky-300/20 to-transparent blur-[130px]" 
      />
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute -bottom-40 -right-40 h-[560px] w-[560px] rounded-full bg-gradient-to-tl from-blue-700/40 via-indigo-900/35 to-transparent blur-[140px]" 
      />
      <div 
        aria-hidden="true" 
        className="pointer-events-none absolute top-1/2 left-1/3 -translate-y-1/2 h-[380px] w-[380px] rounded-full bg-sky-400/15 blur-[100px]" 
      />
      
      {/* Precision Geometric Grid Mesh */}
      <div 
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-[0.07]" 
        style={{
          backgroundImage: `linear-gradient(to right, #ffffff 1px, transparent 1px), linear-gradient(to bottom, #ffffff 1px, transparent 1px)`,
          backgroundSize: '40px 40px'
        }}
      />

      {/* 2. Header / Brand Identity with Frosted Glass Emblem */}
      <header className="relative z-10 flex items-center justify-between">
        <div className="flex items-center gap-3.5">
          {/* Double-bezel hardware emblem in frosted glass style */}
          <div className="p-1 rounded-2xl bg-white/10 ring-1 ring-white/25 shadow-[0_4px_20px_rgba(0,0,0,0.1)] backdrop-blur-md">
            <div className="h-10 w-10 rounded-[calc(1rem-4px)] bg-gradient-to-br from-white/30 via-white/15 to-transparent flex items-center justify-center ring-1 ring-white/40 shadow-[inset_0_1px_1px_rgba(255,255,255,0.6)]">
              <Sparkles className="h-5 w-5 text-white stroke-[1.75]" />
            </div>
          </div>
          <div>
            <span className="text-base font-semibold tracking-tight text-white block drop-shadow-sm">
              AI Learning Platform
            </span>
            <span className="text-[11px] font-mono tracking-wider uppercase text-sky-100/90 font-medium">
              Group 5
            </span>
          </div>
        </div>

        {/* Minimal pill status */}
        <div className="inline-flex items-center gap-2 rounded-full px-3 py-1 bg-white/15 ring-1 ring-white/25 text-[11px] font-mono text-white/95 backdrop-blur-md shadow-sm">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 animate-pulse shadow-[0_0_8px_rgba(110,231,183,0.8)]" />
          <span>v2.0</span>
        </div>
      </header>

      {/* 3. Centerpiece: High-Impact Typography & Frosted Glass Citation Card */}
      <div className="relative z-10 my-auto py-10 max-w-lg space-y-9">
        {/* Eyebrow & Hero Statement */}
        <div className="space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full px-3 py-1 bg-white/15 ring-1 ring-white/30 text-[11px] font-medium tracking-wide text-white backdrop-blur-md shadow-sm">
            <Cpu className="h-3.5 w-3.5 text-cyan-200 stroke-[1.75]" />
            <span>Best AI Tutoring</span>
          </div>

          <h1 className="text-4xl xl:text-5xl font-extrabold tracking-tight leading-[1.1] text-white drop-shadow-sm">
            Learn deeper.
            <br />
            <span className="bg-gradient-to-r from-cyan-100 via-sky-200 to-white bg-clip-text text-transparent">
              Stay curious.
            </span>
          </h1>

          <p className="text-sky-50/90 text-sm leading-relaxed max-w-md pt-1 drop-shadow-sm font-normal">
            Learn Smarter, Grow Faster with AI — Your Personal Path to Mastery.
          </p>
        </div>

        {/* High-End Double-Bezel Interactive Glass Card */}
        <div className="group rounded-[1.75rem] p-1.5 bg-white/15 ring-1 ring-white/30 shadow-[0_20px_50px_rgba(3,105,161,0.35),0_10px_20px_rgba(0,0,0,0.15)] backdrop-blur-2xl transition-all duration-700 ease-[cubic-bezier(0.32,0.72,0,1)] hover:ring-white/50 hover:bg-white/20">
          <div className="rounded-[calc(1.75rem-6px)] bg-slate-950/40 p-5 ring-1 ring-white/20 shadow-[inset_0_1px_2px_rgba(255,255,255,0.3)] backdrop-blur-xl space-y-4">
            {/* Top card bar with simulated document citation */}
            <div className="flex items-center justify-between pb-3 border-b border-white/15">
              <div className="flex items-center gap-2.5">
                <span className="h-2 w-2 rounded-full bg-cyan-300 shadow-[0_0_8px_rgba(103,232,249,0.9)]" />
                <span className="text-xs font-mono text-sky-100 font-medium tracking-tight">
                  Calculus_IV.pdf
                </span>
              </div>
              <span className="inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[10px] font-mono font-medium bg-white/15 text-white ring-1 ring-white/25 shadow-sm">
                p. 142
                <ArrowUpRight className="h-2.5 w-2.5 text-cyan-200" />
              </span>
            </div>

            {/* Socratic Hint quote */}
            <div className="space-y-1.5 pl-3 border-l-2 border-cyan-400">
              <span className="text-[11px] font-mono uppercase tracking-wider text-cyan-200 font-semibold block">
                Socratic Tier 1 • Guided Hint
              </span>
              <p className="text-xs text-white/95 font-sans leading-relaxed">
                &ldquo;Education is not the learning of facts, but the training of the mind to think.&rdquo;
              </p>
            </div>

            {/* Micro pill stats */}
            <div className="flex items-center gap-2 pt-1">
              <div className="h-1.5 flex-1 rounded-full bg-white/15 overflow-hidden ring-1 ring-white/10">
                <div className="h-full w-3/4 rounded-full bg-gradient-to-r from-cyan-300 to-sky-100 shadow-[0_0_10px_rgba(103,232,249,0.8)]" />
              </div>
              <span className="text-[10px] font-mono text-sky-100/90 font-medium">
                Retention 92%
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Elegant Minimal Footer */}
      <footer className="relative z-10 flex items-center justify-between text-xs text-sky-100/80 font-mono border-t border-white/15 pt-6">
        <span>© 2026 AI Learning Platform</span>
        <span className="text-sky-100/90 font-medium">Long is very tuat</span>
      </footer>
    </div>
  )
}
