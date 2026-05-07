import { Link } from 'react-router-dom';
import { api } from '../api';
import { StatusBadge } from './StatusBadge';
import type { JobRecord } from '../types';
import { useToast } from './Toast';

interface Props {
  job: JobRecord;
  onChanged: () => void;
}

export function JobCard({ job, onChanged }: Props) {
  const { show } = useToast();

  const sourceLabel =
    job.source_type === 'url'
      ? `url: ${job.source.url || '?'}`
      : `${job.source_type}: ${job.source.path || '?'}`;

  const stats = (() => {
    // 從 stages 找 ingest 完成的章節數 — 沒拿到就 fallback
    if (job.state === 'pending' || job.state === 'ingesting') return '(processing…)';
    return null;
  })();

  const mp4s = job.artifacts.filter((a) => a.kind === 'mp4');

  const onApprove = async () => {
    if (!confirm('Approve 後會立刻開始渲染, 確定?')) return;
    try {
      await api.approve(job.id);
      show('已 Approve, 渲染中...');
      onChanged();
    } catch (e) {
      show(`Approve 失敗: ${e}`, 'error');
    }
  };

  const onDelete = async () => {
    if (!confirm(`刪除 job ${job.id} 與其所有 artifacts?`)) return;
    try {
      await api.deleteJob(job.id);
      show('已刪除');
      onChanged();
    } catch (e) {
      show(`刪除失敗: ${e}`, 'error');
    }
  };

  return (
    <div className="bg-white border border-border rounded-md p-4 mb-3 flex gap-4 items-start">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-mono text-xs text-ink-muted">{job.id}</span>
          <StatusBadge state={job.state} />
          {stats && <span className="text-sm text-ink-muted">{stats}</span>}
        </div>
        <div className="text-forest font-semibold break-all">{sourceLabel}</div>
        {job.error && (
          <div className="text-red-700 text-sm mt-1">⚠ {job.error}</div>
        )}
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        {(job.state === 'awaiting_review' || job.state === 'done' || job.state === 'failed') && (
          <Link to={`/jobs/${job.id}`} className="btn btn-ghost">
            ✏ Edit
          </Link>
        )}
        {job.state === 'awaiting_review' && (
          <button onClick={onApprove} className="btn btn-primary">
            ✓ Approve
          </button>
        )}
        {job.state === 'done' && mp4s.length > 0 && (
          <a
            href={api.artifactUrl(job.id, mp4s[0].name)}
            className="btn btn-secondary"
          >
            ▶ {mp4s[0].name}
          </a>
        )}
        {job.state === 'done' && mp4s.length > 1 && (
          <span className="text-sm text-ink-muted">+{mp4s.length - 1} more</span>
        )}
        <button onClick={onDelete} className="btn btn-ghost text-red-700" title="刪除 job">
          ✕
        </button>
      </div>
    </div>
  );
}
