// 純 fetch 包裝, 對齊 server/routes/jobs.py 的端點。
// 不上 tanstack-query, 因為 v0 互動量少, useState + useEffect 已足夠。

import type {
  CreateJobRequest,
  CreateJobResponse,
  Deck,
  JobLogResponse,
  JobOptions,
  JobRecord,
  LibraryResponse,
  Proposal,
  ProposalApproveResponse,
  ProposalListResponse,
  ScanAsyncResponse,
  ScanFolderRequest,
  ScanResponse,
  ScanStatusResponse,
  PublishRequest,
  SourceType,
  VoiceListResponse,
  YoutubeMeta,
  YoutubeUpload,
} from './types';

class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`HTTP ${status}: ${detail}`);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!r.ok) {
    const text = await r.text().catch(() => '');
    throw new ApiError(r.status, text || r.statusText);
  }
  // DELETE / 204 沒 body
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export const api = {
  health: () => call<{ status: string }>('/health'),

  listJobs: () => call<{ jobs: JobRecord[] }>('/jobs'),

  getJob: (jobId: string) => call<JobRecord>(`/jobs/${jobId}`),

  createJob: (req: CreateJobRequest) =>
    call<CreateJobResponse>('/jobs', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  deleteJob: (jobId: string) =>
    call<void>(`/jobs/${jobId}`, { method: 'DELETE' }),

  getDraft: (jobId: string) => call<Deck>(`/jobs/${jobId}/draft`),

  saveDraft: (jobId: string, deck: Deck) =>
    call<JobRecord>(`/jobs/${jobId}/draft`, {
      method: 'PUT',
      body: JSON.stringify({ deck }),
    }),

  approve: (jobId: string) =>
    call<JobRecord>(`/jobs/${jobId}/approve`, { method: 'POST' }),

  /** PR-4a: 重新渲染單一 section / problem (整章 mp4 換新, 其他章不動)。 */
  renderSection: (jobId: string, sectionId: string) =>
    call<JobRecord>(
      `/jobs/${jobId}/sections/${encodeURIComponent(sectionId)}/render`,
      { method: 'POST' },
    ),

  // artifact download URL — 給 <a href> 直接用, 不走 fetch
  artifactUrl: (jobId: string, name: string) =>
    `/jobs/${jobId}/artifacts/${encodeURIComponent(name)}`,

  // ---------- YouTube (PR-3f) ----------

  getYoutubeMeta: (jobId: string, name: string) =>
    call<YoutubeMeta>(
      `/jobs/${jobId}/artifacts/${encodeURIComponent(name)}/youtube_meta`,
    ),

  publish: (jobId: string, name: string, req: PublishRequest) =>
    call<YoutubeUpload>(
      `/jobs/${jobId}/artifacts/${encodeURIComponent(name)}/publish`,
      {
        method: 'POST',
        body: JSON.stringify(req),
      },
    ),

  youtubeStatus: (jobId: string, name: string) =>
    call<YoutubeUpload>(
      `/jobs/${jobId}/artifacts/${encodeURIComponent(name)}/youtube_status`,
    ),

  // ---------- Slide images (PR-3h) ----------

  /** 投影片 PNG 縮圖 URL — slide.bg_image 是 "slides/<stem>/p001.png" 形式,
   * 拆出 stem + filename 餵給 /slide_images endpoint。給 <img src> 直接用。
   * 找不到合法路徑回 null (例: bg_image 是 absolute / 不是 slides/ 開頭)。 */
  slideImageUrl: (bgImage: string | null | undefined): string | null => {
    if (!bgImage) return null;
    const norm = bgImage.replace(/\\/g, '/');
    const m = norm.match(/^slides\/([^/]+)\/([^/]+)$/);
    if (!m) return null;
    return `/slide_images/${encodeURIComponent(m[1])}/${encodeURIComponent(m[2])}`;
  },

  // ---------- Upload (PR-3k) ----------

  /** 上傳檔案 + 建 job. 不走 call() 因為 multipart 不能 set Content-Type 為 JSON. */
  uploadFile: async (
    file: File,
    sourceType: SourceType,
    options: JobOptions,
  ): Promise<CreateJobResponse> => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('source_type', sourceType);
    fd.append('options_json', JSON.stringify(options));
    const r = await fetch('/upload', { method: 'POST', body: fd });
    if (!r.ok) {
      const text = await r.text().catch(() => '');
      throw new ApiError(r.status, text || r.statusText);
    }
    return r.json() as Promise<CreateJobResponse>;
  },

  // ---------- Voice picker (PR-3l) ----------

  getVoices: () => call<VoiceListResponse>('/voices'),

  setVoice: (voiceId: string) =>
    call<VoiceListResponse>('/voices', {
      method: 'POST',
      body: JSON.stringify({ voice_id: voiceId }),
    }),

  /** 試聽 sample mp3 URL — 給 <audio src> 用. */
  voiceSampleUrl: (voiceId: string) =>
    `/voices/${encodeURIComponent(voiceId)}/sample`,

  // ---------- Library (PR-3m) ----------

  getLibrary: () => call<LibraryResponse>('/library'),

  // ---------- Job log (PR-4c) ----------

  /** 拉 jobs/<id>/log.jsonl 末尾 N 行 (預設 200). */
  getJobLog: (jobId: string, tail = 200) =>
    call<JobLogResponse>(`/jobs/${jobId}/log?tail=${tail}`),

  // ---------- Proposals (v4 階段 2 B ideate) ----------

  listProposals: (onlyPending = true) =>
    call<ProposalListResponse>(
      `/proposals?only_pending=${onlyPending ? 'true' : 'false'}`,
    ),

  // iter 40/41/43: optional body — 讓 UI 在核准前選主題 / 串 intro / 長度模式
  approveProposal: (
    proposalId: string,
    options?: {
      theme?: string;
      hardsub?: boolean;
      prepend_intro?: boolean;
      length_mode?: string;
    },
  ) =>
    call<ProposalApproveResponse>(
      `/proposals/${encodeURIComponent(proposalId)}/approve`,
      {
        method: 'POST',
        headers: options ? { 'Content-Type': 'application/json' } : undefined,
        body: options ? JSON.stringify(options) : undefined,
      },
    ),

  ignoreProposal: (proposalId: string) =>
    call<Proposal>(
      `/proposals/${encodeURIComponent(proposalId)}/ignore`,
      { method: 'PATCH' },
    ),

  /** 觸發 ideate 掃單一資料夾 (UI 模式, iter 27 取代 yaml). 同步等完成. */
  scanFolder: (req: ScanFolderRequest) =>
    call<ScanResponse>(`/proposals/scan-folder`, {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  /** iter 34: 非同步版 — 立刻回 scan_id, UI poll status 看進度. */
  scanFolderAsync: (req: ScanFolderRequest) =>
    call<ScanAsyncResponse>(`/proposals/scan-folder/async`, {
      method: 'POST',
      body: JSON.stringify(req),
    }),

  getScanStatus: (scanId: string) =>
    call<ScanStatusResponse>(
      `/proposals/scan-status/${encodeURIComponent(scanId)}`,
    ),
};

export { ApiError };
