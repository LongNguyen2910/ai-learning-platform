export interface RoadmapNode {
  id: string;
  roadmap_id: string;
  parent_node_id: string | null;
  document_id: string | null;
  title: string;
  description: string | null;
  order_index: number;
  target_page_start: number | null;
  target_page_end: number | null;
  estimated_minutes: number;
  is_unlocked: boolean;
  is_completed: boolean;
  completed_at: string | null;
  children: RoadmapNode[];
}

export interface Roadmap {
  id: string;
  roadmap_id?: string;
  user_id: string;
  subject_id: string;
  title: string;
  target_date: string | null;
  available_hours_per_day: number;
  progress_percentage: number;
  status: "active" | "completed" | "behind_schedule" | "generating" | "failed";
  created_at: string;
}

export interface RoadmapTreeResponse {
  roadmap: Roadmap;
  tree: RoadmapNode[];
  total_nodes: number;
  total_estimated_minutes: number;
}

export interface RoadmapGenerateRequest {
  subject_id: string;
  document_id: string;
  title: string;
  target_date: string;
  available_hours_per_day: number;
  study_goal?: string;
}

export interface RoadmapTaskStatusResponse {
  task_id: string;
  roadmap_id: string | null;
  status: "processing" | "completed" | "failed";
  progress_percent: number;
  message: string;
  error?: string | null;
}
