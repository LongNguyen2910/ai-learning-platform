"use client"

import * as React from "react"
import {
  Timer,
  Play,
  Pause,
  RotateCcw,
  X,
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Flame,
  Zap,
  Coffee,
  ShieldCheck,
  History,
  BookOpen,
  Trash2,
  Save,
  Loader2,
  ChevronDown,
  Check,
} from "lucide-react"
import { loadLearningPreferences } from "@/lib/api/settings"
import { fetchSubjects, type SubjectItem } from "@/lib/api/roadmaps"
import {
  createStudySession,
  getStudySessions,
  deleteStudySession,
} from "@/lib/api/study-sessions"
import type { StudySessionItem } from "@/types/study-session"

export type PomodoroModeId = "pomodoro" | "deep_work" | "break"

export type TimerStatus =
  | "idle"
  | "running"
  | "paused_manual"
  | "paused_tab_switch"
  | "paused_checkin"
  | "completed"

export type ScreenCorner =
  | "bottom-right"
  | "bottom-left"
  | "top-right"
  | "top-left"

interface PomodoroPreset {
  id: PomodoroModeId
  label: string
  shortLabel: string
  minutes: number
}

const POMODORO_PRESETS: PomodoroPreset[] = [
  {
    id: "pomodoro",
    label: "Pomodoro (25m)",
    shortLabel: "25m Focus",
    minutes: 25,
  },
  {
    id: "deep_work",
    label: "Deep Work (50m)",
    shortLabel: "50m Deep",
    minutes: 50,
  },
  {
    id: "break",
    label: "Giải lao (5m)",
    shortLabel: "5m Break",
    minutes: 5,
  },
]

// Cứ mỗi 2 phút (120 giây) học tập thực tế sẽ dừng đồng hồ và yêu cầu xác nhận
const CHECKIN_INTERVAL_SECONDS = 120
const CORNER_STORAGE_KEY = "luminal_pomodoro_corner"
const ORB_SIZE = 52 // 52px hình tròn gọn gàng
const EDGE_OFFSET = 20 // Khoảng cách từ mép màn hình (20px)

function computeCornerCoords(
  corner: ScreenCorner,
  vw: number,
  vh: number
): { x: number; y: number } {
  const rightX = Math.max(EDGE_OFFSET, vw - ORB_SIZE - EDGE_OFFSET)
  const bottomY = Math.max(EDGE_OFFSET, vh - ORB_SIZE - EDGE_OFFSET)
  switch (corner) {
    case "top-left":
      return { x: EDGE_OFFSET, y: EDGE_OFFSET }
    case "top-right":
      return { x: rightX, y: EDGE_OFFSET }
    case "bottom-left":
      return { x: EDGE_OFFSET, y: bottomY }
    case "bottom-right":
    default:
      return { x: rightX, y: bottomY }
  }
}

interface PomodoroState {
  isExpanded: boolean
  modeId: PomodoroModeId
  totalSeconds: number
  remainingSeconds: number
  status: TimerStatus
  activeCheckinSeconds: number
  tabSwitchTime: string | null
  tabSwitchCount: number
}

type PomodoroAction =
  | { type: "INIT_FROM_PREFS"; modeId: PomodoroModeId; durationSeconds: number }
  | { type: "SET_EXPANDED"; isExpanded: boolean }
  | { type: "TOGGLE_EXPANDED" }
  | { type: "SELECT_MODE"; modeId: PomodoroModeId; durationSeconds: number }
  | { type: "START_OR_RESUME" }
  | { type: "PAUSE_MANUAL" }
  | { type: "RESET" }
  | { type: "TAB_SWITCH"; timestamp: string }
  | { type: "TICK" }

const INITIAL_STATE: PomodoroState = {
  isExpanded: false,
  modeId: "pomodoro",
  totalSeconds: 25 * 60,
  remainingSeconds: 25 * 60,
  status: "idle",
  activeCheckinSeconds: 0,
  tabSwitchTime: null,
  tabSwitchCount: 0,
}

