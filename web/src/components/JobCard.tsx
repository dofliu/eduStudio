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
  // PR-3f: 統計 YouTube 上傳進度 — N/M 已上傳 done
  const ytDoneCount = mp4s.filter(
    (a) => job.youtube_uploads?.[a.name]?.state === 'done',
  ).length;
  const ytUploadingCount = mp4s.filter(
    (a) => job.youtube_uploads?.[a.name]?.state === 'uploading',
  ).length;

  const onApprove = async () => {
    const isRetry = job.state === 'failed';
    const msg = isRetry
      ? '重試 render? 用目前 deck.json 跑'
      : 'Approve 後會立刻開始渲染, 確定?';
    if (!confirm(msg)) return;
    try {
      await api.approve(job.id);
      show(isRetry ? '已重新觸發 render...' : '已 Approve, 渲染中...');
      onChanged();
    } catch (e) {
      show(`${isRetry ? '重試' : 'Approve'} 失敗: ${e}`, 'error');
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
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <span className="font-mono text-xs text-ink-muted">{job.id}</span>
          <StatusBadge state={job.state} />
          {stats && <span className="text-sm text-ink-muted">{stats}</span>}
          {job.state === 'done' && mp4s.length > 0 && (
            <span
              className={
                'text-xs px-2 py-0.5 rounded ' +
                (ytDoneCount === mp4s.length
                  ? 'bg-green-100 text-green-800'
                  : ytUploadingCount > 0
                  ? 'bg-blue-100 text-blue-800'
                  : 'bg-stone-100 text-ink-muted')
              }
              title="YouTube 上傳進度"
            >
              📺 {ytDoneCount}/{mp4s.length}
              {ytUploadingCount > 0 && ` (${ytUploadingCount} 上傳中)`}
            </span>
          )}
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
        {/* PR-3j: failed 也提供 retry 入口, 不必砍 job 重跑 ingest */}
        {job.state === 'failed' && (
          <button onClick={onApprove} className="btn btn-primary" title="用目前 deck.json 重新 render">
            🔄 重試
          </button>
        )}
        {/* iter 47: 有 final.mp4 (iter 45 多章合成) 就優先當 preview 入口,
            各章 mp4 在 JobEditor 才看得到 */}
        {job.state === 'done' && mp4s.length > 0 && (() => {
          const finalMp4 = mp4s.find(a => a.name === 'final.mp4');
          const primary = finalMp4 ?? mp4s[0];
          const others = finalMp4 ? mp4s.length : mp4s.length - 1;
          return (
            <>
              <a
                href={api.artifactUrl(job.id, primary.name)}
                className="btn btn-secondary"
                title={finalMp4 ? '完整影片 (含全部章節)' : primary.name}
              >
                {finalMp4 ? '▶ 🎬 完整影片' : `▶ ${primary.name}`}
              </a>
              {others > 0 && (
                <span className="text-sm text-ink-muted">
                  {finalMp4 ? `+${others - 1} 章獨立` : `+${others} more`}
                </span>
              )}
            </>
          );
        })()}
        <button onClick={onDelete} className="btn btn-ghost text-red-700" title="刪除 job">
          ✕
        </button>
      </div>
    </div>
  );
}
