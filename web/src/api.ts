// 純 fetch 包裝, 對齊 server/routes/jobs.py 的端點。
// 不上 tanstack-query, 因為 v0 互動量少, useState + useEffect 已足夠。

import type {
  CreateJobRequest,
  CreateJobResponse,
  Deck,
  JobRecord,
  PublishRequest,
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
};

export { ApiError };