function pomodoroReducer(
  state: PomodoroState,
  action: PomodoroAction
): PomodoroState {
  switch (action.type) {
    case "INIT_FROM_PREFS":
      return {
        ...state,
        modeId: action.modeId,
        totalSeconds: action.durationSeconds,
        remainingSeconds: action.durationSeconds,
      }

    case "SET_EXPANDED":
      return {
        ...state,
        isExpanded: action.isExpanded,
      }

    case "TOGGLE_EXPANDED":
      return {
        ...state,
        isExpanded: !state.isExpanded,
      }

    case "SELECT_MODE":
      return {
        ...state,
        modeId: action.modeId,
        totalSeconds: action.durationSeconds,
        remainingSeconds: action.durationSeconds,
        status: "idle",
        activeCheckinSeconds: 0,
        tabSwitchTime: null,
      }

    case "START_OR_RESUME": {
      const nextRemaining =
        state.remainingSeconds <= 0 ? state.totalSeconds : state.remainingSeconds
      const nextCheckin =
        state.status === "paused_checkin" || state.status === "completed"
          ? 0
          : state.activeCheckinSeconds
      return {
        ...state,
        remainingSeconds: nextRemaining,
        activeCheckinSeconds: nextCheckin,
        status: "running",
      }
    }

    case "PAUSE_MANUAL":
      if (state.status !== "running") return state
      return {
        ...state,
        status: "paused_manual",
      }

    case "RESET":
      return {
        ...state,
        status: "idle",
        remainingSeconds: state.totalSeconds,
        activeCheckinSeconds: 0,
        tabSwitchTime: null,
        tabSwitchCount: 0,
      }

    case "TAB_SWITCH":
      if (state.status !== "running" || state.modeId === "break") return state
      return {
        ...state,
        status: "paused_tab_switch",
        tabSwitchTime: action.timestamp,
        tabSwitchCount: state.tabSwitchCount + 1,
        isExpanded: true,
      }

    case "TICK": {
      if (state.status !== "running") return state

      if (state.remainingSeconds <= 1) {
        return {
          ...state,
          remainingSeconds: 0,
          activeCheckinSeconds: 0,
          status: "completed",
          isExpanded: true,
        }
      }

      const nextRemaining = state.remainingSeconds - 1

      // Điểm danh mỗi 2 phút (120s) đối với các chế độ tập trung (trừ giải lao)
      if (state.modeId !== "break") {
        const nextCheckin = state.activeCheckinSeconds + 1
        if (nextCheckin >= CHECKIN_INTERVAL_SECONDS) {
          return {
            ...state,
            remainingSeconds: nextRemaining,
            activeCheckinSeconds: 0,
            status: "paused_checkin",
            isExpanded: true,
          }
        }
        return {
          ...state,
          remainingSeconds: nextRemaining,
          activeCheckinSeconds: nextCheckin,
        }
      }

      return {
        ...state,
        remainingSeconds: nextRemaining,
      }
    }

    default:
      return state
  }
}

function formatCountdown(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds))
  const mins = Math.floor(safe / 60)
  const secs = safe % 60
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
}

function formatCurrentTime(): string {
  const now = new Date()
  return now.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
}

function formatSessionDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      day: "2-digit",
      month: "2-digit",
    })
  } catch {
    return ""
  }
}

