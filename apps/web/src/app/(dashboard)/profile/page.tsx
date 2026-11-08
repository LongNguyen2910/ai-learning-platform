"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  ArrowLeft,
  Sparkles,
  Calendar,
  Clock,
  BookOpen,
  FileText,
  Network,
  CheckCircle2,
  Lock,
  Eye,
  EyeOff,
  Check,
  AlertCircle,
  Loader2,
  ShieldCheck,
  Pencil,
} from "lucide-react"
import {
  fetchUserProfile,
  updateUserProfile,
  uploadUserAvatar,
  changeUserPassword,
  resolveAvatarUrl,
  type UserProfileResponse,
} from "@/lib/api/profile"
import { fetchDocuments, type DocumentItem } from "@/lib/api/documents"
import { fetchSubjects, fetchRoadmaps, type SubjectItem, type RoadmapItem } from "@/lib/api/roadmaps"

export default function ProfilePage() {
  const router = useRouter()

  // Profile data & loading
  const [profile, setProfile] = React.useState<UserProfileResponse | null>(null)
  const [isLoadingProfile, setIsLoadingProfile] = React.useState(true)
  const [loadError, setLoadError] = React.useState<string | null>(null)

  // Avatar upload state
  const avatarInputRef = React.useRef<HTMLInputElement>(null)
  const [isUploadingAvatar, setIsUploadingAvatar] = React.useState(false)
  const [avatarErrorMsg, setAvatarErrorMsg] = React.useState<string | null>(null)

  // Learning stats
  const [documents, setDocuments] = React.useState<DocumentItem[]>([])
  const [subjects, setSubjects] = React.useState<SubjectItem[]>([])
  const [roadmaps, setRoadmaps] = React.useState<RoadmapItem[]>([])

  // Personal Info Form State
  const [fullName, setFullName] = React.useState("")
  const [isSavingProfile, setIsSavingProfile] = React.useState(false)
  const [profileSuccessMsg, setProfileSuccessMsg] = React.useState<string | null>(null)
  const [profileErrorMsg, setProfileErrorMsg] = React.useState<string | null>(null)

  // Password Form State
  const [currentPassword, setCurrentPassword] = React.useState("")
  const [newPassword, setNewPassword] = React.useState("")
  const [confirmPassword, setConfirmPassword] = React.useState("")
  const [showCurrentPass, setShowCurrentPass] = React.useState(false)
  const [showNewPass, setShowNewPass] = React.useState(false)
  const [showConfirmPass, setShowConfirmPass] = React.useState(false)
  const [isChangingPass, setIsChangingPass] = React.useState(false)
  const [passwordSuccessMsg, setPasswordSuccessMsg] = React.useState<string | null>(null)
  const [passwordErrorMsg, setPasswordErrorMsg] = React.useState<string | null>(null)

  // Initial Data Load
  React.useEffect(() => {
    let cancelled = false

    const loadData = async () => {
      setIsLoadingProfile(true)
      setLoadError(null)

      try {
        const [userRes, docsRes, subjsRes, rdmsRes] = await Promise.all([
          fetchUserProfile(),
          fetchDocuments().catch(() => []),
          fetchSubjects().catch(() => []),
          fetchRoadmaps().catch(() => []),
        ])

        if (!cancelled) {
          setProfile(userRes)
          setFullName(userRes.full_name || "")
          setDocuments(docsRes)
          setSubjects(subjsRes)
          setRoadmaps(rdmsRes)

          // Sync into localStorage
          localStorage.setItem("auth_user", JSON.stringify(userRes))
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(
            err instanceof Error ? err.message : "Failed to load profile data."
          )
        }
      } finally {
        if (!cancelled) {
          setIsLoadingProfile(false)
        }
      }
    }

    void loadData()
    return () => {
      cancelled = true
    }
  }, [])

  // Handle Avatar Upload
  const handleAvatarFileChange = async (
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return

    setAvatarErrorMsg(null)
    if (!file.type.startsWith("image/")) {
      setAvatarErrorMsg("Please select a valid image file (PNG, JPG, WEBP, GIF).")
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setAvatarErrorMsg("Image size must not exceed 5 MB.")
      return
    }

    setIsUploadingAvatar(true)
    try {
      const updated = await uploadUserAvatar(file)
      setProfile(updated)
      localStorage.setItem("auth_user", JSON.stringify(updated))
      window.dispatchEvent(new Event("auth-user-updated"))
    } catch (err) {
      setAvatarErrorMsg(
        err instanceof Error ? err.message : "Failed to upload avatar."
      )
    } finally {
      setIsUploadingAvatar(false)
    }
  }

  // Handle Update Profile Name
  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setProfileErrorMsg(null)
    setProfileSuccessMsg(null)

    const trimmed = fullName.trim()
    setIsSavingProfile(true)

    try {
      const updated = await updateUserProfile({ full_name: trimmed || null })
      setProfile(updated)
      setFullName(updated.full_name || "")
      localStorage.setItem("auth_user", JSON.stringify(updated))
      window.dispatchEvent(new Event("auth-user-updated"))
      setProfileSuccessMsg("Profile updated successfully.")
      setTimeout(() => setProfileSuccessMsg(null), 3000)
    } catch (err) {
      setProfileErrorMsg(
        err instanceof Error ? err.message : "Could not update profile name."
      )
    } finally {
      setIsSavingProfile(false)
    }
  }

  // Handle Change Password
  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordErrorMsg(null)
    setPasswordSuccessMsg(null)

    if (newPassword.length < 8) {
      setPasswordErrorMsg("New password must be at least 8 characters.")
      return
    }

    if (newPassword !== confirmPassword) {
      setPasswordErrorMsg("Confirmation password does not match.")
      return
    }

    if (currentPassword === newPassword) {
      setPasswordErrorMsg("New password must be different from current password.")
      return
    }

    setIsChangingPass(true)
    try {
      await changeUserPassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setPasswordSuccessMsg("Password changed successfully.")
      setCurrentPassword("")
      setNewPassword("")
      setConfirmPassword("")
      setTimeout(() => setPasswordSuccessMsg(null), 3500)
    } catch (err) {
      setPasswordErrorMsg(
        err instanceof Error ? err.message : "Failed to change password."
      )
    } finally {
      setIsChangingPass(false)
    }
  }

  // Token Metrics Calculation
  const dailyLimit = profile?.daily_token_limit || 50000
  const usedToday = profile?.used_token_today || 0
  const remainingTokens = Math.max(0, dailyLimit - usedToday)
  const quotaPercent = Math.min(100, Math.round((usedToday / dailyLimit) * 100))

  // Completed Roadmaps count
  const completedRoadmapsCount = React.useMemo(() => {
    return roadmaps.filter(
      (r) => r.status === "completed" || (r.progress_percentage || 0) >= 100
    ).length
  }, [roadmaps])

  const displayName = profile?.full_name?.trim() || profile?.email?.split("@")[0] || "User"
  const resolvedAvatarUrl = resolveAvatarUrl(profile?.avatar_url)
  const memberSince = profile?.created_at
    ? new Date(profile.created_at).toLocaleDateString("en-US", {
        month: "short",
        year: "numeric",
      })
    : "Recently"

  if (isLoadingProfile) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[500px] text-slate-400 gap-3">
        <Loader2 className="h-6 w-6 animate-spin text-[#0A77FF]" />
        <p className="text-xs font-medium">Loading account profile...</p>
      </div>
    )
  }

  if (loadError) {
    return (
      <div className="max-w-xl mx-auto mt-12 p-6 rounded-2xl border border-rose-200 dark:border-rose-900/60 bg-white dark:bg-slate-900 text-center space-y-4">
        <AlertCircle className="h-8 w-8 text-rose-500 mx-auto" />
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">
          Could not load profile
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400">{loadError}</p>
        <button
          type="button"
          onClick={() => router.push("/dashboard")}
          className="h-9 px-4 rounded-xl bg-slate-900 dark:bg-white text-white dark:text-slate-900 text-xs font-semibold cursor-pointer"
        >
          Return to Dashboard
        </button>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 bg-[#F8FAFC] dark:bg-slate-950">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Navigation Bar & Header */}
        <div className="space-y-3 border-b border-slate-200/80 dark:border-slate-800/80 pb-5">
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-2 text-xs font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors cursor-pointer group"
          >
            <ArrowLeft className="h-3.5 w-3.5 transition-transform group-hover:-translate-x-0.5" />
            <span>Back to Dashboard</span>
          </Link>

          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Account Profile
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 mt-0.5">
              Manage your personal credentials, AI generation quota, and learning statistics.
            </p>
          </div>
        </div>

        {/* Asymmetric Bento Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* LEFT COLUMN (4 cols): Identity Card & Daily AI Quota */}
          <div className="lg:col-span-4 space-y-5">
            {/* 1. Identity Card */}
            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-6 shadow-2xs space-y-5">
              <div className="flex items-center gap-4">
                <input
                  ref={avatarInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  onChange={handleAvatarFileChange}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => avatarInputRef.current?.click()}
                  disabled={isUploadingAvatar}
                  title="Upload new profile picture"
                  aria-label="Upload new profile picture"
                  className="group relative h-16 w-16 rounded-2xl bg-[#0A77FF] text-white flex items-center justify-center font-bold text-2xl shadow-xs shrink-0 select-none overflow-hidden cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] focus-visible:ring-offset-2"
                >
                  {resolvedAvatarUrl ? (
                    <img
                      src={resolvedAvatarUrl}
                      alt={displayName}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <span>{displayName.charAt(0).toUpperCase()}</span>
                  )}

                  {/* Pencil Hover Overlay */}
                  <div
                    className={`absolute inset-0 bg-slate-900/55 backdrop-blur-[1px] flex items-center justify-center transition-opacity duration-150 ${
                      isUploadingAvatar
                        ? "opacity-100"
                        : "opacity-0 group-hover:opacity-100"
                    }`}
                  >
                    {isUploadingAvatar ? (
                      <Loader2 className="h-5 w-5 text-white animate-spin" />
                    ) : (
                      <Pencil className="h-5 w-5 text-white stroke-[2]" />
                    )}
                  </div>
                </button>

                <div className="min-w-0 flex-1">
                  <h2 className="text-base font-bold text-slate-900 dark:text-white truncate">
                    {displayName}
                  </h2>
                  <p className="text-xs text-slate-400 dark:text-slate-500 truncate mt-0.5">
                    {profile?.email}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-slate-600 dark:text-slate-300 border border-slate-200/60 dark:border-slate-700">
                      {profile?.role || "Member"}
                    </span>
                    <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                    <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      Active
                    </span>
                  </div>
                </div>
              </div>

              {avatarErrorMsg && (
                <div className="rounded-lg border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-3 py-2 text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2">
                  <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                  <span>{avatarErrorMsg}</span>
                </div>
              )}

              <div className="pt-4 border-t border-slate-100 dark:border-slate-800/80 text-xs text-slate-500 dark:text-slate-400 flex items-center gap-2">
                <Calendar className="h-4 w-4 text-slate-400 shrink-0" />
                <span>Member since {memberSince}</span>
              </div>
            </div>

            {/* 2. Daily AI Token Quota Card */}
            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-6 shadow-2xs space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-7 w-7 rounded-lg bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 text-[#0A77FF] dark:text-sky-400 flex items-center justify-center">
                    <Sparkles className="h-3.5 w-3.5 stroke-[2]" />
                  </div>
                  <h3 className="text-xs font-semibold text-slate-900 dark:text-white">
                    Daily AI Quota
                  </h3>
                </div>
                <span className="text-xs font-mono font-semibold text-slate-700 dark:text-slate-300 tabular-nums">
                  {quotaPercent}%
                </span>
              </div>

              {/* Progress Bar */}
              <div className="space-y-1.5">
                <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <div
                    style={{ width: `${quotaPercent}%` }}
                    className={`h-full transition-all duration-300 ${
                      quotaPercent > 90
                        ? "bg-rose-500"
                        : quotaPercent > 70
                        ? "bg-amber-500"
                        : "bg-[#0A77FF]"
                    }`}
                  />
                </div>
                <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 dark:text-slate-500 tabular-nums">
                  <span>{usedToday.toLocaleString()} used</span>
                  <span>{dailyLimit.toLocaleString()} limit</span>
                </div>
              </div>

              {/* Quota Telemetry Details */}
              <div className="rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200/60 dark:border-slate-800/80 p-3 space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500 dark:text-slate-400">Tokens Remaining</span>
                  <span className="font-mono font-semibold text-slate-800 dark:text-slate-200 tabular-nums">
                    {remainingTokens.toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between pt-1 border-t border-slate-200/40 dark:border-slate-800/60 text-[11px] text-slate-400">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    <span>Quota Cycle</span>
                  </span>
                  <span>Resets at 00:00 UTC</span>
                </div>
              </div>
            </div>
          </div>

          {/* RIGHT COLUMN (8 cols): Learning Snapshot & Forms */}
          <div className="lg:col-span-8 space-y-6">
            {/* 3. Learning Telemetry 4-KPI Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 shadow-2xs">
                <div className="flex items-center gap-2 text-slate-400 text-xs">
                  <BookOpen className="h-4 w-4 text-[#0A77FF]" />
                  <span>Subjects</span>
                </div>
                <p className="mt-2 text-xl font-bold font-mono text-slate-900 dark:text-white tabular-nums">
                  {subjects.length}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">Enrolled courses</p>
              </div>

              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 shadow-2xs">
                <div className="flex items-center gap-2 text-slate-400 text-xs">
                  <FileText className="h-4 w-4 text-[#0A77FF]" />
                  <span>Documents</span>
                </div>
                <p className="mt-2 text-xl font-bold font-mono text-slate-900 dark:text-white tabular-nums">
                  {documents.length}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">Uploaded books & slides</p>
              </div>

              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 shadow-2xs">
                <div className="flex items-center gap-2 text-slate-400 text-xs">
                  <Network className="h-4 w-4 text-[#0A77FF]" />
                  <span>Roadmaps</span>
                </div>
                <p className="mt-2 text-xl font-bold font-mono text-slate-900 dark:text-white tabular-nums">
                  {roadmaps.length}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">Active curriculum plans</p>
              </div>

              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-4 shadow-2xs">
                <div className="flex items-center gap-2 text-slate-400 text-xs">
                  <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  <span>Completed</span>
                </div>
                <p className="mt-2 text-xl font-bold font-mono text-slate-900 dark:text-white tabular-nums">
                  {completedRoadmapsCount}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">Completed roadmaps</p>
              </div>
            </div>

            {/* 4. Personal Information Form */}
            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-6 shadow-2xs space-y-5">
              <div>
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                  Personal Information
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Update your display name across roadmaps, quizzes, and AI tutor sessions.
                </p>
              </div>

              <form onSubmit={handleUpdateProfile} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* Full Name Input */}
                  <div className="space-y-1.5">
                    <label
                      htmlFor="profile-fullname"
                      className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                    >
                      Full Name
                    </label>
                    <input
                      id="profile-fullname"
                      type="text"
                      maxLength={100}
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="e.g. John Doe"
                      className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                    />
                  </div>

                  {/* Email Read-only */}
                  <div className="space-y-1.5">
                    <label
                      htmlFor="profile-email"
                      className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                    >
                      Email Address
                    </label>
                    <div className="relative">
                      <input
                        id="profile-email"
                        type="email"
                        disabled
                        value={profile?.email || ""}
                        className="w-full h-9 rounded-lg border border-slate-200/60 dark:border-slate-800/60 bg-slate-100/70 dark:bg-slate-900/60 px-3 text-xs text-slate-500 dark:text-slate-400 cursor-not-allowed select-none pr-20"
                      />
                      <span className="absolute right-2.5 top-2 inline-flex items-center gap-1 rounded bg-emerald-500/10 dark:bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                        <ShieldCheck className="h-3 w-3" />
                        <span>Verified</span>
                      </span>
                    </div>
                  </div>
                </div>

                {profileErrorMsg && (
                  <div className="rounded-lg border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-3 py-2 text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                    <span>{profileErrorMsg}</span>
                  </div>
                )}

                {profileSuccessMsg && (
                  <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/80 dark:bg-emerald-950/40 px-3 py-2 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                    <Check className="h-4 w-4 shrink-0" />
                    <span>{profileSuccessMsg}</span>
                  </div>
                )}

                <div className="flex justify-end pt-1">
                  <button
                    type="submit"
                    disabled={isSavingProfile}
                    className="h-9 px-4 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] disabled:opacity-50 text-white text-xs font-semibold inline-flex items-center gap-1.5 transition-all cursor-pointer active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                  >
                    {isSavingProfile ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Saving...</span>
                      </>
                    ) : (
                      <>
                        <Check className="h-3.5 w-3.5 stroke-[2.2]" />
                        <span>Save Changes</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>

            {/* 5. Security & Password Form */}
            <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-6 shadow-2xs space-y-5">
              <div>
                <div className="flex items-center gap-2">
                  <Lock className="h-4 w-4 text-slate-700 dark:text-slate-300 stroke-[1.8]" />
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                    Security & Password
                  </h3>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Ensure your account is protected with a secure password of at least 8 characters.
                </p>
              </div>

              <form onSubmit={handleChangePassword} className="space-y-4">
                {/* Current Password */}
                <div className="space-y-1.5">
                  <label
                    htmlFor="current-password"
                    className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                  >
                    Current Password
                  </label>
                  <div className="relative">
                    <input
                      id="current-password"
                      type={showCurrentPass ? "text" : "password"}
                      required
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      placeholder="Enter your current password"
                      className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 pr-10 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                    />
                    <button
                      type="button"
                      onClick={() => setShowCurrentPass((prev) => !prev)}
                      aria-label={showCurrentPass ? "Hide current password" : "Show current password"}
                      className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors cursor-pointer"
                    >
                      {showCurrentPass ? (
                        <EyeOff className="h-4 w-4 stroke-[1.75]" />
                      ) : (
                        <Eye className="h-4 w-4 stroke-[1.75]" />
                      )}
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {/* New Password */}
                  <div className="space-y-1.5">
                    <label
                      htmlFor="new-password"
                      className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                    >
                      New Password
                    </label>
                    <div className="relative">
                      <input
                        id="new-password"
                        type={showNewPass ? "text" : "password"}
                        required
                        minLength={8}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="At least 8 characters"
                        className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 pr-10 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                      />
                      <button
                        type="button"
                        onClick={() => setShowNewPass((prev) => !prev)}
                        aria-label={showNewPass ? "Hide new password" : "Show new password"}
                        className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors cursor-pointer"
                      >
                        {showNewPass ? (
                          <EyeOff className="h-4 w-4 stroke-[1.75]" />
                        ) : (
                          <Eye className="h-4 w-4 stroke-[1.75]" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Confirm Password */}
                  <div className="space-y-1.5">
                    <label
                      htmlFor="confirm-password"
                      className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                    >
                      Confirm New Password
                    </label>
                    <div className="relative">
                      <input
                        id="confirm-password"
                        type={showConfirmPass ? "text" : "password"}
                        required
                        minLength={8}
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="Re-enter new password"
                        className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 pr-10 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                      />
                      <button
                        type="button"
                        onClick={() => setShowConfirmPass((prev) => !prev)}
                        aria-label={showConfirmPass ? "Hide confirm password" : "Show confirm password"}
                        className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors cursor-pointer"
                      >
                        {showConfirmPass ? (
                          <EyeOff className="h-4 w-4 stroke-[1.75]" />
                        ) : (
                          <Eye className="h-4 w-4 stroke-[1.75]" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>

                {passwordErrorMsg && (
                  <div className="rounded-lg border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-3 py-2 text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2">
                    <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                    <span>{passwordErrorMsg}</span>
                  </div>
                )}

                {passwordSuccessMsg && (
                  <div className="rounded-lg border border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/80 dark:bg-emerald-950/40 px-3 py-2 text-xs text-emerald-600 dark:text-emerald-400 flex items-center gap-2">
                    <Check className="h-4 w-4 shrink-0" />
                    <span>{passwordSuccessMsg}</span>
                  </div>
                )}

                <div className="flex justify-end pt-1">
                  <button
                    type="submit"
                    disabled={isChangingPass || !currentPassword || !newPassword || !confirmPassword}
                    className="h-9 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 dark:bg-white dark:hover:bg-slate-100 dark:text-slate-900 text-white disabled:opacity-50 text-xs font-semibold inline-flex items-center gap-1.5 transition-all cursor-pointer active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400"
                  >
                    {isChangingPass ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Updating Password...</span>
                      </>
                    ) : (
                      <>
                        <Lock className="h-3.5 w-3.5 stroke-[2]" />
                        <span>Update Password</span>
                      </>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
