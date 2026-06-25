// TypeScript types 對應 server/schemas.py 的 Pydantic models
// 改 schema 時兩邊要同步, 之後可考慮 OpenAPI -> TS 自動產生

export type SourceType =
  | 'exam_pdf'
  | 'slides_pdf'
  | 'repo'
  | 'document'
  | 'url'
  | 'song';   // SONG track (M3): 歌曲音檔 + 歌詞 → 對齊 → AI 生圖 → MV

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
  /** 缺圖簡報補圖 (只對 slides_pdf): 為缺圖頁生 AI 配圖並合成新頁. 預設 false. */
  augment_slide_images?: boolean;
  /** augment_slide_images 開啟時: true 只補偵測到的缺圖頁; false 每頁都生. 預設 true. */
  augment_only_missing?: boolean;
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
  // iter 52: PDF figure 配圖 id (例 "fig_p3_1") 或 null. iter 53 runner 渲染前
  // 會轉成絕對路徑, 但 deck.json 跟 UI 都看 id.
  image_path?: string | null;
}

// iter 54: jobs/{id}/figures route 回的單張 figure metadata
export interface JobFigure {
  id: string;                    // "fig_p3_1"
  page_no: number;
  path: string;                  // "fig_p3_1.png"
  width: number;
  height: number;
  caption_hint: string;
  url: string;                   // "/jobs/{id}/figures/fig_p3_1.png"
}

export interface JobFiguresResponse {
  figures: JobFigure[];
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

// ---------- Song schema (SONG track, M3 用) ----------
// 對應 core.song_render.is_song_schema (track_type==='song' + segments list) 與
// server runner / core.youtube 消費的 song.json 欄位。改這裡要同步 song.json 結構。

export interface SongSegment {
  /** 段落 id (生圖檔名 seg_<id>.png 用); 可選 */
  id?: string;
  /** 對齊好的絕對起點 (秒) */
  start: number;
  /** 對齊好的絕對終點 (秒, 須 > start 否則渲染端跳過) */
  end: number;
  /** 歌詞行 (一段可多行, 渲染時併進同一 SRT cue) */
  lines: string[];
  /** AI 生圖路徑 (相對 job dir, 如 "images/seg_s1.png") 或 null */
  image_path?: string | null;
  /** 生圖 prompt (人工修過則 idempotent 不被覆蓋) */
  image_prompt?: string | null;
  /** AI 生圖是估值, 須人工 review 後才標 true (硬規則 #1) */
  reviewed?: boolean | null;
}

export interface SongDeck {
  /** 區分 song schema 的標記 (硬規則 #9 type guard 用, 不靠 'segments' in d 硬判) */
  track_type: 'song';
  song_title?: string;
  /** 後端 title fallback 鏈會看 deck_title */
  deck_title?: string;
  source_type?: string;
  /** 歌曲音檔 (ingest 後相對 job dir, 如 "song.mp3") */
  audio_path?: string | null;
  /** 統一視覺風格 (逐段生圖共用, 保畫風一致) */
  visual_style?: string | null;
  segments: SongSegment[];
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
 * 共通的 draft 型別: 後端 GET /jobs/{id}/draft 回 dict, 可能是 Exam / Deck / Song。
 * UI 用 isExamDraft / isDeckDraft / isSongDraft 三個 type guard 分流。
 */
export type Draft = Exam | Deck | SongDeck | Record<string, unknown>;

export function isExamDraft(d: unknown): d is Exam {
  return !!d && typeof d === 'object' && Array.isArray((d as any).problems);
}

export function isDeckDraft(d: unknown): d is Deck {
  return !!d && typeof d === 'object' && Array.isArray((d as any).sections);
}

// 比照 core.song_render.is_song_schema: track_type==='song' + segments list。
// song deck 無 problems / sections, 故與 isExamDraft / isDeckDraft 不會誤判互撞。
export function isSongDraft(d: unknown): d is SongDeck {
  return (
    !!d &&
    typeof d === 'object' &&
    (d as any).track_type === 'song' &&
    Array.isArray((d as any).segments)
  );
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

// POST /proposals/scan-folder 觸發 ideate 跑一輪
export interface ScanFolderRequest {
  folder: string;
  source_type?: 'auto' | 'exam_pdf' | 'slides_pdf' | 'document';
  scan_window_days?: number;
  max_proposals_per_file?: number;
}

export interface ScanResponse {
  ok: boolean;
  scanned: number;
  proposed: number;
  new: number;
  error?: string | null;
}

// iter 33-34: async scan + status polling
export interface ScanAsyncResponse {
  scan_id: string;
}

// ---------- E2-6 icon suggestions (iter 107 backend, iter 110 wrapper) ----------

export interface IconSuggestion {
  key: string;
  icon: string;              // 絕對路徑 (Path → str), 給 <img src> 用前要拼 / 處理
  matched_keyword: string;
  position: string;          // top-left | top-right | bottom-left | bottom-right | center
  size_ratio: number;
  domain: string;            // generic | wind | control | mechanics
  file_exists: boolean;      // E2-2 SVG 還沒進 repo 時 false, UI 該 grey-out
}

export interface IconSuggestionsResponse {
  suggestions: Record<string, IconSuggestion[]>;
}

// ---------- E1-4 image frames summary (iter 109 backend, iter 110 wrapper) ----------

export interface ImageFrameSummary {
  count: number;
  terminal_path: string | null;   // PNG 路徑 (Path → str), null 表沒 frame
  has_frames: boolean;
}

export interface ImageFramesSummaryResponse {
  summary: Record<string, ImageFrameSummary>;
}

export type ScanState = 'running' | 'done' | 'failed';

export interface ScanStatusResponse {
  state: ScanState;
  scanned: number;
  proposed: number;
  new: number;
  error?: string | null;
  message: string;            // 最近一條 progress 訊息
  started_at?: string | null;
  ended_at?: string | null;
}
