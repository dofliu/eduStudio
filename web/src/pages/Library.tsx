// Library — UI redesign 套用後的版本
// 邏輯完全保留: items / loading / srcFilter / ytFilter / reload / useMemo
// 新增的 view (grid|list) 是純 UI 切換, 不影響任何 API 行為

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useToast } from '../components/Toast';
import { Btn, Topbar, SourceBadge, Meter } from '../components/ui';
import type { LibraryItem, SourceType } from '../types';

type YtFilter = 'all' | 'uploaded' | 'pending';
type SrcFilter = 'all' | SourceType;
type ViewMode = 'grid' | 'list';

export default function Library() {
  const { show } = useToast();
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [srcFilter, setSrcFilter] = useState<SrcFilter>('all');
  const [ytFilter, setYtFilter] = useState<YtFilter>('all');
  const [view, setView] = useState<ViewMode>('grid');

  const reload = useCallback(async () => {
    try {
      const r = await api.getLibrary();
      setItems(r.items);
    } catch (e) {
      show(`載入 Library 失敗: ${e}`, 'error');
    } finally {
      setLoading(false);
    }
  }, [show]);

  useEffect(() => { reload(); }, [reload]);

  const filtered = useMemo(() => {
    return items.filter((i) => {
      if (srcFilter !== 'all' && i.source_type !== srcFilter) return false;
      if (ytFilter === 'uploaded' && i.youtube?.state !== 'done') return false;
      if (ytFilter === 'pending' && i.youtube?.state === 'done') return false;
      return true;
    });
  }, [items, srcFilter, ytFilter]);

  const ytDone = items.filter((i) => i.youtube?.state === 'done').length;
  const totalGB = (items.reduce((s, i) => s + i.mp4_size_bytes, 0) / 1024 / 1024 / 1024).toFixed(1);

  return (
    <div className="flex flex-col h-screen">
      <Topbar
        eyebrow="03 · Library"
        title="影片庫"
        subtitle="所有跑完 render 的 mp4。可以直接預覽、下載、或一鍵上傳 YouTube。"
        right={
          <>
            <div className="flex items-center rounded-sm border border-paper-edge bg-paper-card overflow-hidden">
              <button onClick={() => setView('grid')} className={'px-3 h-9 text-[12px] whitespace-nowrap ' + (view === 'grid' ? 'bg-forest-600 text-chalk-yellow' : 'text-ink-muted hover:bg-paper-warm')}>⊞ 卡片</button>
              <button onClick={() => setView('list')} className={'px-3 h-9 text-[12px] whitespace-nowrap ' + (view === 'list' ? 'bg-forest-600 text-chalk-yellow' : 'text-ink-muted hover:bg-paper-warm')}>≡ 清單</button>
            </div>
            <Btn kind="ghost" size="md" onClick={reload}>↻</Btn>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="px-10 py-7">
          <div className="grid grid-cols-4 gap-3 mb-7">
            <LibStat n={items.length} l="總影片數" />
            <LibStat n={ytDone} l="已上傳 YT" />
            <LibStat n={`${totalGB}G`} l="總體積" mono />
            <LibStat n={items.filter(i => i.srt_exists).length} l="含字幕" mono />
          </div>

          <div className="flex items-center gap-3 mb-5 flex-wrap pb-4 border-b border-paper-line">
            <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-muted">filter</span>
            <ChipGroup
              value={srcFilter} onChange={setSrcFilter}
              options={[
                ['all', '全部'],
                ['exam_pdf', '考卷'],
                ['slides_pdf', '簡報'],
                ['repo', 'Repo'],
                ['document', '文件'],
                ['url', '網頁'],
              ]}
            />
            <span className="w-px h-5 bg-paper-line"></span>
            <ChipGroup
              value={ytFilter} onChange={setYtFilter}
              options={[
                ['all', '所有 YT 狀態'],
                ['uploaded', '📺 已上傳'],
                ['pending', '🕒 未上傳'],
              ]}
            />
            <span className="ml-auto text-[11px] text-ink-muted font-mono">{filtered.length} / {items.length}</span>
          </div>

          {loading ? (
            <div className="text-center py-10 text-ink-muted">Loading…</div>
          ) : items.length === 0 ? (
            <div className="border border-dashed border-paper-edge rounded-sm p-10 text-center">
              <div className="text-ink-muted mb-3">目前沒有已渲染的影片。</div>
              <Link to="/" className="text-forest-600 underline">建立 Job →</Link>
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-10 text-ink-muted">目前 filter 沒有符合的影片</div>
          ) : view === 'grid' ? (
            <div className="grid grid-cols-3 gap-5">
              {filtered.map((it) => <LibCard key={it.job_id + it.artifact_name} it={it} />)}
            </div>
          ) : (
            <LibTable items={filtered} />
          )}
        </div>
      </div>
    </div>
  );
}

function LibStat({ n, l, mono }: { n: number | string; l: string; mono?: boolean }) {
  return (
    <div className="border border-paper-line bg-paper-card rounded-sm px-4 py-3">
      <div className={'font-display text-[34px] leading-none text-forest-700 ' + (mono ? 'font-mono num' : '')}>{n}</div>
      <div className="mt-1 text-[11px] font-mono uppercase tracking-[0.16em] text-ink-muted">{l}</div>
    </div>
  );
}

interface ChipGroupProps<T extends string> {
  value: T;
  onChange: (v: T) => void;
  options: Array<[T, string]>;
}
function ChipGroup<T extends string>({ value, onChange, options }: ChipGroupProps<T>) {
  return (
    <div className="flex items-center gap-1 flex-wrap text-[12px]">
      {options.map(([k, l]) => {
        const sel = value === k;
        return (
          <button
            key={k}
            onClick={() => onChange(k)}
            className={
              'px-2.5 py-1 rounded-sm font-medium transition-colors whitespace-nowrap ' +
              (sel ? 'bg-forest-600 text-chalk-yellow' : 'text-ink-muted hover:bg-paper-warm border border-transparent')
            }
          >
            {l}
          </button>
        );
      })}
    </div>
  );
}

function LibCard({ it }: { it: LibraryItem }) {
  const yt = it.youtube;
  return (
    <div className="bg-paper-card border border-paper-line rounded-sm overflow-hidden hover:shadow-lift hover:border-forest-300 transition-all group">
      <div className="relative">
        <video
          src={it.artifact_url}
          controls
          className="w-full aspect-video bg-black"
          preload="metadata"
        />
        {yt?.state === 'done' && (
          <div className="absolute top-2 left-2 px-1.5 py-0.5 rounded-sm bg-paper text-forest-700 text-[10px] font-mono uppercase tracking-[0.14em] border border-paper-edge pointer-events-none">📺 {yt.privacy}</div>
        )}
        {yt?.state === 'uploading' && (
          <div className="absolute top-2 left-2 px-1.5 py-0.5 rounded-sm bg-chalk-yellow text-forest-700 text-[10px] font-mono uppercase tracking-[0.14em] pointer-events-none">⏱ 上傳 {yt.progress_percent}%</div>
        )}
        {yt?.state === 'failed' && (
          <div className="absolute top-2 left-2 px-1.5 py-0.5 rounded-sm bg-accent-coral text-paper text-[10px] font-mono uppercase tracking-[0.14em] pointer-events-none">⚠ 上傳失敗</div>
        )}
      </div>

      <div className="p-3.5">
        <div className="flex items-center gap-2 mb-1.5 flex-wrap">
          <SourceBadge type={it.source_type} size="sm" />
          {it.srt_exists && <span className="text-[10px] font-mono text-ink-muted">SRT</span>}
          <span className="ml-auto text-[10px] font-mono text-ink-faint">{(it.mp4_size_bytes / 1024 / 1024).toFixed(0)} MB</span>
        </div>
        <Link
          to={`/jobs/${it.job_id}`}
          className="font-display text-[17px] text-forest-700 leading-[1.15] line-clamp-2 min-h-[40px] hover:underline block"
          title={`Job ${it.job_id}`}
        >
          {it.deck_title}
        </Link>
        <div className="font-mono text-[10px] text-ink-faint mt-1.5 truncate">{it.job_id} · {it.artifact_name}</div>

        {yt?.state === 'done' && yt.url ? (
          <a href={yt.url} target="_blank" rel="noreferrer" className="block mt-2.5 text-[12px] text-forest-600 hover:text-forest-700 underline decoration-dotted truncate">▶ {yt.url}</a>
        ) : yt?.state === 'uploading' ? (
          <div className="mt-2.5"><Meter value={yt.progress_percent / 100} tone="yellow" /></div>
        ) : (
          <div className="mt-2.5 text-[12px] text-ink-muted">{yt?.state === 'failed' ? '上次上傳失敗,可重試' : '尚未上傳 YouTube'}</div>
        )}

        <div className="mt-3 flex gap-1.5 pt-3 border-t border-paper-line">
          <Link
            to={`/jobs/${it.job_id}/publish/${encodeURIComponent(it.artifact_name)}`}
            className={'btn btn-ghost btn-sm flex-1 justify-center !text-[12px] !h-7 ' + (yt?.state === 'done' ? '!text-forest-700' : '')}
          >
            📺 {yt?.state === 'done' ? '已上傳' : '上傳 YT'}
          </Link>
          <a href={it.artifact_url} download className="btn btn-quiet !text-[12px] !h-7" title="下載 MP4">⬇</a>
        </div>
      </div>
    </div>
  );
}

function LibTable({ items }: { items: LibraryItem[] }) {
  return (
    <div className="border border-paper-line rounded-sm overflow-hidden bg-paper-card">
      <div className="grid grid-cols-[120px_1fr_120px_140px_120px] gap-3 px-4 py-2.5 border-b border-paper-line bg-paper text-[10px] font-mono uppercase tracking-[0.14em] text-ink-muted">
        <div>類型</div>
        <div>標題</div>
        <div>大小</div>
        <div>YouTube</div>
        <div className="text-right">動作</div>
      </div>
      {items.map((it) => {
        const yt = it.youtube;
        return (
          <div
            key={it.job_id + it.artifact_name}
            className="grid grid-cols-[120px_1fr_120px_140px_120px] gap-3 px-4 py-3 border-b border-paper-line last:border-b-0 hover:bg-paper items-center"
          >
            <div><SourceBadge type={it.source_type} size="sm" /></div>
            <div className="min-w-0">
              <Link to={`/jobs/${it.job_id}`} className="font-medium text-[13.5px] text-forest-700 truncate hover:underline block">{it.deck_title}</Link>
              <div className="font-mono text-[10.5px] text-ink-faint">{it.job_id} · {it.artifact_name}</div>
            </div>
            <div className="font-mono num text-[13px] text-ink-muted">{(it.mp4_size_bytes / 1024 / 1024).toFixed(0)} MB</div>
            <div>
              {yt?.state === 'done' && <span className="text-[12px] text-forest-700">📺 {yt.privacy}</span>}
              {yt?.state === 'uploading' && <span className="text-[12px] text-chalk-yellowDark">⏱ {yt.progress_percent}%</span>}
              {(!yt || yt.state === 'pending') && <span className="text-[12px] text-ink-muted">—</span>}
              {yt?.state === 'failed' && <span className="text-[12px] text-accent-coral">⚠ 失敗</span>}
            </div>
            <div className="flex gap-1 justify-end">
              <a href={it.artifact_url} target="_blank" rel="noreferrer" className="btn btn-ghost !text-[12px] !h-7" title="開新分頁播放">▶</a>
              <Link to={`/jobs/${it.job_id}/publish/${encodeURIComponent(it.artifact_name)}`} className="btn btn-ghost !text-[12px] !h-7">📺</Link>
              <a href={it.artifact_url} download className="btn btn-quiet !text-[12px] !h-7">⬇</a>
            </div>
          </div>
        );
      })}
    </div>
  );
}
