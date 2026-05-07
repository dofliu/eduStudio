// TypeScript types 對應 server/schemas.py 的 Pydantic models
// 改 schema 時兩邊要同步, 之後可考慮 OpenAPI -> TS 自動產生

export type SourceType =
  | 'exam_pdf'
  | 'slides_pdf'
  | 'repo'
  | 'document'
  | 'url';

export type JobState =
  | 'pending'
  | 'ingesting'
  | 'awaiting_review'
  | 'rendering'
  | 'done'
  | 'failed';

export interface JobSource {
  path?: string | null;
  url?: string | null;
}

export interface JobOptions {
  require_review?: boolean | null;
  tts_provider?: string | null;
  output_name?: string | null;
  mock?: boolean;
  max_files?: number | null;
}

export interface StageInfo {
  name: string;
  state: string;
  started_at?: string | null;
  ended_at?: string | null;
  error?: string | null;
}

export interface Artifact {
  name: string;
  path: string;
  size_bytes: number;
  kind: string;
}

export interface JobRecord {
  id: string;
  source_type: SourceType;
  source: JobSource;
  options: JobOptions;
  state: JobState;
  created_at: string;
  updated_at: string;
  stages: StageInfo[];
  artifacts: Artifact[];
  error?: string | null;
  deck_path?: string | null;
  output_dir?: string | null;
}

export interface CreateJobRequest {
  source_type: SourceType;
  source: JobSource;
  options?: JobOptions;
}

export interface CreateJobResponse {
  job_id: string;
  state: JobState;
  status_url: string;
}

// ---------- Deck schema (新版, repo / document / url 用) ----------

export interface Slide {
  id: string;
  title: string;
  bullets: string[];
  code_snippet?: string | null;
  code_lang?: string | null;
  file_path?: string | null;
  narration: string;
  notes?: string | null;
}

export interface Section {
  id: string;
  title: string;
  slides: Slide[];
}

export interface Deck {
  deck_title: string;
  source_type: string;
  source_meta?: Record<string, unknown>;
  sections: Section[];
}
