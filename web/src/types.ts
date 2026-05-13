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
  /** PR-5a: pptx 主題 (forest / navy). 只影響 repo / document / url. */
  theme?: string | null;
  /** PR-5c: 是否把 SRT 字幕燒進 MP4. 預設 false. */
  hardsub?: boolean;
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
  // PR-3f: YouTube 上傳記錄, key 是 artifact name (例如 "q1.mp4")
  youtube_uploads?: Record<string, YoutubeUpload>;
}

// ---------- YouTube upload (PR-3f) ----------

export type YoutubeUploadState = 'pending' | 'uploading' | 'done' | 'failed';

export interface YoutubeUpload {
  state: YoutubeUploadState;
  title: string;
  description: string;
  tags: string[];
  privacy: string;        // "unlisted" | "public" | "private"
  category: string;       // "27" = Education
  video_id?: string | null;
  url?: string | null;
  caption_id?: string | null;
  progress_percent: number;  // 0~100
  started_at?: string | null;
  uploaded_at?: string | null;
  error?: string | null;
  caption_error?: string | null;
}

export interface YoutubeMeta {
  title: string;
  description: string;
  tags: string[];
  privacy: string;
  category: string;
}

export interface PublishRequest {
  title: string;
  description?: string;
  tags?: string[];
  privacy?: string;
  category?: string;
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
  // PR-3h: slides_pdf 的 deck schema 帶這三個欄位 (其他 source 為 undefined)
  bg_image?: string | null;
  bg_type?: string | null;       // "slide" | undefined
  layout?: string | null;         // "full" | "split-left" (Phase 4 預留)
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

// ---------- v1 exam schema (考卷 / 簡報 用, PR-3g 接 React UI) ----------

export interface Step {
  /** Gemini 自我分類 meta, UI 不依賴它做判斷, 但顯示給 reviewer 看 */
  _section?: string | null;
  /** 黑板顯示 (≤40 字精煉) */
  display: string;
  /** 老師口語旁白 (60~180 字) */
  narration: string;
  /** 此步驟覆蓋的圖片 (選填) */
  image?: string | null;
  /** 投影片模式: bg_type=slide + bg_image 投影片路徑 (slides_pdf 用) */
  bg_type?: string | null;
  bg_image?: string | null;
  layout?: string | null;
}

export interface Problem {
  id: string;
  number: string;
  score?: number;
  /** 題目原文 */
  problem: string;
  steps: Step[];
}

export interface Exam {
  exam_title: string;
  /** 用來區分 v1 exam (problems) vs deck schema (sections) */
  source_type?: string;
  source_meta?: Record<string, unknown>;
  problems: Problem[];
}

/**
 * 共通的 draft 型別: 後端 GET /jobs/{id}/draft 回 dict, 可能是 Exam 或 Deck。
 * UI 用 isExamDraft / isDeckDraft 兩個 type guard 分流。
 */
export type Draft = Exam | Deck | Record<string, unknown>;

export function isExamDraft(d: unknown): d is Exam {
  return !!d && typeof d === 'object' && Array.isArray((d as any).problems);
}

export function isDeckDraft(d: unknown): d is Deck {
  return !!d && typeof d === 'object' && Array.isArray((d as any).sections);
}

// ---------- Voice picker (PR-3l) ----------

export interface VoiceInfo {
  id: string;
  label: string;
  sample_url: string;
}

export interface VoiceListResponse {
  voices: VoiceInfo[];
  current: string;
}

// ---------- Library (PR-3m) ----------

export interface LibraryItem {
  job_id: string;
  artifact_name: string;       // "q1.mp4" / "ch1.mp4"
  source_type: SourceType;
  deck_title: string;
  mp4_size_bytes: number;
  srt_exists: boolean;
  youtube?: YoutubeUpload | null;
  artifact_url: string;        // /jobs/{id}/artifacts/{name}
  publish_url: string;         // /ui/jobs/{id}/publish/{name}
}

export interface LibraryResponse {
  items: LibraryItem[];
  total: number;
}

// ---------- Job log (PR-4c) ----------

export interface LogEntry {
  ts: string;
  level: string;       // INFO / WARNING / ERROR / DEBUG / RAW
  logger?: string;
  msg: string;
  job_id?: string;
  stage?: string;
  exc?: string;
  [key: string]: unknown;   // 其他 extra 欄位 (step_idx 等)
}

export interface JobLogResponse {
  entries: LogEntry[];
}

// ---------- Proposals (v4 階段 2 B ideate.py) ----------

export type ProposalStatus = 'pending' | 'approved' | 'ignored' | 'expired';

export interface Proposal {
  id: string;
  generated_at: string;
  source_file: string;
  source_type: SourceType;
  suggested_title: string;
  suggested_chapters: string[];
  reason: string;
  estimated_duration_min: number;
  status: ProposalStatus;
  job_id?: string | null;
}

export interface ProposalListResponse {
  proposals: Proposal[];
}

export interface ProposalApproveResponse {
  proposal: Proposal;
  job: CreateJobResponse;
}

// POST /proposals/scan 觸發 ideate 跑一輪
export interface ScanResponse {
  ok: boolean;
  scanned: number;
  proposed: number;
  new: number;
  error?: string | null;
}
