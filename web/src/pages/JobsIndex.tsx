// JobsIndex — UI redesign 套用後的版本
// 邏輯完全保留: api.listJobs polling / filter / CreateJobForm 觸發 reload
// 視覺改為兩欄: 左 list, 右 detail (純 UI 狀態, 不額外打 API)

import { useEffect, useState, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { CreateJobForm } from '../components/CreateJobForm';
import { useToast } from '../components/Toast';
import { Btn, Topbar, SourceBadge, StatusPill, Meter } from '../components/ui';
import type { JobRecord, JobState } from '../types';

const POLL_INTERVAL_MS = 5000;

type FilterKey = 'all' | 'active' | JobState;
const FILTER_TABS: { key: FilterKey; label: string }[] = [
  { key: 'all',             label: '全部' },
  { key: 'active',          label: '進行中' },
  { key: 'awaiting_review', label: '待 Review' },
  { key: 'rendering',       label: '渲染中' },
  { key: 'done',            label: '完成' },
  { key: 'failed',          label: '失敗' },
];
const ACTIVE_STATES: JobState[] = ['ingesting', 'rendering', 'awaiting_review', 'pending'];

export default function JobsIndex() {
  const { show } = useToast();
  const [jobs, setJobs] = useState<JobRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const reload = useCallback(async () => {
    try {
      const r = await api.listJobs();
      setJobs(r.jobs);
    } catch {
      // 連線錯誤不彈 toast 免得 polling 一直叫
    } finally {
      setLoading(false);
    }
  }, []);

  // 5 秒輪詢
  useEffect(() => {
    reload();
    const t = setInterval(reload, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [reload]);

  const filtered = useMemo(() => {
    if (filter === 'all') return jobs;
    if (filter === 'active') return jobs.filter((j) => ACTIVE_STATES.includes(j.state));
    return jobs.filter((j) => j.state === filter);
  }, [filter, jobs]);

  // 預設選第一個 job (如果還沒選 / 選的 id 不在 filtered 裡)
  const selected = jobs.find((j) => j.id === selectedId) || filtered[0] || null;

  const counts: Record<FilterKey, number> = useMemo(() => ({
    all:             jobs.length,
    active:          jobs.filter((j) => ACTIVE_STATES.includes(j.state)).length,
    awaiting_review: jobs.filter((j) => j.state === 'awaiting_review').length,
    rendering:       jobs.filter((j) => j.state === 'rendering').length,
    done:            jobs.filter((j) => j.state === 'done').length,
    failed:          jobs.filter((j) => j.state === 'failed').length,
    pending:         jobs.filter((j) => j.state === 'pending').length,
    ingesting:       jobs.filter((j) => j.state === 'ingesting').length,
  }), [jobs]);

  const onApprove = async (job: JobRecord) => {
    const isRetry = job.state === 'failed';
    const msg = isRetry
      ? '重試 render? 用目前 deck.json 跑'
      : 'Approve 後會立刻開始渲染, 確定?';
    if (!confirm(msg)) return;
    try {
      await api.approve(job.id);
      show(isRetry ? '已重新觸發 render...' : '已 Approve, 渲染中...');
      reload();
    } catch (e) {
      show(`${isRetry ? '重試' : 'Approve'} 失敗: ${e}`, 'error');
    }
  };

  const onDelete = async (job: JobRecord) => {
    if (!confirm(`刪除 job ${job.id} 與其所有 artifacts?`)) return;
    try {
      await api.deleteJob(job.id);
      show('已刪除');
      reload();
    } catch (e) {
      show(`刪除失敗: ${e}`, 'error');
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <Topbar
        eyebrow="01 · Jobs"
        title="作業中心"
        subtitle="從上傳到輸出的單一視角。每一個 job 都會經過 ingest → review → render 三個關卡,在這裡推進。"
        right={
          <>
            <Btn kind="ghost" size="md" onClick={reload}>↻ 重新整理</Btn>
            <Btn kind="secondary" size="md" onClick={() => setShowCreate(true)}>＋ 建立 Job</Btn>
          </>
        }
      />

      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* LEFT — list */}
        <div className="w-[340px] shrink-0 border-r border-paper-line flex flex-col">
          <div className="px-4 pt-3 pb-2 border-b border-paper-line">
            <div className="flex items-center gap-0.5 flex-wrap text-[11.5px]">
              {FILTER_TABS.map(({ key, label }) => {
                const active = filter === key;
                return (
                  <button
                    key={key}
                    onClick={() => setFilter(key)}
                    className={
                      'px-2 py-0.5 rounded-sm font-medium transition-colors whitespace-nowrap ' +
                      (active
                        ? 'bg-forest-600 text-chalk-yellow'
                        : 'text-ink-muted hover:bg-paper-warm')
                    }
                  >
                    {label}{' '}
                    <span className="num font-mono text-[10px] opacity-70 ml-0.5">
                      {counts[key] || 0}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto scrollbar-thin">
            {loading && jobs.length === 0 ? (
              <div className="text-center py-10 text-ink-muted">Loading…</div>
            ) : filtered.length === 0 ? (
              <div className="text-center py-10 text-ink-muted text-[13px]">
                {jobs.length === 0
                  ? '尚無 job。用上方「＋ 建立 Job」開始。'
                  : `沒有 ${filter} 狀態的 job`}
              </div>
            ) : (
              filtered.map((j) => {
                const sel = j.id === selected?.id;
                const mp4s = j.artifacts.filter((a) => a.kind === 'mp4');
                const ytDone = mp4s.filter(
                  (a) => j.youtube_uploads?.[a.name]?.state === 'done',
                ).length;
                const sourceLabel =
                  j.source_type === 'url'
                    ? j.source.url || '?'
                    : j.source.path || '?';
                return (
                  <button
                    key={j.id}
                    onClick={() => setSelectedId(j.id)}
                    className={
                      'w-full text-left px-4 py-2.5 border-b border-paper-line transition-colors block ' +
                      (sel ? 'bg-chalk-yellow/30' : 'hover:bg-paper-warm')
                    }
                  >
                    <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                      <SourceBadge type={j.source_type} size="sm" />
                      <StatusPill state={j.state} size="sm" />
                      <span className="ml-auto font-mono text-[10px] text-ink-faint">
                        {j.id.slice(0, 8)}
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-ink-subtle truncate">
                      {sourceLabel}
                    </div>
                    {j.error && (
                      <div className="text-accent-coral text-[11px] mt-1 truncate">
                        ⚠ {j.error}
                      </div>
                    )}
                    {(j.state === 'rendering' || j.state === 'ingesting') && (
                      <div className="mt-2">
                        <Meter value={0.5} />
                      </div>
                    )}
                    <div className="mt-1.5 flex items-center gap-2.5 text-[10.5px] text-ink-muted">
                      <span className="font-mono">{j.updated_at.slice(0, 16).replace('T', ' ')}</span>
                      {mp4s.length > 0 && (
                        <span className="font-mono">▶ {mp4s.length}</span>
                      )}
                      {mp4s.length > 0 && (
                        <span className="font-mono">📺 {ytDone}/{mp4s.length}</span>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* RIGHT — detail */}
        <div className="flex-1 overflow-y-auto scrollbar-thin min-w-0">
          {selected ? (
            <JobDetailPane job={selected} onApprove={() => onApprove(selected)} onDelete={() => onDelete(selected)} />
          ) : (
            <div className="text-center py-20 text-ink-muted">
              {loading ? 'Loading…' : '選擇左側 job 看詳情'}
            </div>
          )}
        </div>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-40 bg-forest-900/40 backdrop-blur-[2px] flex items-start justify-center p-6 overflow-y-auto" onClick={() => setShowCreate(false)}>
          <div className="bg-paper-card w-full max-w-2xl border border-paper-line rounded-sm shadow-lift mt-12" onClick={(e) => e.stopPropagation()}>
            <div className="px-6 pt-5 pb-2 border-b border-paper-line flex items-center">
              <div>
                <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-ink-muted">new job</div>
                <div className="font-display text-[24px] text-forest-700 leading-tight mt-0.5">建立新作業</div>
              </div>
              <button onClick={() => setShowCreate(false)} className="ml-auto btn btn-ghost">✕</button>
            </div>
            <div className="p-2">
              {/* 沿用原 CreateJobForm — 邏輯完全沒動, 樣式吃新的 .btn / .field-input */}
              <CreateJobForm onCreated={() => { setShowCreate(false); reload(); }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Detail pane (純 presentational, 不額外打 API) ─────────────────────────

interface DetailProps {
  job: JobRecord;
  onApprove: () => void;
  onDelete: () => void;
}

function JobDetailPane({ job, onApprove, onDelete }: DetailProps) {
  const stages = [
    { key: 'ingest', label: 'Ingest',         desc: '抽取結構' },
    { key: 'review', label: 'Awaiting Review', desc: '人工核稿' },
    { key: 'render', label: 'Render',          desc: 'TTS · video' },
    { key: 'done',   label: 'Done',            desc: 'final.mp4' },
  ];
  const stageIdx = (() => {
    if (job.state === 'pending' || job.state === 'ingesting') return 0;
    if (job.state === 'awaiting_review') return 1;
    if (job.state === 'rendering') return 2;
    if (job.state === 'done') return 3;
    if (job.state === 'failed') return 2;
    return 0;
  })();

  const sourceLabel =
    job.source_type === 'url'
      ? `url: ${job.source.url || '?'}`
      : `${job.source_type}: ${job.source.path || '?'}`;

  const mp4s = job.artifacts.filter((a) => a.kind === 'mp4');
  const finalMp4 = mp4s.find((a) => a.name === 'final.mp4');
  const sectionMp4s = mp4s.filter((a) => a.name !== 'final.mp4');
  const ytDone = mp4s.filter((a) => job.youtube_uploads?.[a.name]?.state === 'done').length;

  return (
    <div className="px-7 py-5 space-y-5 max-w-5xl">
      {/* Title block — compact */}
      <div>
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <SourceBadge type={job.source_type} size="sm" />
          <StatusPill state={job.state} size="sm" />
          <span className="font-mono text-[10.5px] text-ink-faint ml-auto">id · {job.id}</span>
        </div>
        <h2 className="font-display text-[22px] leading-[1.15] text-forest-700 break-all">{sourceLabel}</h2>
        <div className="text-[11px] text-ink-muted mt-1">
          建立 <span className="font-mono">{job.created_at.slice(0, 16).replace('T', ' ')}</span>
          {' · '}最後更新 <span className="font-mono">{job.updated_at.slice(0, 16).replace('T', ' ')}</span>
        </div>
      </div>

      {job.state === 'failed' && job.error && (
        <div className="border-l-2 border-accent-coral pl-3 py-1.5 bg-paper-warm">
          <div className="text-[10.5px] font-mono uppercase tracking-[0.18em] text-accent-coral mb-0.5">render error</div>
          <div className="text-[12.5px] text-ink font-mono break-all">{job.error}</div>
          <div className="text-[11px] text-ink-muted mt-1">deck.json 還在,可以直接重試 render,不必重新 ingest。</div>
        </div>
      )}

      {/* Pipeline — compact */}
      <section>
        <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-muted mb-2">pipeline</div>
        <div className="grid grid-cols-4 gap-2">
          {stages.map((s, i) => {
            const past = i < stageIdx;
            const cur = i === stageIdx;
            const failed = job.state === 'failed' && i === stageIdx;
            return (
              <div
                key={s.key}
                className={
                  'border rounded-sm px-2.5 py-2 ' +
                  (failed
                    ? 'border-accent-coral bg-paper-warm'
                    : cur
                    ? 'border-forest-500 bg-forest-100'
                    : past
                    ? 'border-paper-line bg-paper-card'
                    : 'border-paper-line bg-paper-card opacity-50')
                }
              >
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span className={'font-mono text-[10px] ' + (cur || past || failed ? 'text-forest-600' : 'text-ink-faint')}>0{i + 1}</span>
                  <span className={'text-[11.5px] font-medium leading-tight ' + (failed ? 'text-accent-coral' : 'text-ink')}>{s.label}</span>
                </div>
                <div className="text-[10.5px] text-ink-muted leading-tight">{s.desc}</div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Actions */}
      <section>
        <div className="flex items-center gap-2 flex-wrap">
          {job.state === 'awaiting_review' && (
            <>
              <Link to={`/jobs/${job.id}`} className="btn btn-primary">✏ 進入 Edit · 核稿</Link>
              <Btn kind="secondary" size="md" onClick={onApprove}>✓ 直接 Approve & Render</Btn>
            </>
          )}
          {job.state === 'failed' && (
            <>
              <Btn kind="primary" size="md" onClick={onApprove}>🔄 重試 render</Btn>
              <Link to={`/jobs/${job.id}`} className="btn btn-ghost">✏ 開 Edit 修 deck</Link>
            </>
          )}
          {job.state === 'done' && finalMp4 && (
            <>
              <a href={api.artifactUrl(job.id, finalMp4.name)} className="btn btn-primary">▶ 預覽完整影片</a>
              <Link to={`/jobs/${job.id}/publish/${encodeURIComponent(finalMp4.name)}`} className="btn btn-secondary">📺 上傳到 YouTube</Link>
              <Link to={`/jobs/${job.id}`} className="btn btn-ghost">✏ 編輯 / 重 render 單章</Link>
            </>
          )}
          {(job.state === 'ingesting' || job.state === 'rendering' || job.state === 'pending') && (
            <Link to={`/jobs/${job.id}`} className="btn btn-ghost">⏱ 等待中 · 看 log</Link>
          )}
          <span className="flex-1" />
          <Btn kind="danger" size="sm" onClick={onDelete}>✕ 刪除 job</Btn>
        </div>
      </section>

      {/* Stats — compact 4-col, smaller */}
      <section className="grid grid-cols-4 gap-2">
        {job.options.theme && <Stat label="主題" value={job.options.theme} />}
        {mp4s.length > 0 && <Stat label="MP4 個數" value={String(mp4s.length)} mono />}
        {mp4s.length > 0 && <Stat label="YouTube" value={`${ytDone}/${mp4s.length}`} mono />}
        <Stat label="stages" value={String(job.stages.length)} mono />
      </section>

      {/* Artifacts */}
      {job.state === 'done' && mp4s.length > 0 && (
        <section>
          <div className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-muted mb-2">artifacts</div>
          <div className="space-y-1.5">
            {finalMp4 && <ArtifactRow job={job} a={finalMp4} primary />}
            {sectionMp4s.map((a) => (
              <ArtifactRow key={a.name} job={job} a={a} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Stat({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="border border-paper-line bg-paper-card rounded-sm px-3 py-1.5">
      <div className="text-[9.5px] font-mono uppercase tracking-[0.16em] text-ink-muted">{label}</div>
      <div className={'text-[13.5px] text-forest-700 mt-0.5 ' + (mono ? 'font-mono num' : 'font-medium')}>{value}</div>
    </div>
  );
}

function ArtifactRow({ job, a, primary }: { job: JobRecord; a: JobRecord['artifacts'][number]; primary?: boolean }) {
  const yt = job.youtube_uploads?.[a.name];
  return (
    <div className={'border rounded-sm px-3 py-2 flex items-center gap-2.5 flex-wrap text-[12px] ' + (primary ? 'border-forest-500 bg-forest-100' : 'border-paper-line bg-paper-card')}>
      <span className="font-mono">{primary ? '🎬 ' : ''}{a.name}</span>
      <span className="text-[10.5px] text-ink-muted font-mono">{(a.size_bytes / 1024 / 1024).toFixed(1)} MB</span>
      <a href={api.artifactUrl(job.id, a.name)} className="text-forest-600 hover:text-forest-700 underline decoration-dotted">▶ 預覽</a>
      <Link
        to={`/jobs/${job.id}/publish/${encodeURIComponent(a.name)}`}
        className="text-forest-600 hover:text-forest-700 underline decoration-dotted"
      >
        📺 {yt?.state === 'done' ? '已上傳'
          : yt?.state === 'uploading' ? `上傳中 ${yt.progress_percent}%`
          : yt?.state === 'failed' ? '上傳失敗 (重試)'
          : '上傳到 YouTube'}
      </Link>
      {yt?.url && (
        <a href={yt.url} target="_blank" rel="noreferrer" className="text-[10.5px] text-ink-muted underline break-all">{yt.url}</a>
      )}
    </div>
  );
}
