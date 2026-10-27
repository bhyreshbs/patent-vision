export const VIEW_TYPES = ["Front", "Rear", "Left", "Right", "Top", "Bottom", "Other"] as const;
export type ViewType = (typeof VIEW_TYPES)[number];

export type ImageStatus = "Uploaded" | "Queued" | "Processing" | "Completed" | "Failed";

export interface User {
  id: number;
  name: string;
  email: string;
}

export interface Project {
  id: number;
  name: string;
  description: string;
  status: string;
  created_at: string;
  updated_at: string;
  image_count: number;
  status_counts: Partial<Record<ImageStatus, number>>;
}

export interface Meta {
  max_upload_bytes: number;
  accepted_types: string[];
  storage: "blob" | "local";
}

export interface ResultUrls {
  drawing: string | null;
  svg: string | null;
  background_removed: string | null;
  mask: string | null;
  outline: string | null;
  original: string;
}

export interface AiResult {
  id: number;
  image_id: number;
  status: ImageStatus;
  error_message: string | null;
  failed_stage: string | null;
  metrics: Record<string, unknown> | null;
  updated_at: string;
  urls: ResultUrls;
}

export interface Job {
  id: number;
  job_status: ImageStatus;
  error_message: string | null;
  failed_stage: string | null;
  retry_count: number;
}

export interface ImageItem {
  id: number;
  project_id: number;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  width: number;
  height: number;
  view_type: ViewType;
  processing_status: ImageStatus;
  created_at: string;
  original_url: string;
  result: AiResult | null;
  job: Job | null;
}

export interface Dashboard {
  project_count: number;
  image_count: number;
  status_counts: Partial<Record<ImageStatus, number>>;
  recent_projects: Project[];
  recent_results: ImageItem[];
}
