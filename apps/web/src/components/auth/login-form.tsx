"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { loginSchema, type LoginInput } from "@/lib/validations/auth"
import { Label } from "@/components/ui/label"
import { AlertCircle, Eye, EyeOff, Loader2 } from "lucide-react"

export function LoginForm() {
  const router = useRouter()
  const [formData, setFormData] = React.useState<LoginInput>({
    email: "",
    password: "",
  })
  const [keepSignedIn, setKeepSignedIn] = React.useState(false)
  const [showPassword, setShowPassword] = React.useState(false)
  const [errors, setErrors] = React.useState<Partial<Record<keyof LoginInput, string>>>({})
  const [serverError, setServerError] = React.useState<string | null>(null)
  const [isLoading, setIsLoading] = React.useState(false)

  // Ensure loading state is always reset when returning to /login (e.g. after logout or BFCache restore)
  React.useEffect(() => {
    setIsLoading(false)
    setServerError(null)
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
    if (errors[name as keyof LoginInput]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }))
    }
    if (serverError) setServerError(null)
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setServerError(null)

    const result = loginSchema.safeParse(formData)
    if (!result.success) {
      const fieldErrors: Partial<Record<keyof LoginInput, string>> = {}
      result.error.issues.forEach((issue) => {
        const fieldName = issue.path[0] as keyof LoginInput
        if (!fieldErrors[fieldName]) {
          fieldErrors[fieldName] = issue.message
        }
      })
      setErrors(fieldErrors)
      return
    }

    setErrors({})
    setIsLoading(true)

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"
      const response = await fetch(`${apiUrl}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => null)
        const message = data?.detail || data?.message || "Invalid email or password. Please try again."
        setServerError(message)
        setIsLoading(false)
        return
      }

      const data = await response.json()
      if (data?.access_token) {
        localStorage.setItem("auth_token", data.access_token)
      }
      if (data?.user) {
        localStorage.setItem("auth_user", JSON.stringify(data.user))
      }

      setIsLoading(false)
      setFormData((prev) => ({ ...prev, password: "" }))
      router.replace("/dashboard")
    } catch {
      setServerError("Unable to connect to authentication server. Please check your network or try again.")
      setIsLoading(false)
    }
  }

  const inputBaseClass =
    "h-12 w-full rounded-xl bg-[#F1F4F8] dark:bg-slate-900 px-4 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 border border-transparent focus:border-blue-500/40 focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:ring-4 focus:ring-blue-500/10 transition-all duration-200 disabled:opacity-50 aria-invalid:border-destructive/60 aria-invalid:ring-4 aria-invalid:ring-destructive/10"

  return (
    <div className="w-full space-y-7 animate-in fade-in-0 duration-300">
      <div className="space-y-2">
        <h1 className="text-[28px] font-bold tracking-tight text-slate-900 dark:text-white leading-tight">
          Welcome back
        </h1>
        <p className="text-[15px] text-slate-400 dark:text-slate-400">
          Sign in to continue your learning journey.
        </p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        {serverError && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-xl bg-destructive/10 p-3.5 text-xs text-destructive dark:text-red-400"
          >
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <div className="leading-relaxed font-medium">{serverError}</div>
          </div>
        )}

        {/* Email field */}
        <div className="space-y-2">
          <Label htmlFor="email" className="text-[14px] font-medium text-slate-800 dark:text-slate-200">
            Email
          </Label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            disabled={isLoading}
            placeholder="you@school.edu"
            value={formData.email}
            onChange={handleChange}
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? "email-error" : undefined}
            className={inputBaseClass}
          />
          {errors.email && (
            <p id="email-error" role="alert" className="text-xs text-destructive font-medium mt-1">
              {errors.email}
            </p>
          )}
        </div>

        {/* Password field */}
        <div className="space-y-2">
          <Label htmlFor="password" className="text-[14px] font-medium text-slate-800 dark:text-slate-200">
            Password
          </Label>
          <div className="relative">
            <input
              id="password"
              name="password"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              disabled={isLoading}
              placeholder="Enter your password"
              value={formData.password}
              onChange={handleChange}
              aria-invalid={!!errors.password}
              aria-describedby={errors.password ? "password-error" : undefined}
              className={`${inputBaseClass} pr-11`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              aria-label={showPassword ? "Hide password" : "Show password"}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors cursor-pointer"
            >
              {showPassword ? <Eye className="h-5 w-5 stroke-[1.75]" /> : <EyeOff className="h-5 w-5 stroke-[1.75]" />}
            </button>
          </div>
          {errors.password && (
            <p id="password-error" role="alert" className="text-xs text-destructive font-medium mt-1">
              {errors.password}
            </p>
          )}
        </div>

        {/* Keep me signed in & Forgot password row */}
        <div className="flex items-center justify-between pt-0.5">
          <label className="inline-flex items-center gap-2.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={keepSignedIn}
              onChange={(e) => setKeepSignedIn(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-[#0A77FF] focus:ring-[#0A77FF]/30 cursor-pointer"
            />
            <span className="text-[14px] text-slate-500 dark:text-slate-400">
              Keep me signed in
            </span>
          </label>

          <Link
            href="/login"
            className="text-[14px] font-semibold text-[#0A77FF] hover:text-[#0062CC] transition-colors"
          >
            Forgot password?
          </Link>
        </div>

        {/* Submit CTA */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={isLoading}
            className="w-full h-12 rounded-xl bg-[#0A77FF] hover:bg-[#0066E6] active:scale-[0.99] text-white text-[15px] font-semibold shadow-[0_8px_20px_-4px_rgba(10,119,255,0.45)] transition-all duration-200 flex items-center justify-center cursor-pointer disabled:opacity-60 disabled:pointer-events-none"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Signing in...
              </>
            ) : (
              "Continue"
            )}
          </button>
        </div>

        {/* Bottom link */}
        <div className="text-center text-[14px] text-slate-400 pt-3">
          Don&apos;t have an account?{" "}
          <Link
            href="/register"
            className="font-semibold text-[#0A77FF] hover:underline underline-offset-4"
          >
            Sign up
          </Link>
        </div>
      </form>
    </div>
  )
}
