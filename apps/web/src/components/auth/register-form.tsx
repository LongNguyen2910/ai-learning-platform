"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { registerSchema, type RegisterInput } from "@/lib/validations/auth"
import { Label } from "@/components/ui/label"
import { AlertCircle, CheckCircle2, Eye, EyeOff, Loader2 } from "lucide-react"

export function RegisterForm() {
  const router = useRouter()
  const [formData, setFormData] = React.useState<RegisterInput>({
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    confirm_password: "",
  })
  const [showPassword, setShowPassword] = React.useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = React.useState(false)
  const [errors, setErrors] = React.useState<Partial<Record<keyof RegisterInput, string>>>({})
  const [serverError, setServerError] = React.useState<string | null>(null)
  const [isSuccess, setIsSuccess] = React.useState(false)
  const [isLoading, setIsLoading] = React.useState(false)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData((prev) => ({ ...prev, [name]: value }))
    if (errors[name as keyof RegisterInput]) {
      setErrors((prev) => ({ ...prev, [name]: undefined }))
    }
    if (serverError) setServerError(null)
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setServerError(null)

    const result = registerSchema.safeParse(formData)
    if (!result.success) {
      const fieldErrors: Partial<Record<keyof RegisterInput, string>> = {}
      result.error.issues.forEach((issue) => {
        const fieldName = issue.path[0] as keyof RegisterInput
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
      const payload = {
        email: formData.email,
        password: formData.password,
        full_name: `${formData.first_name.trim()} ${formData.last_name.trim()}`.trim(),
      }

      const response = await fetch(`${apiUrl}/auth/register`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      })

      if (!response.ok) {
        const data = await response.json().catch(() => null)
        const message =
          response.status === 409
            ? "An account with this email address already exists."
            : data?.detail || data?.message || "Registration failed. Please check your data."
        setServerError(message)
        setIsLoading(false)
        return
      }

      setIsSuccess(true)
      setIsLoading(false)

      setTimeout(() => {
        router.push("/login?registered=true")
      }, 1500)
    } catch {
      setServerError("Unable to connect to authentication server. Please check your network or try again.")
      setIsLoading(false)
    }
  }

  const inputBaseClass =
    "h-12 w-full rounded-xl bg-[#F1F4F8] dark:bg-slate-900 px-4 text-sm text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500 border border-transparent focus:border-blue-500/40 focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:ring-4 focus:ring-blue-500/10 transition-all duration-200 disabled:opacity-50 aria-invalid:border-destructive/60 aria-invalid:ring-4 aria-invalid:ring-destructive/10"

  if (isSuccess) {
    return (
      <div className="w-full py-12 text-center animate-in fade-in-50 duration-300 space-y-4">
        <div className="mx-auto h-12 w-12 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center ring-8 ring-emerald-500/5">
          <CheckCircle2 className="h-6 w-6" />
        </div>
        <div className="space-y-1">
          <h3 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">
            Registration Successful!
          </h3>
          <p className="text-sm text-slate-400 max-w-xs mx-auto">
            Your account has been created. Redirecting you to the sign-in screen...
          </p>
        </div>
        <Loader2 className="h-4 w-4 animate-spin text-[#0A77FF] mx-auto mt-2" />
      </div>
    )
  }

  return (
    <div className="w-full space-y-7 animate-in fade-in-0 duration-300">
      <div className="space-y-2">
        <h1 className="text-[28px] font-bold tracking-tight text-slate-900 dark:text-white leading-tight">
          Create your account
        </h1>
        <p className="text-[15px] text-slate-400 dark:text-slate-400">
          Set up your account in under a minute.
        </p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        {serverError && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-xl bg-destructive/10 p-3.5 text-xs text-destructive dark:text-red-400"
          >
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <div className="leading-relaxed font-medium">{serverError}</div>
          </div>
        )}

        {/* First name & Last name 2-column row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          <div className="space-y-2">
            <Label htmlFor="first_name" className="text-[14px] font-medium text-slate-800 dark:text-slate-200">
              First name
            </Label>
            <input
              id="first_name"
              name="first_name"
              type="text"
              autoComplete="given-name"
              required
              disabled={isLoading}
              placeholder="First name"
              value={formData.first_name}
              onChange={handleChange}
              aria-invalid={!!errors.first_name}
              aria-describedby={errors.first_name ? "first-name-error" : undefined}
              className={inputBaseClass}
            />
            {errors.first_name && (
              <p id="first-name-error" role="alert" className="text-xs text-destructive font-medium mt-1">
                {errors.first_name}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="last_name" className="text-[14px] font-medium text-slate-800 dark:text-slate-200">
              Last name
            </Label>
            <input
              id="last_name"
              name="last_name"
              type="text"
              autoComplete="family-name"
              required
              disabled={isLoading}
              placeholder="Last name"
              value={formData.last_name}
              onChange={handleChange}
              aria-invalid={!!errors.last_name}
              aria-describedby={errors.last_name ? "last-name-error" : undefined}
              className={inputBaseClass}
            />
            {errors.last_name && (
              <p id="last-name-error" role="alert" className="text-xs text-destructive font-medium mt-1">
                {errors.last_name}
              </p>
            )}
          </div>
        </div>

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
              autoComplete="new-password"
              required
              disabled={isLoading}
              placeholder="Create a password"
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
              {showPassword ? <EyeOff className="h-5 w-5 stroke-[1.75]" /> : <Eye className="h-5 w-5 stroke-[1.75]" />}
            </button>
          </div>
          {errors.password && (
            <p id="password-error" role="alert" className="text-xs text-destructive font-medium mt-1">
              {errors.password}
            </p>
          )}
        </div>

        {/* Confirm password field */}
        <div className="space-y-2">
          <Label htmlFor="confirm_password" className="text-[14px] font-medium text-slate-800 dark:text-slate-200">
            Confirm password
          </Label>
          <div className="relative">
            <input
              id="confirm_password"
              name="confirm_password"
              type={showConfirmPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              disabled={isLoading}
              placeholder="Re-enter password"
              value={formData.confirm_password}
              onChange={handleChange}
              aria-invalid={!!errors.confirm_password}
              aria-describedby={errors.confirm_password ? "confirm-error" : undefined}
              className={`${inputBaseClass} pr-11`}
            />
            <button
              type="button"
              onClick={() => setShowConfirmPassword((prev) => !prev)}
              aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 transition-colors cursor-pointer"
            >
              {showConfirmPassword ? <EyeOff className="h-5 w-5 stroke-[1.75]" /> : <Eye className="h-5 w-5 stroke-[1.75]" />}
            </button>
          </div>
          {errors.confirm_password && (
            <p id="confirm-error" role="alert" className="text-xs text-destructive font-medium mt-1">
              {errors.confirm_password}
            </p>
          )}
        </div>

        {/* Helper caption */}
        <p className="text-center text-[13px] text-slate-400 pt-1">
          Join students in 187 countries · Set up in under 2 minutes
        </p>

        {/* Submit CTA */}
        <div className="pt-1">
          <button
            type="submit"
            disabled={isLoading}
            className="w-full h-12 rounded-xl bg-[#0A77FF] hover:bg-[#0066E6] active:scale-[0.99] text-white text-[15px] font-semibold shadow-[0_8px_20px_-4px_rgba(10,119,255,0.45)] transition-all duration-200 flex items-center justify-center cursor-pointer disabled:opacity-60 disabled:pointer-events-none"
          >
            {isLoading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Creating account...
              </>
            ) : (
              "Create my account"
            )}
          </button>
        </div>

        {/* Bottom link */}
        <div className="text-center text-[14px] text-slate-400 pt-3">
          Already have an account?{" "}
          <Link
            href="/login"
            className="font-semibold text-[#0A77FF] hover:underline underline-offset-4"
          >
            Sign in
          </Link>
        </div>
      </form>
    </div>
  )
}
