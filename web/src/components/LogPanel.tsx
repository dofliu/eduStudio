// PR-4c: per-job log tail panel
//
// 給 JobEditor 用. RENDERING / INGESTING 時 auto-poll 3 秒, 其他狀態 reload 一次。
// 預設摺起來 (內容多, 不影響上方編輯), 展開時固定高度 + 自動滾到最新。

import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { JobState, LogEntry } from '../types';

interface Props {
  jobId: string;
  jobState: JobState;
}

const LIVE_STATES: JobState[] = ['ingesting', 'rendering'];
const POLL_MS = 3000;

const LEVEL_COLOR: Record<string, string> = {
  ERROR: 'text-red-700',
  WARNING: 'text-orange-600',
  INFO: 'text-ink',
  DEBUG: 'text-ink-muted',
  RAW: 'text-ink-muted',
};

export function LogPanel({ jobId, jobState }: Props) {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.getJobLog(jobId, 200);
      setEntries(r.entries);
    } catch {
      // log 不存在不算錯 (job 還沒跑出 log)
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    if (!open) return;
    load();
    if (LIVE_STATES.includes(jobState)) {
      const t = setInterval(load, POLL_MS);
      return () => clearInterval(t);
    }
    return undefined;
  }, [open, jobState, load]);

  // 新 log 進來時自動滾到底
  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [entries, open]);

  const isLive = LIVE_STATES.includes(jobState);

  return (
    <div className="bg-white border border-border rounded-md mb-4">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-2 text-sm hover:bg-stone-50 text-left"
      >
        <span>{open ? '▼' : '▶'}</span>
        <span className="font-semibold text-forest">📋 Job Log</span>
        {entries.length > 0 && (
          <span className="text-ink-muted text-xs">({entries.length} 筆)</span>
        )}
        {isLive && open && (
          <span className="text-xs text-blue-700 ml-auto animate-pulse">
            ⏳ live polling 每 3 秒
          </span>
        )}
        {!open && isLive && (
          <span className="text-xs text-blue-700 ml-auto">⏳ live</span>
        )}
      </button>

      {open && (
        <div
          ref={scrollRef}
          className="border-t border-border bg-stone-50 max-h-96 overflow-y-auto p-2 font-mono text-xs"
        >
          {loading && entries.length === 0 && (
            <div className="text-ink-muted text-center py-4">Loading…</div>
          )}
          {!loading && entries.length === 0 && (
            <div className="text-ink-muted text-center py-4">
              還沒有 log (job 可能還沒進 ingesting/rendering)
            </div>
          )}
          {entries.map((e, i) => {
            const level = (e.level || 'INFO').toUpperCase();
            const color = LEVEL_COLOR[level] || 'text-ink';
            const timeOnly = (e.ts || '').slice(11, 23); // "HH:MM:SS.sss"
            return (
              <div key={i} className="py-0.5 border-b border-stone-200 last:border-b-0">
                <span className="text-ink-muted">{timeOnly}</span>{' '}
                <span className={color + ' font-semibold'}>{level}</span>{' '}
                {e.stage && (
                  <span className="text-purple-700">[{e.stage}]</span>
                )}{' '}
                <span className="text-ink-muted">{e.logger}</span>:{' '}
                <span className={color}>{e.msg}</span>
                {e.exc && (
                  <pre className="text-red-700 whitespace-pre-wrap mt-1 ml-4">
                    {e.exc}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
