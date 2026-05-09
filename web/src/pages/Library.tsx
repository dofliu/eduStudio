// PR-3m: Library 頁 — 跨 job 平鋪所有 mp4
//
// 對齊 Track A /library 的功能, 但加上 source_type / YouTube 狀態 filter。
// 點影片進去 PublishReview, 點標題進去 JobEditor。
//
// 跟 JobsIndex 的差別:
//   - JobsIndex 是「以 job 為單位」, 一行一個 job (含進行中的)
//   - Library 是「以 mp4 為單位」, 一張一支影片 (只有 done 的 job)

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { useToast } from '../components/Toast';
import type { LibraryItem, SourceType } from '../types';

const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  exam_pdf: '考卷',
  slides_pdf: '簡報',
  repo: 'Repo',
  document: '文件',
  url: '網頁',
};

type YtFilter = 'all' | 'uploaded' | 'pending';
type SrcFilter = 'all' | SourceType;

export default function Library() {
  const { show } = useToast();
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [srcFilter, setSrcFilter] = useState<SrcFilter>('all');
  const [ytFilter, setYtFilter] = useState<YtFilter>('all');

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

  useEffect(() => {
    reload();
  }, [reload]);

  const filtered = useMemo(() => {
    return items.filter((i) => {
      if (srcFilter !== 'all' && i.source_type !== srcFilter) return false;
      if (ytFilter === 'uploaded' && i.youtube?.state !== 'done') return false;
      if (ytFilter === 'pending' && i.youtube?.state === 'done') return false;
      return true;
    });
  }, [items, srcFilter, ytFilter]);

  // 統計
  const ytDone = items.filter((i) => i.youtube?.state === 'done').length;

  if (loading) {
    return <div className="text-center py-10 text-ink-muted">Loading…</div>;
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <h1 className="text-xl font-semibold text-forest">📚 Library</h1>
        <span className="text-sm text-ink-muted">
          {filtered.length} / {items.length} 支 · {ytDone} 已上傳 YouTube
        </span>
        <div className="ml-auto flex items-center gap-2 text-sm">
          <label className="flex items-center gap-1.5">
            <span className="text-ink-muted">類型</span>
            <select
              className="field-input text-xs py-1 px-2"
              value={srcFilter}
              onChange={(e) => setSrcFilter(e.target.value as SrcFilter)}
            >
              <option value="all">全部</option>
              <option value="exam_pdf">考卷</option>
              <option value="slides_pdf">簡報</option>
              <option value="repo">Repo</option>
              <option value="document">文件</option>
              <option value="url">網頁</option>
            </select>
          </label>
          <label className="flex items-center gap-1.5">
            <span className="text-ink-muted">YT</span>
            <select
              className="field-input text-xs py-1 px-2"
              value={ytFilter}
              onChange={(e) => setYtFilter(e.target.value as YtFilter)}
            >
              <option value="all">全部</option>
              <option value="uploaded">已上傳</option>
              <option value="pending">未上傳</option>
            </select>
          </label>
          <button onClick={reload} className="btn btn-ghost text-xs" title="重新整理">
            🔄
          </button>
        </div>
      </div>

      {items.length === 0 && (
        <div className="bg-white border border-border rounded p-6 text-center text-ink-muted">
          目前沒有已渲染的影片。
          <Link to="/" className="text-forest underline ml-2">
            建立 Job →
          </Link>
        </div>
      )}

      {filtered.length === 0 && items.length > 0 && (
        <div className="bg-white border border-border rounded p-4 text-center text-ink-muted">
          目前 filter 沒有符合的影片
        </div>
      )}

      {/* grid 卡片 — 每張 mp4 一張, 縮圖 + meta + 動作 */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {filtered.map((item) => (
          <LibraryCard key={`${item.job_id}-${item.artifact_name}`} item={item} />
        ))}
      </div>
    </div>
  );
}

function LibraryCard({ item }: { item: LibraryItem }) {
  const yt = item.youtube;
  const ytDone = yt?.state === 'done';

  return (
    <div className="bg-white border border-border rounded-md overflow-hidden flex flex-col">
      {/* 影片預覽 */}
      <video
        controls
        src={item.artifact_url}
        className="w-full aspect-video bg-black"
        preload="metadata"
      />
      {/* meta + actions */}
      <div className="p-3 flex flex-col flex-1 gap-1.5">
        <div className="flex items-center gap-1.5 text-xs text-ink-muted flex-wrap">
          <span className="bg-forest/10 px-1.5 py-0.5 rounded">
            {SOURCE_TYPE_LABEL[item.source_type] || item.source_type}
          </span>
          <span className="font-mono">{item.artifact_name}</span>
          <span>· {(item.mp4_size_bytes / 1024 / 1024).toFixed(1)} MB</span>
          {item.srt_exists && (
            <span className="text-forest" title="同名 .srt 存在, 上傳會帶字幕">
              📝 SRT
            </span>
          )}
        </div>
        <Link
          to={`/jobs/${item.job_id}`}
          className="font-semibold text-forest hover:underline text-sm break-all"
          title={`Job ${item.job_id}`}
        >
          {item.deck_title}
        </Link>

        {ytDone && yt?.url && (
          <a
            href={yt.url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-green-700 underline break-all"
          >
            ▶ {yt.url} ({yt.privacy})
          </a>
        )}
        {yt && yt.state === 'uploading' && (
          <div className="text-xs text-blue-700">
            ⏳ 上傳中 {yt.progress_percent}%
          </div>
        )}
        {yt && yt.state === 'failed' && (
          <div className="text-xs text-red-700">⚠ 上次上傳失敗</div>
        )}

        <div className="mt-auto flex gap-1.5 pt-2">
          <Link
            to={`/jobs/${item.job_id}/publish/${encodeURIComponent(item.artifact_name)}`}
            className={
              'btn btn-ghost text-xs flex-1 text-center ' +
              (ytDone ? 'text-green-700' : '')
            }
          >
            📺 {ytDone ? '已上傳 (查看)' : '上傳到 YouTube'}
          </Link>
          <a
            href={item.artifact_url}
            download
            className="btn btn-ghost text-xs"
            title="下載 MP4"
          >
            ⬇
          </a>
        </div>
      </div>
    </div>
  );
}