export function PomodoroWidget() {
  const [state, dispatch] = React.useReducer(pomodoroReducer, INITIAL_STATE)
  const {
    isExpanded,
    modeId,
    totalSeconds,
    remainingSeconds,
    status,
    activeCheckinSeconds,
    tabSwitchTime,
    tabSwitchCount,
  } = state

  // Vị trí góc màn hình (4 góc), kích thước viewport & trạng thái kéo thả mượt bằng translate3d
  const [corner, setCorner] = React.useState<ScreenCorner>("bottom-right")
  const [viewport, setViewport] = React.useState<{ w: number; h: number } | null>(
    null
  )
  const [dragPos, setDragPos] = React.useState<{ x: number; y: number } | null>(
    null
  )
  const dragRef = React.useRef<{
    pointerId: number
    startX: number
    startY: number
    originLeft: number
    originTop: number
    lastX: number
    lastY: number
    moved: boolean
  } | null>(null)

  // Tích hợp API Study Sessions (/api/v1/study-sessions)
  const [subjects, setSubjects] = React.useState<SubjectItem[]>([])
  const [selectedSubjectId, setSelectedSubjectId] = React.useState<string>("")
  const [isSubjectMenuOpen, setIsSubjectMenuOpen] = React.useState(false)
  const [showHistory, setShowHistory] = React.useState(false)
  const [sessions, setSessions] = React.useState<StudySessionItem[]>([])
  const [isLoadingHistory, setIsLoadingHistory] = React.useState(false)
  const [isSavingSession, setIsSavingSession] = React.useState(false)
  const [deletingSessionId, setDeletingSessionId] = React.useState<
    string | null
  >(null)
  const [saveFeedback, setSaveFeedback] = React.useState<string | null>(null)
  const hasAutoSavedRef = React.useRef(false)

  // Đọc cấu hình mặc định từ Settings, vị trí góc đã lưu & lắng nghe resize viewport
  React.useEffect(() => {
    const updateViewport = () => {
      setViewport({ w: window.innerWidth, h: window.innerHeight })
    }
    updateViewport()
    window.addEventListener("resize", updateViewport)

    const prefs = loadLearningPreferences()
    if (prefs.sessionMode === "deep_work") {
      dispatch({
        type: "INIT_FROM_PREFS",
        modeId: "deep_work",
        durationSeconds: 50 * 60,
      })
    } else {
      dispatch({
        type: "INIT_FROM_PREFS",
        modeId: "pomodoro",
        durationSeconds: 25 * 60,
      })
    }

    try {
      const savedCorner = localStorage.getItem(
        CORNER_STORAGE_KEY
      ) as ScreenCorner | null
      if (
        savedCorner === "bottom-right" ||
        savedCorner === "bottom-left" ||
        savedCorner === "top-right" ||
        savedCorner === "top-left"
      ) {
        setCorner(savedCorner)
      }
    } catch {
      // Ignore storage error
    }

    return () => {
      window.removeEventListener("resize", updateViewport)
    }
  }, [])

  // Tải danh sách môn học và lịch sử phiên học khi mở bảng Pomodoro
  const loadSubjectsAndSessions = React.useCallback(async () => {
    try {
      const subjList = await fetchSubjects().catch(() => [])
      setSubjects(subjList)
      if (subjList.length > 0 && !selectedSubjectId) {
        setSelectedSubjectId(subjList[0].id)
      }
    } catch {
      // Ignore unauthorized or network error
    }
  }, [selectedSubjectId])

  const loadSessionHistory = React.useCallback(async () => {
    setIsLoadingHistory(true)
    try {
      const list = await getStudySessions({ limit: 10 })
      setSessions(list)
    } catch {
      // Ignore error
    } finally {
      setIsLoadingHistory(false)
    }
  }, [])

  React.useEffect(() => {
    if (isExpanded) {
      void loadSubjectsAndSessions()
      if (showHistory) {
        void loadSessionHistory()
      }
    } else {
      setIsSubjectMenuOpen(false)
    }
  }, [isExpanded, showHistory, loadSubjectsAndSessions, loadSessionHistory])

  // Tự động lưu phiên học lên Backend khi hoàn thành 100% chu kỳ tập trung
  const handleRecordSessionToApi = React.useCallback(
    async (minutesToSave: number, isAutoComplete: boolean) => {
      if (!selectedSubjectId || modeId === "break" || minutesToSave < 1) return
      const clampedMinutes = Math.min(180, Math.max(1, Math.round(minutesToSave)))

      setIsSavingSession(true)
      setSaveFeedback(null)
      try {
        const created = await createStudySession({
          subject_id: selectedSubjectId,
          duration_minutes: clampedMinutes,
          session_type: modeId,
        })
        setSessions((prev) => [created, ...prev.slice(0, 9)])
        setSaveFeedback(
          isAutoComplete
            ? `Đã tự động lưu phiên học ${clampedMinutes} phút!`
            : `Đã lưu phiên học ${clampedMinutes} phút!`
        )
        if (!isAutoComplete) {
          dispatch({ type: "RESET" })
        }
      } catch (err) {
        setSaveFeedback(
          err instanceof Error
            ? err.message
            : "Không thể lưu phiên học lên hệ thống."
        )
      } finally {
        setIsSavingSession(false)
      }
    },
    [selectedSubjectId, modeId]
  )

  React.useEffect(() => {
    if (
      status === "completed" &&
      modeId !== "break" &&
      selectedSubjectId &&
      !hasAutoSavedRef.current
    ) {
      hasAutoSavedRef.current = true
      const totalMins = Math.max(1, Math.round(totalSeconds / 60))
      void handleRecordSessionToApi(totalMins, true)
    }
  }, [status, modeId, selectedSubjectId, totalSeconds, handleRecordSessionToApi])

  const handleDeleteSessionItem = async (sessionId: string) => {
    setDeletingSessionId(sessionId)
    try {
      await deleteStudySession(sessionId)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))
    } catch {
      // Ignore error
    } finally {
      setDeletingSessionId(null)
    }
  }

  // Lắng nghe sự kiện chuyển tab (Page Visibility API)
  React.useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden && status === "running" && modeId !== "break") {
        dispatch({ type: "TAB_SWITCH", timestamp: formatCurrentTime() })
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange)
    }
  }, [status, modeId])

  // Bộ đếm ngược mỗi giây (1000ms) thông qua pure reducer TICK
  React.useEffect(() => {
    if (status !== "running") return

    const timer = window.setInterval(() => {
      dispatch({ type: "TICK" })
    }, 1000)

    return () => {
      window.clearInterval(timer)
    }
  }, [status])

  // Xử lý kéo thả nút tròn vào 4 góc màn hình với GPU translate3d mượt mà
  const handleOrbPointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    if (e.button !== 0) return
    const rect = e.currentTarget.getBoundingClientRect()
    e.currentTarget.setPointerCapture(e.pointerId)
    dragRef.current = {
      pointerId: e.pointerId,
      startX: e.clientX,
      startY: e.clientY,
      originLeft: rect.left,
      originTop: rect.top,
      lastX: rect.left,
      lastY: rect.top,
      moved: false,
    }
  }

  const handleOrbPointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const info = dragRef.current
    if (!info || info.pointerId !== e.pointerId) return

    const dx = e.clientX - info.startX
    const dy = e.clientY - info.startY

    if (!info.moved && Math.hypot(dx, dy) > 5) {
      info.moved = true
    }

    if (info.moved) {
      const maxX = window.innerWidth - ORB_SIZE - 8
      const maxY = window.innerHeight - ORB_SIZE - 8
      const nextX = Math.max(8, Math.min(maxX, info.originLeft + dx))
      const nextY = Math.max(8, Math.min(maxY, info.originTop + dy))
      info.lastX = nextX
      info.lastY = nextY
      setDragPos({ x: nextX, y: nextY })
    }
  }

  const handleOrbPointerUp = (e: React.PointerEvent<HTMLButtonElement>) => {
    const info = dragRef.current
    if (!info || info.pointerId !== e.pointerId) return

    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }

    dragRef.current = null

    if (!info.moved) {
      // Nếu chỉ ấn vào (không kéo) -> Mở/Đóng giao diện Pomodoro
      setDragPos(null)
      dispatch({ type: "TOGGLE_EXPANDED" })
      return
    }

    // Tính toán góc gần nhất dựa trên tọa độ thả cuối cùng + hướng vận tốc nhẹ
    const centerX = info.lastX + ORB_SIZE / 2
    const centerY = info.lastY + ORB_SIZE / 2
    const isRight = centerX >= window.innerWidth / 2
    const isBottom = centerY >= window.innerHeight / 2

    const nextCorner: ScreenCorner = isBottom
      ? isRight
        ? "bottom-right"
        : "bottom-left"
      : isRight
        ? "top-right"
        : "top-left"

    setViewport({ w: window.innerWidth, h: window.innerHeight })
    setCorner(nextCorner)
    setDragPos(null)

    try {
      localStorage.setItem(CORNER_STORAGE_KEY, nextCorner)
    } catch {
      // Ignore storage error
    }
  }

  const handleSelectMode = (preset: PomodoroPreset) => {
    hasAutoSavedRef.current = false
    setSaveFeedback(null)
    setIsSubjectMenuOpen(false)
    dispatch({
      type: "SELECT_MODE",
      modeId: preset.id,
      durationSeconds: preset.minutes * 60,
    })
  }

  const handleStartOrResume = () => {
    if (status === "idle" || status === "completed") {
      hasAutoSavedRef.current = false
      setSaveFeedback(null)
    }
    setIsSubjectMenuOpen(false)
    dispatch({ type: "START_OR_RESUME" })
  }

  const handleManualPause = () => {
    dispatch({ type: "PAUSE_MANUAL" })
  }

  const handleReset = () => {
    hasAutoSavedRef.current = false
    setSaveFeedback(null)
    dispatch({ type: "RESET" })
  }

  const progressPct =
    totalSeconds > 0
      ? Math.min(
          100,
          Math.max(
            0,
            Math.round(((totalSeconds - remainingSeconds) / totalSeconds) * 100)
          )
        )
      : 0

  const elapsedMinutes = Math.floor((totalSeconds - remainingSeconds) / 60)

  const secondsUntilNextCheckin = Math.max(
    0,
    CHECKIN_INTERVAL_SECONDS - activeCheckinSeconds
  )

  const isAlertState =
    status === "paused_tab_switch" || status === "paused_checkin"

  const subjectNameMap = React.useMemo(() => {
    const map: Record<string, string> = {}
    for (const s of subjects) {
      map[s.id] = s.name
    }
    return map
  }, [subjects])

  const selectedSubjectName =
    (selectedSubjectId && subjectNameMap[selectedSubjectId]) ||
    subjects[0]?.name ||
    "Chọn môn học"

  const renderModeIcon = (id: PomodoroModeId, className = "h-3.5 w-3.5") => {
    if (id === "deep_work") return <Zap className={className} />
    if (id === "break") return <Coffee className={className} />
    return <Flame className={className} />
  }

  // Vị trí 4 góc dự phòng khi SSR (trước khi đo được viewport)
  const cornerFallbackClasses: Record<ScreenCorner, string> = {
    "bottom-right": "bottom-5 right-5",
    "bottom-left": "bottom-5 left-5",
    "top-right": "top-5 right-5",
    "top-left": "top-5 left-5",
  }

  // Vị trí bung bảng Pomodoro tương ứng với góc của nút tròn
  const popoverPositionClasses: Record<ScreenCorner, string> = {
    "bottom-right": "bottom-20 right-5",
    "bottom-left": "bottom-20 left-5",
    "top-right": "top-20 right-5",
    "top-left": "top-20 left-5",
  }

  // Tọa độ thực tế (x, y) của nút tròn để nội suy mượt bằng translate3d
  const snappedCoords = viewport
    ? computeCornerCoords(corner, viewport.w, viewport.h)
    : null
  const activeOrbCoords = dragPos ?? snappedCoords

  // Thông số vòng tròn tiến độ SVG viền ngoài nút tròn
  const circleRadius = 21
  const circleCircumference = 2 * Math.PI * circleRadius
  const strokeDashoffset =
    circleCircumference - (progressPct / 100) * circleCircumference

  return (
    <>
      {/* ====================================================================
          NÚT TRÒN DUY NHẤT (DRAGGABLE 4-CORNER ORB VỚI SPRING ANIMATION)
         ==================================================================== */}
      <button
        type="button"
        onPointerDown={handleOrbPointerDown}
        onPointerMove={handleOrbPointerMove}
        onPointerUp={handleOrbPointerUp}
        aria-label="Mở hoặc di chuyển đồng hồ Pomodoro"
        title="Nhấn để mở giao diện Pomodoro · Kéo để đặt vào 4 góc màn hình"
        style={
          activeOrbCoords
            ? {
                left: 0,
                top: 0,
                width: `${ORB_SIZE}px`,
                height: `${ORB_SIZE}px`,
                transform: `translate3d(${activeOrbCoords.x}px, ${activeOrbCoords.y}px, 0) scale(${
                  dragPos ? 1.08 : 1
                })`,
                transition: dragPos
                  ? "box-shadow 150ms ease, background-color 150ms ease"
                  : "transform 450ms cubic-bezier(0.22, 1, 0.36, 1), box-shadow 200ms ease, background-color 200ms ease",
              }
            : {
                width: `${ORB_SIZE}px`,
                height: `${ORB_SIZE}px`,
              }
        }
        className={`fixed z-50 rounded-full shadow-xl backdrop-blur-md flex items-center justify-center select-none touch-none cursor-grab active:cursor-grabbing will-change-transform ${
          !activeOrbCoords ? cornerFallbackClasses[corner] : ""
        } ${
          status === "paused_tab_switch"
            ? "bg-amber-600 text-white ring-4 ring-amber-500/30"
            : status === "paused_checkin"
              ? "bg-[#0A77FF] text-white ring-4 ring-[#0A77FF]/30"
              : status === "running"
                ? "bg-slate-900/95 text-white shadow-[#0A77FF]/25"
                : "bg-white/95 dark:bg-slate-900/95 text-slate-700 dark:text-slate-100 border border-slate-200/90 dark:border-slate-800"
        }`}
      >
        {/* Vòng tròn mảnh báo tiến độ quanh viền nút tròn */}
        <svg
          className="absolute inset-0 h-full w-full -rotate-90 pointer-events-none"
          viewBox="0 0 52 52"
        >
          <circle
            cx="26"
            cy="26"
            r={circleRadius}
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            className="text-slate-200/30 dark:text-slate-800/60"
          />
          {status !== "idle" && (
            <circle
              cx="26"
              cy="26"
              r={circleRadius}
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeDasharray={circleCircumference}
              strokeDashoffset={strokeDashoffset}
              className={`transition-all duration-300 ${
                status === "paused_tab_switch"
                  ? "text-amber-200"
                  : status === "paused_checkin"
                    ? "text-white"
                    : status === "completed"
                      ? "text-emerald-400"
                      : "text-[#0A77FF]"
              }`}
            />
          )}
        </svg>

        {/* Biểu tượng trung tâm tối giản */}
        {status === "paused_tab_switch" ? (
          <AlertTriangle className="h-5 w-5 text-white animate-pulse pointer-events-none" />
        ) : status === "paused_checkin" ? (
          <BellRing className="h-5 w-5 text-white animate-bounce pointer-events-none" />
        ) : (
          <Timer
            className={`h-5 w-5 pointer-events-none ${
              status === "running"
                ? "text-[#0A77FF]"
                : status === "completed"
                  ? "text-emerald-500"
                  : "text-[#0A77FF] dark:text-sky-400"
            }`}
          />
        )}

        {/* Chấm nhỏ báo trạng thái trên viền nút tròn */}
        {status !== "idle" && (
          <span className="absolute top-0.5 right-0.5 flex h-3 w-3 pointer-events-none">
            {(status === "running" || isAlertState) && (
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  status === "paused_tab_switch"
                    ? "bg-amber-300"
                    : "bg-[#0A77FF]"
                }`}
              />
            )}
            <span
              className={`relative inline-flex rounded-full h-3 w-3 border-2 border-white dark:border-slate-900 ${
                status === "running"
                  ? "bg-[#0A77FF]"
                  : status === "paused_tab_switch"
                    ? "bg-amber-400"
                    : status === "paused_checkin"
                      ? "bg-sky-300"
                      : status === "completed"
                        ? "bg-emerald-500"
                        : "bg-slate-400"
              }`}
            />
          </span>
        )}
      </button>

      {/* ====================================================================
          GIAO DIỆN POMODORO (CHỈ HIỆN KHI ẤN VÀO NÚT TRÒN HOẶC CÓ CẢNH BÁO)
         ==================================================================== */}
      {isExpanded && (
        <aside
          aria-label="Bộ bấm giờ học tập Pomodoro"
          className={`fixed z-50 w-80 sm:w-[340px] rounded-2xl border bg-white/95 dark:bg-slate-900/95 backdrop-blur-md shadow-2xl transition-all duration-200 overflow-hidden select-none ${
            popoverPositionClasses[corner]
          } ${
            status === "paused_tab_switch"
              ? "border-amber-500/70 ring-2 ring-amber-500/20"
              : status === "paused_checkin"
                ? "border-[#0A77FF]/80 ring-2 ring-[#0A77FF]/25"
                : "border-slate-200/90 dark:border-slate-800"
          }`}
        >
          {/* Top Progress Strip */}
          <div className="h-1 w-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
            <div
              style={{ width: `${progressPct}%` }}
              className={`h-full transition-all duration-300 ${
                status === "paused_tab_switch"
                  ? "bg-amber-500"
                  : status === "completed"
                    ? "bg-emerald-500"
                    : "bg-[#0A77FF]"
              }`}
            />
          </div>

          <div className="p-4 space-y-3.5">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div
                  className={`h-7 w-7 rounded-lg flex items-center justify-center ${
                    status === "paused_tab_switch"
                      ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                      : status === "paused_checkin"
                        ? "bg-[#0A77FF]/15 text-[#0A77FF] dark:text-sky-400"
                        : "bg-[#0A77FF]/10 text-[#0A77FF] dark:text-sky-400"
                  }`}
                >
                  <Timer className="h-4 w-4" />
                </div>
                <div className="flex items-center gap-1.5">
                  <h3 className="text-xs font-bold tracking-tight text-slate-900 dark:text-slate-100">
                    Pomodoro Focus
                  </h3>
                  {status !== "idle" && (
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase ${
                        status === "running"
                          ? "bg-emerald-500/12 text-emerald-600 dark:text-emerald-400"
                          : status === "paused_tab_switch"
                            ? "bg-amber-500/15 text-amber-600 dark:text-amber-400"
                            : status === "paused_checkin"
                              ? "bg-[#0A77FF]/15 text-[#0A77FF] dark:text-sky-400"
                              : status === "completed"
                                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                                : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
                      }`}
                    >
                      {status === "running"
                        ? "Đang học"
                        : status === "paused_tab_switch"
                          ? "Rời Tab"
                          : status === "paused_checkin"
                            ? "Điểm danh"
                            : status === "paused_manual"
                              ? "Tạm dừng"
                              : "Hoàn thành"}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => setShowHistory((prev) => !prev)}
                  aria-label="Lịch sử phiên học Pomodoro"
                  title="Lịch sử phiên học"
                  className={`h-7 w-7 rounded-lg flex items-center justify-center transition-colors cursor-pointer ${
                    showHistory
                      ? "bg-[#0A77FF]/15 text-[#0A77FF] dark:text-sky-400"
                      : "text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
                  }`}
                >
                  <History className="h-3.5 w-3.5" />
                </button>

                <button
                  type="button"
                  onClick={() =>
                    dispatch({ type: "SET_EXPANDED", isExpanded: false })
                  }
                  aria-label="Đóng bảng Pomodoro"
                  title="Đóng"
                  className="h-7 w-7 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-center transition-colors cursor-pointer"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {showHistory ? (
              /* ==============================================================
                 DANH SÁCH LỊCH SỬ PHIÊN HỌC TỪ API (/api/v1/study-sessions)
                 ============================================================== */
              <div className="space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-slate-600 dark:text-slate-300">
                    Nhật ký phiên học gần đây
                  </span>
                  <button
                    type="button"
                    onClick={() => setShowHistory(false)}
                    className="text-[11px] font-medium text-[#0A77FF] hover:underline cursor-pointer"
                  >
                    Quay lại đồng hồ
                  </button>
                </div>

                {isLoadingHistory ? (
                  <div className="py-8 flex items-center justify-center text-slate-400">
                    <Loader2 className="h-4 w-4 animate-spin" />
                  </div>
                ) : sessions.length === 0 ? (
                  <div className="py-6 text-center text-xs text-slate-400 dark:text-slate-500">
                    Chưa có phiên học nào được lưu.
                  </div>
                ) : (
                  <div className="max-h-52 overflow-y-auto space-y-1.5 pr-0.5">
                    {sessions.map((item) => (
                      <div
                        key={item.id}
                        className="rounded-xl border border-slate-200/70 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/60 px-2.5 py-2 flex items-center justify-between gap-2 text-xs"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="font-medium text-slate-800 dark:text-slate-200 truncate">
                            {item.subject_id && subjectNameMap[item.subject_id]
                              ? subjectNameMap[item.subject_id]
                              : "Phiên tập trung"}
                          </div>
                          <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-400 tabular-nums">
                            <span className="text-[#0A77FF] dark:text-sky-400 font-semibold">
                              {item.duration_minutes}m
                            </span>
                            <span>·</span>
                            <span>{item.session_type}</span>
                            <span>·</span>
                            <span>{formatSessionDate(item.completed_at)}</span>
                          </div>
                        </div>

                        <button
                          type="button"
                          disabled={deletingSessionId === item.id}
                          onClick={() => void handleDeleteSessionItem(item.id)}
                          aria-label="Xóa phiên học"
                          className="h-6 w-6 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 flex items-center justify-center transition-colors cursor-pointer shrink-0"
                        >
                          {deletingSessionId === item.id ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Trash2 className="h-3 w-3" />
                          )}
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              /* ==============================================================
                 BẢNG ĐIỀU KHIỂN ĐỒNG HỒ POMODORO CHÍNH
                 ============================================================== */
              <>
                {/* Preset Selector Tabs */}
                <div className="grid grid-cols-3 gap-1 p-1 rounded-xl bg-slate-100/90 dark:bg-slate-950 border border-slate-200/60 dark:border-slate-800/80">
                  {POMODORO_PRESETS.map((preset) => {
                    const isSelected = modeId === preset.id
                    return (
                      <button
                        key={preset.id}
                        type="button"
                        onClick={() => handleSelectMode(preset)}
                        className={`h-7 px-2 rounded-lg text-[11px] font-medium inline-flex items-center justify-center gap-1 transition-all cursor-pointer tabular-nums ${
                          isSelected
                            ? "bg-white dark:bg-slate-800 text-[#0A77FF] dark:text-sky-400 font-semibold shadow-2xs"
                            : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                        }`}
                      >
                        {renderModeIcon(preset.id, "h-3 w-3")}
                        <span>{preset.shortLabel}</span>
                      </button>
                    )
                  })}
                </div>

                {/* Bộ chọn môn học tùy biến (Custom Dropdown không có viền đen mặc định của trình duyệt) */}
                {modeId !== "break" && subjects.length > 0 && (
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setIsSubjectMenuOpen((prev) => !prev)}
                      aria-expanded={isSubjectMenuOpen}
                      aria-label="Chọn môn học cho phiên Pomodoro"
                      className={`w-full flex items-center justify-between gap-2 rounded-xl border px-3 h-9 text-xs font-medium transition-colors cursor-pointer focus:outline-none ${
                        isSubjectMenuOpen
                          ? "border-[#0A77FF]/60 bg-white dark:bg-slate-900 text-slate-900 dark:text-white ring-2 ring-[#0A77FF]/15"
                          : "border-slate-200/80 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/60 text-slate-700 dark:text-slate-200 hover:border-slate-300 dark:hover:border-slate-700"
                      }`}
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <BookOpen className="h-3.5 w-3.5 text-[#0A77FF] dark:text-sky-400 shrink-0" />
                        <span className="truncate">
                          Môn: {selectedSubjectName}
                        </span>
                      </span>
                      <ChevronDown
                        className={`h-3.5 w-3.5 text-slate-400 shrink-0 transition-transform duration-150 ${
                          isSubjectMenuOpen ? "rotate-180 text-[#0A77FF]" : ""
                        }`}
                      />
                    </button>

                    {isSubjectMenuOpen && (
                      <div className="mt-1.5 max-h-40 overflow-y-auto rounded-xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-slate-900 p-1 shadow-lg space-y-0.5">
                        {subjects.map((subj) => {
                          const isCurrent = subj.id === selectedSubjectId
                          return (
                            <button
                              key={subj.id}
                              type="button"
                              onClick={() => {
                                setSelectedSubjectId(subj.id)
                                setIsSubjectMenuOpen(false)
                              }}
                              className={`w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-xs text-left transition-colors cursor-pointer ${
                                isCurrent
                                  ? "bg-[#0A77FF]/10 text-[#0A77FF] dark:text-sky-400 font-semibold"
                                  : "text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800"
                              }`}
                            >
                              <span className="truncate">{subj.name}</span>
                              {isCurrent && (
                                <Check className="h-3.5 w-3.5 shrink-0 text-[#0A77FF] dark:text-sky-400" />
                              )}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )}

                {/* ============================================================
                    BANNER CẢNH BÁO 1: PHÁT HIỆN CHUYỂN TAB (paused_tab_switch)
                   ============================================================ */}
                {status === "paused_tab_switch" && (
                  <div
                    role="alert"
                    className="rounded-xl border border-amber-500/40 bg-amber-500/10 dark:bg-amber-950/40 p-3 space-y-2.5"
                  >
                    <div className="flex items-start gap-2.5">
                      <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
                      <div className="space-y-1 text-xs">
                        <p className="font-semibold text-amber-900 dark:text-amber-200">
                          Phát hiện rời khỏi Tab học tập!
                        </p>
                        <p className="text-amber-800/90 dark:text-amber-300/90 leading-relaxed">
                          Đồng hồ đã tự động dừng
                          {tabSwitchTime ? ` lúc ${tabSwitchTime}` : ""} vì bạn
                          chuyển sang tab khác.
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={handleStartOrResume}
                      className="w-full h-8 rounded-lg bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold inline-flex items-center justify-center gap-1.5 shadow-xs transition-colors cursor-pointer"
                    >
                      <Play className="h-3.5 w-3.5 fill-current" />
                      <span>Tiếp tục học ngay</span>
                    </button>
                  </div>
                )}

                {/* ============================================================
                    BANNER CẢNH BÁO 2: XÁC NHẬN HIỆN DIỆN MỖI 2 PHÚT
                   ============================================================ */}
                {status === "paused_checkin" && (
                  <div
                    role="alert"
                    className="rounded-xl border border-[#0A77FF]/40 bg-[#0A77FF]/10 dark:bg-[#0A77FF]/15 p-3 space-y-2.5"
                  >
                    <div className="flex items-start gap-2.5">
                      <BellRing className="h-4 w-4 text-[#0A77FF] dark:text-sky-400 shrink-0 mt-0.5 animate-bounce" />
                      <div className="space-y-1 text-xs">
                        <p className="font-semibold text-slate-900 dark:text-white">
                          Bạn vẫn còn ở đây chứ?
                        </p>
                        <p className="text-slate-600 dark:text-slate-300 leading-relaxed">
                          Đã qua 2 phút tập trung liên tục. Đồng hồ đang tạm
                          dừng chờ bạn xác nhận để tiếp tục tính giờ.
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={handleStartOrResume}
                      className="w-full h-8 rounded-lg bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center justify-center gap-1.5 shadow-xs transition-colors cursor-pointer"
                    >
                      <ShieldCheck className="h-3.5 w-3.5" />
                      <span>Tôi vẫn đang học — Tiếp tục</span>
                    </button>
                  </div>
                )}

                {/* ============================================================
                    BANNER HOÀN THÀNH PHIÊN HỌC (completed)
                   ============================================================ */}
                {status === "completed" && (
                  <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 dark:bg-emerald-950/40 p-3 flex items-center gap-2.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
                    <p className="text-xs font-medium text-emerald-900 dark:text-emerald-200">
                      Tuyệt vời! Bạn đã hoàn thành trọn vẹn phiên tập trung này.
                    </p>
                  </div>
                )}

                {/* Phản hồi lưu API */}
                {saveFeedback && (
                  <div className="rounded-lg bg-slate-100 dark:bg-slate-800/80 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 dark:text-slate-300 text-center">
                    {saveFeedback}
                  </div>
                )}

                {/* Main Countdown Display */}
                <div className="py-1.5 text-center space-y-1">
                  <div
                    className={`text-4xl font-mono font-bold tracking-tight tabular-nums ${
                      status === "paused_tab_switch"
                        ? "text-amber-600 dark:text-amber-400"
                        : status === "paused_checkin"
                          ? "text-[#0A77FF] dark:text-sky-400"
                          : status === "completed"
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-slate-900 dark:text-white"
                    }`}
                  >
                    {formatCountdown(remainingSeconds)}
                  </div>

                  {/* Sub-telemetry: 2-minute check-in countdown & tab switch counter */}
                  <div className="flex items-center justify-center gap-3 text-[11px] font-mono text-slate-400 dark:text-slate-500 tabular-nums">
                    {modeId !== "break" && (
                      <span>
                        Check-in sau: {formatCountdown(secondsUntilNextCheckin)}
                      </span>
                    )}
                    {tabSwitchCount > 0 && (
                      <>
                        <span>·</span>
                        <span className="text-amber-600 dark:text-amber-400">
                          Rời tab: {tabSwitchCount} lần
                        </span>
                      </>
                    )}
                  </div>
                </div>

                {/* Primary Action Controls */}
                <div className="flex items-center gap-2">
                  {status === "running" ? (
                    <button
                      type="button"
                      onClick={handleManualPause}
                      className="flex-1 h-9 rounded-xl bg-slate-900 dark:bg-slate-800 hover:bg-slate-800 dark:hover:bg-slate-700 text-white text-xs font-semibold inline-flex items-center justify-center gap-1.5 transition-colors cursor-pointer"
                    >
                      <Pause className="h-3.5 w-3.5" />
                      <span>Tạm dừng</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleStartOrResume}
                      className="flex-1 h-9 rounded-xl bg-[#0A77FF] hover:bg-[#0A77FF]/90 text-white text-xs font-semibold inline-flex items-center justify-center gap-1.5 shadow-xs transition-colors cursor-pointer"
                    >
                      <Play className="h-3.5 w-3.5 fill-current" />
                      <span>
                        {status === "idle" || status === "completed"
                          ? "Bắt đầu học"
                          : "Tiếp tục học"}
                      </span>
                    </button>
                  )}

                  {/* Nút Lưu sớm phiên học nếu đã học >= 1 phút và đang tạm dừng */}
                  {status !== "running" &&
                    status !== "idle" &&
                    status !== "completed" &&
                    modeId !== "break" &&
                    selectedSubjectId &&
                    elapsedMinutes >= 1 && (
                      <button
                        type="button"
                        disabled={isSavingSession}
                        onClick={() =>
                          void handleRecordSessionToApi(elapsedMinutes, false)
                        }
                        title={`Lưu ${elapsedMinutes} phút đã học vào hệ thống`}
                        className="h-9 px-2.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 text-xs font-mono font-semibold inline-flex items-center gap-1 transition-colors cursor-pointer shrink-0 tabular-nums"
                      >
                        {isSavingSession ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Save className="h-3.5 w-3.5" />
                        )}
                        <span>{elapsedMinutes}m</span>
                      </button>
                    )}

                  <button
                    type="button"
                    onClick={handleReset}
                    aria-label="Đặt lại đồng hồ"
                    title="Đặt lại (Reset)"
                    className="h-9 w-9 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 flex items-center justify-center transition-colors cursor-pointer shrink-0"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </button>
                </div>
              </>
            )}
          </div>
        </aside>
      )}
    </>
  )
}
