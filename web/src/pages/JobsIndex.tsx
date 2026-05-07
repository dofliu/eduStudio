import { useEffect, useState, useCallback, useMemo } from 'react';
import { api } from '../api';
import { JobCard } from '../components/JobCard';
import { CreateJobForm } from '../components/CreateJobForm';
import type { JobRecord, JobState } from '../types';

const POLL_INTERVAL_MS = 5000;
const STATE_FILTERS: (JobState | 'all')[] = [
  'all', 'awaiting_review', 'rendering', 'done', 'failed', 'ingesting', 'pending',
];

export default function JobsIndex() {
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<JobState | 'all'>('all');

  const reload = useCallback(async () => {
    try {
      const r = await api.listJobs();
      setJobs(r.jobs);
    } catch {
      // 連線錯誤不彈 toast 免得 polling 一直叫, 留空就好
    } finally {
      setLoading(false);
    }
  }, []);

  // 啟動載一次, 之後 5 秒輪詢一次
  // 為什麼用輪詢: server 沒做 SSE / WebSocket, 而 mock pipeline 與 render 完成的瞬間
  // 通常 5 秒內看得到, polling 簡單可靠
  useEffect(() => {
    reload();
    const t = setInterval(reload, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [reload]);

  const filtered = useMemo(
    () => (filter === 'all' ? jobs : jobs.filter((j) => j.state === filter)),
    [jobs, filter],
  );

  return (
    <div>
      <CreateJobForm onCreated={reload} />

      <div className="flex items-center gap-2 mb-3">
        <h2 className="text-lg font-semibold text-forest mr-auto">
          Jobs <span className="text-sm font-normal text-ink-muted">({jobs.length})</span>
        </h2>
        <select
          className="field-input w-auto"
          value={filter}
          onChange={(e) => setFilter(e.target.value as JobState | 'all')}
        >
          {STATE_FILTERS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <button onClick={reload} className="btn btn-ghost" title="立即重新整理">
          ↻
        </button>
      </div>

      {loading && jobs.length === 0 ? (
        <div className="text-center py-10 text-ink-muted">Loading…</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-10 text-ink-muted">
          {jobs.length === 0
            ? '尚無 job。用上方表單或 scripts/submit_job.py 建立。'
            : `沒有 state=${filter} 的 job`}
        </div>
      ) : (
        filtered.map((j) => <JobCard key={j.id} job={j} onChanged={reload} />)
      )}
    </div>
  );
}
