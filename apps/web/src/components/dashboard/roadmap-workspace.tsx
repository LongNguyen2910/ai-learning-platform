"use client"

import * as React from "react"
import {
  Network,
  Clock,
  FileText,
  Sparkles,
  Loader2,
  Trash2,
  ChevronRight,
  ChevronDown,
  BookOpen,
  ArrowUpRight,
  AlertCircle,
  CheckCircle2,
  Plus,
  RefreshCw,
  Compass,
  Lock,
  PlayCircle,
  Check,
  Layers,
} from "lucide-react"
import type { DocumentItem } from "@/lib/api/documents"
import {
  fetchRoadmaps,
  fetchRoadmapTree,
  fetchRoadmapTaskStatus,
  generateRoadmap,
  deleteRoadmap,
  completeRoadmapNode,
  type SubjectItem,
  type RoadmapItem,
  type RoadmapNodeItem,
  type RoadmapTreeResponse,
  type RoadmapTaskStatusResponse,
} from "@/lib/api/roadmaps"

interface RoadmapWorkspaceProps {
  documents: DocumentItem[]
  subjects: SubjectItem[]
  preselectedSubjectId?: string | null
  onOpenDocumentAtPage: (documentId: string, pageNumber?: number) => void
  onSwitchToDocuments: (filterSubjectId?: string | null) => void
}

function getDefaultTargetDateString(daysFromNow = 14): string {
  const d = new Date()
  d.setDate(d.getDate() + daysFromNow)
  return d.toISOString().split("T")[0]
}

function getTomorrowDateString(): string {
  const d = new Date()
  d.setDate(d.getDate() + 1)
  return d.toISOString().split("T")[0]
}

function formatShortDate(isoDate: string | null): string {
  if (!isoDate) return "No deadline"
  try {
    const d = new Date(isoDate)
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    })
  } catch {
    return isoDate
  }
}

function computeTopicMinutes(topicNode: RoadmapNodeItem): number {
  if (topicNode.estimated_minutes > 0) return topicNode.estimated_minutes
  if (!topicNode.children || topicNode.children.length === 0) return 25
  return topicNode.children.reduce(
    (sum, block) => sum + (block.estimated_minutes || 25),
    0
  )
}

function computeChapterMinutes(chapterNode: RoadmapNodeItem): number {
  if (chapterNode.estimated_minutes > 0) return chapterNode.estimated_minutes
  if (!chapterNode.children || chapterNode.children.length === 0) return 0
  return chapterNode.children.reduce(
    (sum, topic) => sum + computeTopicMinutes(topic),
    0
  )
}

function formatDuration(minutes: number): string {
  if (minutes <= 0) return "—"
  if (minutes < 60) return `${minutes} min`
  const hrs = Math.floor(minutes / 60)
  const mins = minutes % 60
  return mins > 0 ? `${hrs}h ${mins}m` : `${hrs} hrs`
}

/**
 * Finds the Topic IDs that should be auto-expanded by default:
 * expands any topic containing an unlocked & incomplete study block (or the first topic with blocks).
 */
function resolveAutoExpandedTopicIds(
  tree: RoadmapNodeItem[]
): Record<string, boolean> {
  const expanded: Record<string, boolean> = {}
  let foundActive = false

  for (const ch of tree) {
    for (const tp of ch.children || []) {
      const blocks = tp.children || []
      if (blocks.some((b) => b.is_unlocked && !b.is_completed)) {
        expanded[tp.id] = true
        foundActive = true
      }
    }
  }

  if (!foundActive) {
    for (const ch of tree) {
      const firstTopicWithBlocks = (ch.children || []).find(
        (tp) => (tp.children || []).length > 0
      )
      if (firstTopicWithBlocks) {
        expanded[firstTopicWithBlocks.id] = true
        break
      }
    }
  }

  return expanded
}

const HOUR_PRESETS = [1.0, 2.0, 3.0, 4.0]

export function RoadmapWorkspace({
  documents,
  subjects,
  preselectedSubjectId,
  onOpenDocumentAtPage,
  onSwitchToDocuments,
}: RoadmapWorkspaceProps) {
  const [roadmaps, setRoadmaps] = React.useState<RoadmapItem[]>([])
  const [isLoadingList, setIsLoadingList] = React.useState(true)
  const [selectedRoadmapId, setSelectedRoadmapId] = React.useState<
    string | null
  >(null)
  const [activeTree, setActiveTree] =
    React.useState<RoadmapTreeResponse | null>(null)
  const [isLoadingTree, setIsLoadingTree] = React.useState(false)
  const [treeError, setTreeError] = React.useState<string | null>(null)

  // Node completion state
  const [completingNodeId, setCompletingNodeId] = React.useState<string | null>(
    null
  )
  const [completionError, setCompletionError] = React.useState<string | null>(
    null
  )

  // Form states
  const [isFormExpanded, setIsFormExpanded] = React.useState(true)
  const [selectedSubjectId, setSelectedSubjectId] = React.useState<string>("")
  const [title, setTitle] = React.useState<string>("")
  const [targetDate, setTargetDate] = React.useState<string>("")
  const [minTargetDate, setMinTargetDate] = React.useState<string>("")
  const [todayTimestamp, setTodayTimestamp] = React.useState<number | null>(
    null
  )
  const [hoursPerDay, setHoursPerDay] = React.useState<number>(2.0)
  const [studyGoal, setStudyGoal] = React.useState<string>("")
  const [formError, setFormError] = React.useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  // Background generation task state
  const [activeTask, setActiveTask] =
    React.useState<RoadmapTaskStatusResponse | null>(null)
  const [deletingId, setDeletingId] = React.useState<string | null>(null)

  // Expanded chapters & topics state
  const [collapsedChapterIds, setCollapsedChapterIds] = React.useState<
    Record<string, boolean>
  >({})
  const [expandedTopicIds, setExpandedTopicIds] = React.useState<
    Record<string, boolean>
  >({})

  // Initialize current date values on client mount to avoid Next.js 16 prerender Date() error
  React.useEffect(() => {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    setTodayTimestamp(today.getTime())
    setMinTargetDate(getTomorrowDateString())
    setTargetDate((prev) => prev || getDefaultTargetDateString(14))
  }, [])

  // Sync preselected Subject or default to first Subject
  React.useEffect(() => {
    if (
      preselectedSubjectId &&
      subjects.some((s) => s.id === preselectedSubjectId)
    ) {
      setSelectedSubjectId(preselectedSubjectId)
      const subj = subjects.find((s) => s.id === preselectedSubjectId)
      if (subj) {
        setTitle(`Roadmap: ${subj.name}`)
      }
      setIsFormExpanded(true)
    } else if (!selectedSubjectId && subjects.length > 0) {
      const firstSubj = subjects[0]
      setSelectedSubjectId(firstSubj.id)
      setTitle(`Roadmap: ${firstSubj.name}`)
    }
  }, [preselectedSubjectId, subjects, selectedSubjectId])

  // Documents belonging to the currently selected Subject
  const subjectDocuments = React.useMemo(() => {
    if (!selectedSubjectId) return []
    return documents.filter((d) => d.subject_id === selectedSubjectId)
  }, [documents, selectedSubjectId])

  const readySubjectDocuments = React.useMemo(
    () =>
      subjectDocuments.filter(
        (d) => d.status === "ready" || d.status === "parsed"
      ),
    [subjectDocuments]
  )

  const documentTitleMap = React.useMemo(() => {
    const map: Record<string, string> = {}
    for (const d of documents) {
      map[d.document_id] = d.title
    }
    return map
  }, [documents])

  const subjectMap = React.useMemo(() => {
    const map: Record<string, SubjectItem> = {}
    for (const s of subjects) {
      map[s.id] = s
    }
    return map
  }, [subjects])

  const loadRoadmapsList = React.useCallback(
    async (autoSelectFirst = false) => {
      setIsLoadingList(true)
      try {
        const list = await fetchRoadmaps()
        setRoadmaps(list)
        if (autoSelectFirst && list.length > 0 && !selectedRoadmapId) {
          setSelectedRoadmapId(list[0].id)
        }
      } catch {
        // Keep current list on transient error
      } finally {
        setIsLoadingList(false)
      }
    },
    [selectedRoadmapId]
  )

  React.useEffect(() => {
    void loadRoadmapsList(true)
  }, [loadRoadmapsList])

  // Load selected roadmap tree
  const loadSelectedRoadmapTree = React.useCallback(
    async (roadmapId: string, preserveExpandState = false) => {
      if (!preserveExpandState) {
        setIsLoadingTree(true)
      }
      setTreeError(null)
      setCompletionError(null)
      try {
        const treeData = await fetchRoadmapTree(roadmapId)
        setActiveTree(treeData)
        if (!preserveExpandState) {
          setCollapsedChapterIds({})
          setExpandedTopicIds(resolveAutoExpandedTopicIds(treeData.tree))
        } else {
          const autoExpanded = resolveAutoExpandedTopicIds(treeData.tree)
          setExpandedTopicIds((prev) => ({
            ...prev,
            ...autoExpanded,
          }))
        }
      } catch (err) {
        setTreeError(
          err instanceof Error
            ? err.message
            : "Could not load roadmap tree details."
        )
      } finally {
        setIsLoadingTree(false)
      }
    },
    []
  )

  React.useEffect(() => {
    if (!selectedRoadmapId) {
      setActiveTree(null)
      return
    }
    void loadSelectedRoadmapTree(selectedRoadmapId, false)
  }, [selectedRoadmapId, loadSelectedRoadmapTree])

  // Poll active generation task every 1.8s
  React.useEffect(() => {
    if (!activeTask || activeTask.status !== "processing") return

    let cancelled = false
    const timer = setInterval(async () => {
      try {
        const statusRes = await fetchRoadmapTaskStatus(activeTask.task_id)
        if (cancelled) return
        setActiveTask(statusRes)

        if (statusRes.status === "completed") {
          clearInterval(timer)
          await loadRoadmapsList(false)
          if (statusRes.roadmap_id) {
            setSelectedRoadmapId(statusRes.roadmap_id)
            await loadSelectedRoadmapTree(statusRes.roadmap_id, false)
          }
          setTimeout(() => {
            setActiveTask((prev) =>
              prev?.task_id === statusRes.task_id ? null : prev
            )
          }, 1200)
        } else if (statusRes.status === "failed") {
          clearInterval(timer)
          await loadRoadmapsList(false)
        }
      } catch {
        // Ignore transient network poll glitch
      }
    }, 1800)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [activeTask, loadRoadmapsList, loadSelectedRoadmapTree])

  // Live time budget calculation
  const timeBudgetStats = React.useMemo(() => {
    if (!targetDate || todayTimestamp === null) return null
    const target = new Date(targetDate)
    target.setHours(0, 0, 0, 0)
    const diffDays = Math.round(
      (target.getTime() - todayTimestamp) / (1000 * 60 * 60 * 24)
    )
    if (diffDays <= 0) return null
    const totalHours = Math.round(diffDays * hoursPerDay * 10) / 10
    const totalMinutes = Math.round(totalHours * 60)
    return {
      days: diffDays,
      totalHours,
      totalMinutes,
    }
  }, [targetDate, hoursPerDay, todayTimestamp])

  const handleSubjectSelectChange = (subjId: string) => {
    setSelectedSubjectId(subjId)
    setFormError(null)
    const subj = subjects.find((s) => s.id === subjId)
    if (
      subj &&
      (!title.trim() ||
        title.startsWith("Roadmap:") ||
        title.startsWith("Lộ trình:"))
    ) {
      setTitle(`Roadmap: ${subj.name}`)
    }
  }

  const handleCreateRoadmap = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)

    if (!selectedSubjectId) {
      setFormError("Please select a subject to synthesize a roadmap.")
      return
    }

    if (readySubjectDocuments.length === 0) {
      setFormError(
        "This subject has no ready PDF documents yet. Please assign or upload documents for this subject in the Documents tab."
      )
      return
    }

    const trimmedTitle = title.trim()
    if (trimmedTitle.length < 2) {
      setFormError("Roadmap title must be at least 2 characters.")
      return
    }

    if (!timeBudgetStats || timeBudgetStats.days <= 0) {
      setFormError("Target completion date must be in the future.")
      return
    }

    setIsSubmitting(true)
    try {
      const taskRes = await generateRoadmap({
        subject_id: selectedSubjectId,
        document_id: null,
        title: trimmedTitle,
        target_date: targetDate,
        available_hours_per_day: hoursPerDay,
        session_mode: "auto",
        study_goal: studyGoal.trim() ? studyGoal.trim() : null,
      })

      setActiveTask(taskRes)
      if (taskRes.roadmap_id) {
        setSelectedRoadmapId(taskRes.roadmap_id)
      }
      await loadRoadmapsList(false)
    } catch (err) {
      setFormError(
        err instanceof Error
          ? err.message
          : "An error occurred while generating the roadmap."
      )
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDeleteRoadmap = async (
    e: React.MouseEvent,
    roadmapId: string
  ) => {
    e.stopPropagation()
    setDeletingId(roadmapId)
    try {
      await deleteRoadmap(roadmapId)
      const remaining = roadmaps.filter((r) => r.id !== roadmapId)
      setRoadmaps(remaining)
      if (selectedRoadmapId === roadmapId) {
        setSelectedRoadmapId(remaining.length > 0 ? remaining[0].id : null)
      }
    } catch (err) {
      setFormError(
        err instanceof Error ? err.message : "Could not delete roadmap."
      )
    } finally {
      setDeletingId(null)
    }
  }

  const handleCompleteNode = async (nodeId: string) => {
    if (!selectedRoadmapId || completingNodeId) return
    setCompletingNodeId(nodeId)
    setCompletionError(null)
    try {
      const res = await completeRoadmapNode(nodeId)
      // Update roadmap progress in left sidebar immediately
      setRoadmaps((prev) =>
        prev.map((r) =>
          r.id === selectedRoadmapId
            ? {
                ...r,
                progress_percentage: res.progress_percentage,
                status: res.roadmap_status,
              }
            : r
        )
      )
      // Refresh tree while preserving expanded state + auto-expanding newly unlocked topic
      await loadSelectedRoadmapTree(selectedRoadmapId, true)

      // Also ensure any chapter containing a newly unlocked node is not collapsed
      if (res.unlocked_node_ids.length > 0 && activeTree) {
        const unlockedSet = new Set(res.unlocked_node_ids)
        for (const ch of activeTree.tree) {
          for (const tp of ch.children || []) {
            if (
              unlockedSet.has(tp.id) ||
              (tp.children || []).some((b) => unlockedSet.has(b.id))
            ) {
              setCollapsedChapterIds((prev) => ({
                ...prev,
                [ch.id]: false,
              }))
              setExpandedTopicIds((prev) => ({
                ...prev,
                [tp.id]: true,
              }))
            }
          }
        }
      }
    } catch (err) {
      setCompletionError(
        err instanceof Error
          ? err.message
          : "Could not mark study block as completed."
      )
    } finally {
      setCompletingNodeId(null)
    }
  }

  const toggleChapter = (chapterId: string) => {
    setCollapsedChapterIds((prev) => ({
      ...prev,
      [chapterId]: !prev[chapterId],
    }))
  }

  const toggleTopic = (topicId: string) => {
    setExpandedTopicIds((prev) => ({
      ...prev,
      [topicId]: !prev[topicId],
    }))
  }

  // Distinct documents referenced inside activeTree
  const activeTreeDocIds = React.useMemo(() => {
    if (!activeTree) return []
    const set = new Set<string>()
    for (const ch of activeTree.tree) {
      if (ch.document_id) set.add(ch.document_id)
      for (const tp of ch.children || []) {
        if (tp.document_id) set.add(tp.document_id)
        for (const blk of tp.children || []) {
          if (blk.document_id) set.add(blk.document_id)
        }
      }
    }
    return Array.from(set)
  }, [activeTree])

  // Aggregate counts for chapters, topics, and leaf study blocks
  const treeStats = React.useMemo(() => {
    if (!activeTree) {
      return {
        totalTopics: 0,
        totalBlocks: 0,
        completedBlocks: 0,
      }
    }
    let totalTopics = 0
    let totalBlocks = 0
    let completedBlocks = 0

    for (const ch of activeTree.tree) {
      const topics = ch.children || []
      totalTopics += topics.length
      for (const tp of topics) {
        const blocks = tp.children || []
        if (blocks.length > 0) {
          totalBlocks += blocks.length
          completedBlocks += blocks.filter((b) => b.is_completed).length
        } else {
          // Fallback when topic itself is a leaf node
          totalBlocks += 1
          if (tp.is_completed) completedBlocks += 1
        }
      }
    }

    return {
      totalTopics,
      totalBlocks,
      completedBlocks,
    }
  }, [activeTree])

  const progressPercent = React.useMemo(() => {
    if (!activeTree) return 0
    return Math.min(
      100,
      Math.max(0, Math.round(activeTree.roadmap.progress_percentage || 0))
    )
  }, [activeTree])

  return (
    <div className="flex-1 overflow-y-auto px-6 py-8 bg-[#F8FAFC] dark:bg-slate-950">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Page-Level Header & Control Bar */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 border-b border-slate-200/80 dark:border-slate-800/80 pb-5">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Subject Study Roadmaps
            </h1>
            <p className="text-xs sm:text-sm text-slate-500 dark:text-slate-400 max-w-2xl">
              Select a subject so AI can synthesize all assigned textbooks and
              lecture slides into a unified Chapter, Topic, and Study Block
              roadmap.
            </p>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => void loadRoadmapsList(false)}
              aria-label="Refresh roadmap list"
              className="h-9 px-3 rounded-xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-2 transition-colors cursor-pointer active:scale-[0.97]"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 stroke-[1.8] ${
                  isLoadingList ? "animate-spin" : ""
                }`}
              />
              <span>Refresh</span>
            </button>

            <button
              type="button"
              onClick={() => setIsFormExpanded((prev) => !prev)}
              className="h-9 px-3.5 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] text-white text-xs font-semibold inline-flex items-center gap-1.5 transition-colors cursor-pointer active:scale-[0.97] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
            >
              <Plus className="h-3.5 w-3.5 stroke-[2.2]" />
              <span>New Roadmap</span>
            </button>
          </div>
        </div>

        {/* Split Master-Detail Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* LEFT COLUMN (5 cols): Subject-Based Generator + Saved Roadmaps List */}
          <div className="lg:col-span-5 space-y-5">
            {/* 1. Roadmap Generator Card */}
            {isFormExpanded && (
              <section
                aria-label="Generate roadmap by subject"
                className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-5 shadow-2xs"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2.5">
                    <div className="h-8 w-8 rounded-lg bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 text-[#0A77FF] dark:text-sky-400 flex items-center justify-center shrink-0">
                      <Sparkles className="h-4 w-4 stroke-[2]" />
                    </div>
                    <div>
                      <h2 className="text-sm font-semibold text-slate-900 dark:text-white">
                        Synthesize Subject Roadmap
                      </h2>
                      <p className="text-[11px] text-slate-500 dark:text-slate-400">
                        Combine all PDF documents assigned to the selected
                        subject
                      </p>
                    </div>
                  </div>
                </div>

                <form onSubmit={handleCreateRoadmap} className="space-y-4">
                  {/* Subject Selector */}
                  <div className="space-y-1.5">
                    <label
                      htmlFor="roadmap-subject-select"
                      className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                    >
                      Subject
                    </label>

                    {subjects.length === 0 ? (
                      <div className="rounded-xl border border-dashed border-slate-200 dark:border-slate-800 p-3.5 text-center space-y-2">
                        <p className="text-xs text-slate-500">
                          No subjects created yet. Please create a subject in
                          the Documents tab first.
                        </p>
                        <button
                          type="button"
                          onClick={() => onSwitchToDocuments(null)}
                          className="h-8 px-3 rounded-lg bg-[#0A77FF]/10 text-[#0A77FF] text-xs font-semibold inline-flex items-center gap-1 cursor-pointer"
                        >
                          <FileText className="h-3.5 w-3.5" />
                          <span>Go to Documents</span>
                        </button>
                      </div>
                    ) : (
                      <select
                        id="roadmap-subject-select"
                        value={selectedSubjectId}
                        onChange={(e) =>
                          handleSubjectSelectChange(e.target.value)
                        }
                        className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs font-medium text-slate-900 dark:text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] cursor-pointer"
                      >
                        {subjects.map((subj) => (
                          <option key={subj.id} value={subj.id}>
                            {subj.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  {/* Roadmap Title */}
                  <div className="space-y-1.5">
                    <label
                      htmlFor="roadmap-title-input"
                      className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                    >
                      Roadmap Title
                    </label>
                    <input
                      id="roadmap-title-input"
                      type="text"
                      required
                      minLength={2}
                      maxLength={255}
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="e.g. Calculus 1 Study Plan"
                      className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                    />
                  </div>

                  {/* Target Date & Hours/Day Row */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <label
                        htmlFor="roadmap-target-date"
                        className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                      >
                        Target Completion Date
                      </label>
                      <input
                        id="roadmap-target-date"
                        type="date"
                        required
                        min={minTargetDate || undefined}
                        value={targetDate}
                        onChange={(e) => setTargetDate(e.target.value)}
                        className="w-full h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-3 text-xs font-mono text-slate-900 dark:text-slate-100 tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label
                        htmlFor="roadmap-hours-input"
                        className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                      >
                        Study Hours / Day
                      </label>
                      <div className="flex items-center gap-1.5">
                        <input
                          id="roadmap-hours-input"
                          type="number"
                          step="0.5"
                          min="0.5"
                          max="12"
                          required
                          value={hoursPerDay}
                          onChange={(e) =>
                            setHoursPerDay(
                              Math.min(
                                12,
                                Math.max(0.5, Number(e.target.value) || 0.5)
                              )
                            )
                          }
                          className="w-18 h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 px-2.5 text-xs font-mono font-semibold text-slate-900 dark:text-slate-100 tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF]"
                        />
                        <div className="flex items-center gap-1 flex-1">
                          {HOUR_PRESETS.map((preset) => (
                            <button
                              key={preset}
                              type="button"
                              onClick={() => setHoursPerDay(preset)}
                              className={`flex-1 h-9 rounded-lg text-[11px] font-mono font-medium transition-colors cursor-pointer tabular-nums ${
                                hoursPerDay === preset
                                  ? "bg-[#0A77FF]/12 text-[#0A77FF] dark:bg-[#0A77FF]/25 dark:text-sky-300 border border-[#0A77FF]/30 font-semibold"
                                  : "bg-slate-100 dark:bg-slate-800/80 text-slate-600 dark:text-slate-400 hover:bg-slate-200/70"
                              }`}
                            >
                              {preset}h
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Live Time Budget Calculation Pill */}
                  {timeBudgetStats && (
                    <div className="rounded-lg bg-slate-50 dark:bg-slate-950/90 border border-slate-200/70 dark:border-slate-800 px-3 py-2 flex items-center justify-between text-xs">
                      <span className="text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                        <Clock className="h-3.5 w-3.5 text-[#0A77FF]" />
                        <span>Available time budget:</span>
                      </span>
                      <span className="font-mono font-semibold text-slate-800 dark:text-slate-200 tabular-nums">
                        {timeBudgetStats.days}{" "}
                        {timeBudgetStats.days === 1 ? "day" : "days"} ·{" "}
                        {timeBudgetStats.totalHours}h (
                        {timeBudgetStats.totalMinutes.toLocaleString("en-US")}{" "}
                        min)
                      </span>
                    </div>
                  )}

                  {/* Optional Study Goal */}
                  <div className="space-y-1.5">
                    <label
                      htmlFor="roadmap-goal-input"
                      className="block text-xs font-medium text-slate-700 dark:text-slate-300"
                    >
                      Focus Goal{" "}
                      <span className="text-slate-400 font-normal">
                        (Optional)
                      </span>
                    </label>
                    <textarea
                      id="roadmap-goal-input"
                      rows={2}
                      value={studyGoal}
                      onChange={(e) => setStudyGoal(e.target.value)}
                      placeholder="e.g. Master core theory, prioritize final exam problem types..."
                      className="w-full rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950 p-2.5 text-xs text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] resize-none"
                    />
                  </div>

                  {formError && (
                    <div className="rounded-lg border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-3 py-2 text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                      <span>{formError}</span>
                    </div>
                  )}

                  {/* Primary CTA */}
                  <button
                    type="submit"
                    disabled={
                      isSubmitting ||
                      activeTask?.status === "processing" ||
                      subjects.length === 0
                    }
                    className="w-full h-10 rounded-xl bg-[#0A77FF] hover:bg-[#0866DF] disabled:opacity-50 disabled:pointer-events-none text-white text-xs font-semibold inline-flex items-center justify-center gap-2 transition-all duration-150 cursor-pointer active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0A77FF] focus-visible:ring-offset-2"
                  >
                    {isSubmitting || activeTask?.status === "processing" ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Synthesizing subject roadmap...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4 stroke-[2]" />
                        <span>Generate Roadmap</span>
                      </>
                    )}
                  </button>
                </form>
              </section>
            )}

            {/* 2. Saved Roadmaps List */}
            <section
              aria-label="Saved roadmaps list"
              className="space-y-2.5"
            >
              <div className="flex items-center justify-between px-1">
                <h2 className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Your Roadmaps
                </h2>
                <span className="text-xs font-mono text-slate-400 dark:text-slate-500 tabular-nums">
                  {roadmaps.length}{" "}
                  {roadmaps.length === 1 ? "roadmap" : "roadmaps"}
                </span>
              </div>

              {isLoadingList ? (
                <div className="space-y-2">
                  {[1, 2].map((n) => (
                    <div
                      key={n}
                      className="h-18 rounded-xl bg-slate-200/60 dark:bg-slate-900 animate-pulse"
                    />
                  ))}
                </div>
              ) : roadmaps.length === 0 ? (
                <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900/50 p-6 text-center">
                  <Compass className="h-5 w-5 text-slate-400 mx-auto mb-2 stroke-[1.75]" />
                  <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
                    No roadmaps generated yet
                  </p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Select a subject above to synthesize a personalized study
                    roadmap.
                  </p>
                </div>
              ) : (
                <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 divide-y divide-slate-200/70 dark:divide-slate-800/70 overflow-hidden">
                  {roadmaps.map((item) => {
                    const isSelected = item.id === selectedRoadmapId
                    const isDeleting = deletingId === item.id
                    const subj = subjectMap[item.subject_id]
                    const itemPct = Math.min(
                      100,
                      Math.max(0, Math.round(item.progress_percentage || 0))
                    )

                    return (
                      <div
                        key={item.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => setSelectedRoadmapId(item.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault()
                            setSelectedRoadmapId(item.id)
                          }
                        }}
                        className={`group flex items-center justify-between gap-3 px-4 py-3.5 transition-colors cursor-pointer focus-visible:outline-none ${
                          isSelected
                            ? "bg-[#0A77FF]/[0.07] dark:bg-[#0A77FF]/15"
                            : "hover:bg-slate-50 dark:hover:bg-slate-800/50"
                        }`}
                      >
                        <div className="min-w-0 flex-1 space-y-1.5">
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className={`h-2 w-2 rounded-full shrink-0 ${
                                  item.status === "completed" || itemPct >= 100
                                    ? "bg-emerald-500"
                                    : item.status === "active"
                                    ? "bg-[#0A77FF]"
                                    : item.status === "failed"
                                    ? "bg-rose-500"
                                    : "bg-[#0A77FF] animate-pulse"
                                }`}
                              />
                              <p
                                className={`text-xs font-semibold truncate ${
                                  isSelected
                                    ? "text-[#0A77FF] dark:text-sky-300"
                                    : "text-slate-900 dark:text-white"
                                }`}
                              >
                                {item.title}
                              </p>
                            </div>

                            <span
                              className={`text-[11px] font-mono font-semibold tabular-nums shrink-0 ${
                                itemPct >= 100
                                  ? "text-emerald-600 dark:text-emerald-400"
                                  : "text-slate-500 dark:text-slate-400"
                              }`}
                            >
                              {itemPct}%
                            </span>
                          </div>

                          <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400 dark:text-slate-500 tabular-nums pl-4 truncate">
                            {subj && (
                              <>
                                <span className="font-sans font-medium text-slate-500 dark:text-slate-400">
                                  {subj.name}
                                </span>
                                <span>·</span>
                              </>
                            )}
                            <span>Due: {formatShortDate(item.target_date)}</span>
                            <span>·</span>
                            <span>{item.available_hours_per_day}h/day</span>
                          </div>

                          {/* Mini Progress Bar */}
                          <div className="pl-4">
                            <div className="h-1 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                              <div
                                style={{ width: `${itemPct}%` }}
                                className={`h-full transition-all duration-300 ${
                                  itemPct >= 100
                                    ? "bg-emerald-500"
                                    : "bg-[#0A77FF]"
                                }`}
                              />
                            </div>
                          </div>
                        </div>

                        <button
                          type="button"
                          disabled={isDeleting}
                          onClick={(e) => void handleDeleteRoadmap(e, item.id)}
                          aria-label={`Delete ${item.title}`}
                          title="Delete roadmap"
                          className="h-7 w-7 rounded-lg flex items-center justify-center text-slate-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors cursor-pointer shrink-0"
                        >
                          {isDeleting ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5 stroke-[1.75]" />
                          )}
                        </button>
                      </div>
                    )
                  })}
                </div>
              )}
            </section>
          </div>

          {/* RIGHT COLUMN (7 cols): Live Pipeline Status + 3-Tier Curriculum & Study Blocks Viewer */}
          <div className="lg:col-span-7 space-y-4">
            {/* Active AI Generation Progress Banner */}
            {activeTask && (
              <div className="rounded-2xl border border-[#0A77FF]/30 bg-white dark:bg-slate-900 p-5 shadow-2xs space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2.5 min-w-0">
                    {activeTask.status === "completed" ? (
                      <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                    ) : activeTask.status === "failed" ? (
                      <AlertCircle className="h-4 w-4 text-rose-500 shrink-0" />
                    ) : (
                      <Loader2 className="h-4 w-4 text-[#0A77FF] animate-spin shrink-0" />
                    )}
                    <span className="text-xs font-semibold text-slate-900 dark:text-white truncate">
                      {activeTask.message}
                    </span>
                  </div>
                  <span className="text-xs font-mono font-semibold text-[#0A77FF] dark:text-sky-400 tabular-nums shrink-0">
                    {activeTask.progress_percent}%
                  </span>
                </div>

                <div className="h-1.5 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                  <div
                    style={{ width: `${activeTask.progress_percent}%` }}
                    className={`h-full transition-all duration-300 ${
                      activeTask.status === "failed"
                        ? "bg-rose-500"
                        : activeTask.status === "completed"
                        ? "bg-emerald-500"
                        : "bg-[#0A77FF]"
                    }`}
                  />
                </div>

                {activeTask.error && (
                  <p className="text-xs text-rose-600 dark:text-rose-400">
                    Error details: {activeTask.error}
                  </p>
                )}
              </div>
            )}

            {/* Main Roadmap Outline Viewer */}
            {isLoadingTree ? (
              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-12 flex flex-col items-center justify-center gap-2.5 text-slate-400">
                <Loader2 className="h-5 w-5 animate-spin text-[#0A77FF]" />
                <span className="text-xs font-medium">
                  Loading roadmap structure...
                </span>
              </div>
            ) : treeError ? (
              <div className="rounded-2xl border border-rose-200/80 dark:border-rose-900/60 bg-white dark:bg-slate-900 p-6 text-xs text-rose-600 dark:text-rose-400">
                {treeError}
              </div>
            ) : !activeTree ? (
              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 p-12 text-center space-y-2.5">
                <div className="h-11 w-11 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mx-auto">
                  <Network className="h-5 w-5 stroke-[1.75]" />
                </div>
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                  Select or generate a subject roadmap
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 max-w-md mx-auto leading-relaxed">
                  All PDF documents assigned to a subject will be synthesized by
                  AI into a 3-tier Chapter, Topic, and Study Block outline with
                  direct links to the exact document and page range.
                </p>
              </div>
            ) : (
              <div className="rounded-2xl border border-slate-200/80 dark:border-slate-800/80 bg-white dark:bg-slate-900 overflow-hidden shadow-2xs">
                {/* Roadmap Detail Header */}
                <div className="p-5 sm:p-6 border-b border-slate-200/80 dark:border-slate-800/80 space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        {subjectMap[activeTree.roadmap.subject_id] && (
                          <span className="rounded-md bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 px-2 py-0.5 text-[11px] font-semibold text-[#0A77FF] dark:text-sky-300">
                            {subjectMap[activeTree.roadmap.subject_id].name}
                          </span>
                        )}
                        {progressPercent >= 100 && (
                          <span className="rounded-md bg-emerald-500/10 dark:bg-emerald-500/20 px-2 py-0.5 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 inline-flex items-center gap-1">
                            <CheckCircle2 className="h-3 w-3" />
                            <span>Completed</span>
                          </span>
                        )}
                        <span className="text-xs font-mono text-slate-400 tabular-nums">
                          Synthesized from {Math.max(1, activeTreeDocIds.length)}{" "}
                          {Math.max(1, activeTreeDocIds.length) === 1
                            ? "document"
                            : "documents"}
                        </span>
                      </div>
                      <h2 className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">
                        {activeTree.roadmap.title}
                      </h2>
                    </div>

                    {activeTreeDocIds.length > 0 && (
                      <button
                        type="button"
                        onClick={() =>
                          onOpenDocumentAtPage(activeTreeDocIds[0], 1)
                        }
                        className="h-8 px-3 rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-medium text-slate-700 dark:text-slate-200 inline-flex items-center gap-1.5 transition-colors cursor-pointer shrink-0 active:scale-[0.97]"
                      >
                        <BookOpen className="h-3.5 w-3.5 text-[#0A77FF]" />
                        <span>Open Primary Document</span>
                      </button>
                    )}
                  </div>

                  {/* Overall Study Block Progress Bar */}
                  <div className="space-y-1.5 pt-0.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium text-slate-600 dark:text-slate-300 flex items-center gap-1.5">
                        <Layers className="h-3.5 w-3.5 text-[#0A77FF]" />
                        <span>Study Block Progress</span>
                      </span>
                      <span className="font-mono font-semibold text-slate-900 dark:text-white tabular-nums">
                        {treeStats.completedBlocks} / {treeStats.totalBlocks}{" "}
                        blocks ({progressPercent}%)
                      </span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                      <div
                        style={{ width: `${progressPercent}%` }}
                        className={`h-full transition-all duration-300 ${
                          progressPercent >= 100
                            ? "bg-emerald-500"
                            : "bg-[#0A77FF]"
                        }`}
                      />
                    </div>
                  </div>

                  {/* Single Aggregated Telemetry Strip (Tabular Nums) */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-1">
                    <div className="rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200/60 dark:border-slate-800/80 px-3 py-2">
                      <span className="block text-[11px] text-slate-400 dark:text-slate-500">
                        Curriculum Structure
                      </span>
                      <span className="text-sm font-mono font-semibold text-slate-900 dark:text-white tabular-nums">
                        {activeTree.tree.length} ch · {treeStats.totalTopics} tp{" "}
                        · {treeStats.totalBlocks} blk
                      </span>
                    </div>

                    <div className="rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200/60 dark:border-slate-800/80 px-3 py-2">
                      <span className="block text-[11px] text-slate-400 dark:text-slate-500">
                        Total Duration
                      </span>
                      <span className="text-sm font-mono font-semibold text-slate-900 dark:text-white tabular-nums">
                        {formatDuration(activeTree.total_estimated_minutes)}
                      </span>
                    </div>

                    <div className="rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200/60 dark:border-slate-800/80 px-3 py-2">
                      <span className="block text-[11px] text-slate-400 dark:text-slate-500">
                        Daily Pace
                      </span>
                      <span className="text-sm font-mono font-semibold text-slate-900 dark:text-white tabular-nums">
                        {activeTree.roadmap.available_hours_per_day} hrs / day
                      </span>
                    </div>

                    <div className="rounded-xl bg-slate-50 dark:bg-slate-950/70 border border-slate-200/60 dark:border-slate-800/80 px-3 py-2">
                      <span className="block text-[11px] text-slate-400 dark:text-slate-500">
                        Target Date
                      </span>
                      <span className="text-sm font-mono font-semibold text-slate-900 dark:text-white tabular-nums">
                        {formatShortDate(activeTree.roadmap.target_date)}
                      </span>
                    </div>
                  </div>

                  {completionError && (
                    <div className="rounded-xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/80 dark:bg-rose-950/40 px-3.5 py-2.5 text-xs text-rose-600 dark:text-rose-400 flex items-start gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
                      <span>{completionError}</span>
                    </div>
                  )}
                </div>

                {/* Hierarchical 3-Tier Chapters -> Topics -> Study Blocks Accordion List */}
                {activeTree.tree.length === 0 ? (
                  <div className="p-10 text-center space-y-2">
                    <Loader2 className="h-5 w-5 animate-spin text-[#0A77FF] mx-auto" />
                    <p className="text-xs font-medium text-slate-600 dark:text-slate-300">
                      Roadmap is still being generated or has no chapters yet...
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-slate-200/70 dark:divide-slate-800/70">
                    {activeTree.tree.map((chapter, chapterIdx) => {
                      const isCollapsed = Boolean(
                        collapsedChapterIds[chapter.id]
                      )
                      const chapterMinutes = computeChapterMinutes(chapter)
                      const topics = chapter.children || []
                      const chapterDocTitle = chapter.document_id
                        ? documentTitleMap[chapter.document_id]
                        : null

                      return (
                        <div
                          key={chapter.id}
                          className="bg-white dark:bg-slate-900"
                        >
                          {/* Level 1: Chapter Header Row */}
                          <div className="flex items-center justify-between gap-3 px-5 py-4 hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors">
                            <button
                              type="button"
                              onClick={() => toggleChapter(chapter.id)}
                              className="flex items-start gap-3 min-w-0 flex-1 text-left cursor-pointer focus-visible:outline-none"
                            >
                              <span className="mt-0.5 h-6 w-6 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 flex items-center justify-center shrink-0">
                                {isCollapsed ? (
                                  <ChevronRight className="h-3.5 w-3.5 stroke-[2]" />
                                ) : (
                                  <ChevronDown className="h-3.5 w-3.5 stroke-[2]" />
                                )}
                              </span>

                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-xs font-mono font-semibold text-[#0A77FF] dark:text-sky-400 tabular-nums">
                                    Chapter {chapterIdx + 1}
                                  </span>
                                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                                    {chapter.title}
                                  </h3>
                                  {chapter.is_completed && (
                                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                                  )}
                                </div>

                                {chapter.description && (
                                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 line-clamp-2 max-w-prose">
                                    {chapter.description}
                                  </p>
                                )}

                                <div className="flex items-center gap-2.5 flex-wrap text-[11px] font-mono text-slate-400 dark:text-slate-500 tabular-nums mt-1.5">
                                  {chapterDocTitle && (
                                    <>
                                      <span className="font-sans text-slate-500 dark:text-slate-400 truncate max-w-[220px]">
                                        {chapterDocTitle}
                                      </span>
                                      <span>·</span>
                                    </>
                                  )}
                                  {chapter.target_page_start &&
                                    chapter.target_page_end && (
                                      <span>
                                        Pages {chapter.target_page_start}–
                                        {chapter.target_page_end}
                                      </span>
                                    )}
                                  <span>·</span>
                                  <span>
                                    {topics.length}{" "}
                                    {topics.length === 1 ? "topic" : "topics"}
                                  </span>
                                  {chapterMinutes > 0 && (
                                    <>
                                      <span>·</span>
                                      <span>~{formatDuration(chapterMinutes)}</span>
                                    </>
                                  )}
                                </div>
                              </div>
                            </button>

                            {chapter.document_id &&
                              chapter.target_page_start && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    onOpenDocumentAtPage(
                                      chapter.document_id!,
                                      chapter.target_page_start!
                                    )
                                  }
                                  className="h-7 px-2.5 rounded-lg border border-slate-200/80 dark:border-slate-800 hover:border-[#0A77FF]/40 hover:text-[#0A77FF] text-[11px] font-mono font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-1 transition-colors cursor-pointer shrink-0 tabular-nums"
                                >
                                  <span>
                                    Page {chapter.target_page_start}
                                  </span>
                                  <ArrowUpRight className="h-3 w-3" />
                                </button>
                              )}
                          </div>

                          {/* Level 2: Topics List inside Chapter */}
                          {!isCollapsed && topics.length > 0 && (
                            <div className="bg-slate-50/60 dark:bg-slate-950/50 border-t border-slate-100 dark:border-slate-800/60 px-5 py-3 space-y-2.5">
                              {topics.map((topic, topicIdx) => {
                                const topicMinutes = computeTopicMinutes(topic)
                                const docId =
                                  topic.document_id ||
                                  chapter.document_id ||
                                  activeTreeDocIds[0]
                                const topicDocTitle = docId
                                  ? documentTitleMap[docId]
                                  : null
                                const studyBlocks = topic.children || []
                                const hasBlocks = studyBlocks.length > 0
                                const isTopicExpanded = Boolean(
                                  expandedTopicIds[topic.id]
                                )
                                const completedBlocksInTopic =
                                  studyBlocks.filter((b) => b.is_completed)
                                    .length
                                const hasActiveBlockInTopic = studyBlocks.some(
                                  (b) => b.is_unlocked && !b.is_completed
                                )

                                return (
                                  <div
                                    key={topic.id}
                                    className={`rounded-xl border transition-colors overflow-hidden ${
                                      hasActiveBlockInTopic
                                        ? "border-[#0A77FF]/35 bg-white dark:bg-slate-900 shadow-2xs"
                                        : "border-slate-200/70 dark:border-slate-800/80 bg-white dark:bg-slate-900"
                                    }`}
                                  >
                                    {/* Topic Header Row */}
                                    <div className="px-4 py-3 flex items-center justify-between gap-3">
                                      <button
                                        type="button"
                                        onClick={() =>
                                          hasBlocks && toggleTopic(topic.id)
                                        }
                                        className={`flex items-start gap-2.5 min-w-0 flex-1 text-left focus-visible:outline-none ${
                                          hasBlocks
                                            ? "cursor-pointer"
                                            : "cursor-default"
                                        }`}
                                      >
                                        {hasBlocks && (
                                          <span className="mt-0.5 h-5 w-5 rounded-md bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 flex items-center justify-center shrink-0">
                                            {isTopicExpanded ? (
                                              <ChevronDown className="h-3 w-3 stroke-[2]" />
                                            ) : (
                                              <ChevronRight className="h-3 w-3 stroke-[2]" />
                                            )}
                                          </span>
                                        )}

                                        <div className="min-w-0 flex-1 space-y-0.5">
                                          <div className="flex items-center gap-2 flex-wrap">
                                            <span className="text-[11px] font-mono font-semibold text-slate-400 dark:text-slate-500 tabular-nums shrink-0">
                                              {chapterIdx + 1}.{topicIdx + 1}
                                            </span>
                                            <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-100 truncate">
                                              {topic.title}
                                            </h4>
                                            {topic.is_completed ? (
                                              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 dark:bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400">
                                                <CheckCircle2 className="h-2.5 w-2.5" />
                                                <span>Done</span>
                                              </span>
                                            ) : hasActiveBlockInTopic ? (
                                              <span className="inline-flex items-center gap-1 rounded-md bg-[#0A77FF]/10 dark:bg-[#0A77FF]/20 px-1.5 py-0.5 text-[10px] font-semibold text-[#0A77FF] dark:text-sky-300">
                                                <span>In Progress</span>
                                              </span>
                                            ) : !topic.is_unlocked ? (
                                              <Lock className="h-3 w-3 text-slate-400 shrink-0" />
                                            ) : null}
                                          </div>

                                          {topic.description && (
                                            <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-1">
                                              {topic.description}
                                            </p>
                                          )}

                                          <div className="flex items-center gap-2 flex-wrap text-[11px] font-mono text-slate-400 dark:text-slate-500 tabular-nums pt-0.5">
                                            {topicDocTitle && (
                                              <>
                                                <span className="font-sans text-slate-500 dark:text-slate-400 truncate max-w-[200px]">
                                                  {topicDocTitle}
                                                </span>
                                                <span>·</span>
                                              </>
                                            )}
                                            {topic.target_page_start &&
                                              topic.target_page_end && (
                                                <span>
                                                  Pages {topic.target_page_start}–
                                                  {topic.target_page_end}
                                                </span>
                                              )}
                                            {topicMinutes > 0 && (
                                              <>
                                                <span>·</span>
                                                <span>
                                                  Est. {topicMinutes} min
                                                </span>
                                              </>
                                            )}
                                            {hasBlocks && (
                                              <>
                                                <span>·</span>
                                                <span
                                                  className={
                                                    completedBlocksInTopic ===
                                                    studyBlocks.length
                                                      ? "text-emerald-600 dark:text-emerald-400 font-semibold"
                                                      : "text-slate-600 dark:text-slate-300 font-semibold"
                                                  }
                                                >
                                                  {completedBlocksInTopic}/
                                                  {studyBlocks.length} blocks
                                                </span>
                                              </>
                                            )}
                                          </div>
                                        </div>
                                      </button>

                                      {/* Topic Right Actions */}
                                      <div className="flex items-center gap-2 shrink-0">
                                        {hasBlocks ? (
                                          <button
                                            type="button"
                                            onClick={() =>
                                              toggleTopic(topic.id)
                                            }
                                            className="h-7 px-2.5 rounded-lg border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-[11px] font-mono font-medium text-slate-600 dark:text-slate-300 inline-flex items-center gap-1 transition-colors cursor-pointer tabular-nums"
                                          >
                                            <span>
                                              {isTopicExpanded
                                                ? "Hide blocks"
                                                : `View ${studyBlocks.length} ${
                                                    studyBlocks.length === 1
                                                      ? "block"
                                                      : "blocks"
                                                  }`}
                                            </span>
                                          </button>
                                        ) : (
                                          // Fallback when Topic has no child Study Blocks (2-tier legacy tree)
                                          <>
                                            {docId &&
                                              topic.target_page_start &&
                                              (topic.is_unlocked ||
                                                topic.is_completed) && (
                                                <button
                                                  type="button"
                                                  onClick={() =>
                                                    onOpenDocumentAtPage(
                                                      docId,
                                                      topic.target_page_start!
                                                    )
                                                  }
                                                  className="h-7 px-2.5 rounded-lg bg-[#0A77FF]/10 hover:bg-[#0A77FF]/15 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300 text-[11px] font-medium inline-flex items-center gap-1 transition-colors cursor-pointer shrink-0 active:scale-[0.97] tabular-nums"
                                                >
                                                  <span>
                                                    Read p.
                                                    {topic.target_page_start}
                                                  </span>
                                                  <ArrowUpRight className="h-3 w-3" />
                                                </button>
                                              )}
                                            {topic.is_unlocked &&
                                              !topic.is_completed && (
                                                <button
                                                  type="button"
                                                  disabled={
                                                    completingNodeId ===
                                                    topic.id
                                                  }
                                                  onClick={() =>
                                                    void handleCompleteNode(
                                                      topic.id
                                                    )
                                                  }
                                                  className="h-7 px-2.5 rounded-lg bg-[#0A77FF] hover:bg-[#0866DF] disabled:opacity-50 text-white text-[11px] font-semibold inline-flex items-center gap-1 transition-colors cursor-pointer shrink-0 active:scale-[0.97]"
                                                >
                                                  {completingNodeId ===
                                                  topic.id ? (
                                                    <Loader2 className="h-3 w-3 animate-spin" />
                                                  ) : (
                                                    <Check className="h-3 w-3 stroke-[2.2]" />
                                                  )}
                                                  <span>Complete</span>
                                                </button>
                                              )}
                                          </>
                                        )}
                                      </div>
                                    </div>

                                    {/* Level 3: Study Blocks Vertical Stepper inside Topic */}
                                    {hasBlocks && isTopicExpanded && (
                                      <div className="border-t border-slate-100 dark:border-slate-800/70 bg-slate-50/50 dark:bg-slate-950/60 px-4 py-3">
                                        <div className="border-l-2 border-slate-200 dark:border-slate-800 ml-2.5 pl-3.5 space-y-2">
                                          {studyBlocks.map(
                                            (block, blockIdx) => {
                                              const blockDocId =
                                                block.document_id ||
                                                topic.document_id ||
                                                chapter.document_id ||
                                                activeTreeDocIds[0]
                                              const blockDocTitle = blockDocId
                                                ? documentTitleMap[blockDocId]
                                                : null
                                              const isCompleted =
                                                block.is_completed
                                              const isUnlocked =
                                                block.is_unlocked &&
                                                !block.is_completed
                                              const isLocked =
                                                !block.is_unlocked &&
                                                !block.is_completed
                                              const isCompleting =
                                                completingNodeId === block.id

                                              return (
                                                <div
                                                  key={block.id}
                                                  className={`rounded-xl border px-3.5 py-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 transition-colors ${
                                                    isUnlocked
                                                      ? "border-[#0A77FF]/40 bg-[#0A77FF]/[0.04] dark:bg-[#0A77FF]/10"
                                                      : isCompleted
                                                      ? "border-emerald-200/70 dark:border-emerald-900/40 bg-white dark:bg-slate-900"
                                                      : "border-slate-200/60 dark:border-slate-800/60 bg-slate-100/60 dark:bg-slate-900/40 opacity-65"
                                                  }`}
                                                >
                                                  <div className="flex items-start gap-2.5 min-w-0 flex-1">
                                                    <span className="mt-0.5 shrink-0">
                                                      {isCompleted ? (
                                                        <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                                                      ) : isUnlocked ? (
                                                        <PlayCircle className="h-4 w-4 text-[#0A77FF] dark:text-sky-400" />
                                                      ) : (
                                                        <Lock className="h-3.5 w-3.5 text-slate-400 mt-0.5" />
                                                      )}
                                                    </span>

                                                    <div className="min-w-0 flex-1 space-y-0.5">
                                                      <div className="flex items-center gap-2 flex-wrap">
                                                        <span className="text-[11px] font-mono font-semibold text-slate-400 dark:text-slate-500 tabular-nums">
                                                          Block {blockIdx + 1}
                                                        </span>
                                                        <p className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate">
                                                          {block.title}
                                                        </p>
                                                        {isUnlocked && (
                                                          <span className="rounded bg-[#0A77FF] px-1.5 py-0.2 text-[10px] font-semibold text-white">
                                                            Current Session
                                                          </span>
                                                        )}
                                                      </div>

                                                      {block.description && (
                                                        <p className="text-[11px] text-slate-500 dark:text-slate-400 line-clamp-1">
                                                          {block.description}
                                                        </p>
                                                      )}

                                                      <div className="flex items-center gap-2 flex-wrap text-[11px] font-mono text-slate-400 dark:text-slate-500 tabular-nums">
                                                        {blockDocTitle && (
                                                          <>
                                                            <span className="font-sans text-slate-500 dark:text-slate-400 truncate max-w-[180px]">
                                                              {blockDocTitle}
                                                            </span>
                                                            <span>·</span>
                                                          </>
                                                        )}
                                                        {block.target_page_start &&
                                                          block.target_page_end && (
                                                            <span>
                                                              Pages{" "}
                                                              {
                                                                block.target_page_start
                                                              }
                                                              –
                                                              {
                                                                block.target_page_end
                                                              }
                                                            </span>
                                                          )}
                                                        <span>·</span>
                                                        <span>
                                                          {block.estimated_minutes ||
                                                            25}{" "}
                                                          min
                                                        </span>
                                                        {isLocked && (
                                                          <>
                                                            <span>·</span>
                                                            <span className="font-sans text-slate-400">
                                                              Complete previous
                                                              block to unlock
                                                            </span>
                                                          </>
                                                        )}
                                                      </div>
                                                    </div>
                                                  </div>

                                                  {/* Study Block Actions */}
                                                  <div className="flex items-center gap-1.5 shrink-0 self-end sm:self-center">
                                                    {blockDocId &&
                                                      block.target_page_start &&
                                                      (isUnlocked ||
                                                        isCompleted) && (
                                                        <button
                                                          type="button"
                                                          onClick={() =>
                                                            onOpenDocumentAtPage(
                                                              blockDocId,
                                                              block.target_page_start!
                                                            )
                                                          }
                                                          className={`h-7 px-2.5 rounded-lg text-[11px] font-mono font-medium inline-flex items-center gap-1 transition-colors cursor-pointer active:scale-[0.97] tabular-nums ${
                                                            isUnlocked
                                                              ? "bg-[#0A77FF]/10 hover:bg-[#0A77FF]/18 text-[#0A77FF] dark:bg-[#0A77FF]/20 dark:text-sky-300"
                                                              : "border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300"
                                                          }`}
                                                        >
                                                          <span>
                                                            {isCompleted
                                                              ? `Review p.${block.target_page_start}`
                                                              : `Read p.${block.target_page_start}`}
                                                          </span>
                                                          <ArrowUpRight className="h-3 w-3" />
                                                        </button>
                                                      )}

                                                    {isUnlocked && (
                                                      <button
                                                        type="button"
                                                        disabled={isCompleting}
                                                        onClick={() =>
                                                          void handleCompleteNode(
                                                            block.id
                                                          )
                                                        }
                                                        className="h-7 px-2.5 rounded-lg bg-[#0A77FF] hover:bg-[#0866DF] disabled:opacity-50 text-white text-[11px] font-semibold inline-flex items-center gap-1 transition-colors cursor-pointer active:scale-[0.97]"
                                                      >
                                                        {isCompleting ? (
                                                          <Loader2 className="h-3 w-3 animate-spin" />
                                                        ) : (
                                                          <Check className="h-3 w-3 stroke-[2.2]" />
                                                        )}
                                                        <span>Complete</span>
                                                      </button>
                                                    )}

                                                    {isCompleted && (
                                                      <span className="h-7 px-2 rounded-lg bg-emerald-500/10 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-[11px] font-semibold inline-flex items-center gap-1">
                                                        <Check className="h-3 w-3 stroke-[2.2]" />
                                                        <span>Done</span>
                                                      </span>
                                                    )}
                                                  </div>
                                                </div>
                                              )
                                            }
                                          )}
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
