/**
 * iter 81 (D1 v1): Outline 預覽 modal.
 *
 * 觸發點: JobEditor 標題列「📋 看 outline」按鈕.
 * 內容: 渲染 GET /jobs/{id}/outline 回的 JSON. 結構化顯示:
 *  - deck_title / summary (頂部 banner)
 *  - sections: 每章 collapsed card (title / intent / topics)
 *  - 整份 raw JSON 可展開 (debug 用)
 *
 * v1 唯讀 — 用戶看 LLM 拆解結果, 判斷要不要重 ingest. edit / approve gate
 * 是 D1 v2 工作.
 */
import { useEffect, useState } from 'react';

import { api } from '../api';

interface OutlineSection {
  id?: string;
  title?: string;
  intent?: string;
  topics?: string[];
}

interface OutlineData {
  deck_title?: string;
  summary?: string;
  sections?: OutlineSection[];
}

interface OutlineModalProps {
  jobId: string;
  onClose: () => void;
}

export function OutlineModal({ jobId, onClose }: OutlineModalProps) {
  const [outline, setOutline] = useState<OutlineData | null>(null);
  const [rawJson, setRawJson] = useState<string>('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    api
      .getOutline(jobId)
      .then((data) => {
        setOutline(data as OutlineData);
        setRawJson(JSON.stringify(data, null, 2));
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message || '讀 outline 失敗');
        setLoading(false);
      });
  }, [jobId]);

  return (
    <div
      className="fixed inset-0 z-50 bg-forest-900/60 backdrop-blur-[3px] flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-paper-card w-full max-w-4xl max-h-[90vh] border border-paper-line rounded-sm shadow-lift overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 pt-5 pb-4 border-b border-paper-line flex items-center gap-3">
          <div className="flex-1">
            <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-ink-muted mb-1">
              outline · ai 拆解結果
            </div>
            <h3 className="font-display text-[22px] text-forest-700 leading-tight">
              📋 影片大綱
            </h3>
            <p className="text-[12px] text-ink-muted mt-0.5">
              scriptor 前的章節規劃, 用來判斷要不要重 ingest (調 length_mode / source 等)
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink text-2xl leading-none px-2"
            aria-label="關閉"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto bg-paper-warm">
          {loading ? (
            <div className="text-center py-20 text-ink-muted">載入中…</div>
          ) : error ? (
            <div className="p-6 text-center">
              <div className="text-ink-muted mb-2">⚠ {error}</div>
              <div className="text-[11px] text-ink-faint">
                exam_pdf 不產 outline (直接吐 deck) — 該類型不適用此功能
              </div>
            </div>
          ) : outline ? (
            <div className="p-5 space-y-4">
              {/* Title + summary */}
              <div className="bg-paper-card border border-paper-line rounded-sm p-4">
                <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-muted mb-1">
                  Deck Title
                </div>
                <div className="text-[18px] font-display text-forest-700 mb-3">
                  {outline.deck_title || '(未命名)'}
                </div>
                {outline.summary && (
                  <>
                    <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-muted mb-1">
                      Summary
                    </div>
                    <p className="text-[13px] text-ink leading-relaxed">{outline.summary}</p>
                  </>
                )}
              </div>

              {/* Sections */}
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-muted mb-2">
                  Sections ({outline.sections?.length ?? 0})
                </div>
                <div className="space-y-2">
                  {(outline.sections || []).map((sec, i) => (
                    <div
                      key={sec.id ?? i}
                      className="bg-paper-card border border-paper-line rounded-sm p-3"
                    >
                      <div className="flex items-baseline gap-2 mb-1">
                        <span className="font-mono text-[11px] text-ink-faint">{i + 1}.</span>
                        <span className="font-medium text-[14px] text-forest-700">
                          {sec.title || '(無標題)'}
                        </span>
                        {sec.id && (
                          <span className="font-mono text-[10px] text-ink-faint ml-auto">
                            {sec.id}
                          </span>
                        )}
                      </div>
                      {sec.intent && (
                        <div className="text-[12px] text-ink-muted ml-5 mb-1">{sec.intent}</div>
                      )}
                      {sec.topics && sec.topics.length > 0 && (
                        <div className="flex flex-wrap gap-1 ml-5 mt-2">
                          {sec.topics.map((t, j) => (
                            <span
                              key={j}
                              className="text-[10.5px] px-2 py-0.5 bg-paper-warm border border-paper-edge rounded-sm text-ink"
                            >
                              {t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Raw JSON (debug) */}
              <div>
                <button
                  onClick={() => setShowRaw((v) => !v)}
                  className="text-[11px] text-ink-muted hover:text-ink underline"
                >
                  {showRaw ? '收起' : '展開'} 原始 JSON
                </button>
                {showRaw && (
                  <pre className="mt-2 bg-ink/5 border border-paper-line rounded-sm p-3 text-[11px] font-mono overflow-x-auto whitespace-pre">
                    {rawJson}
                  </pre>
                )}
              </div>
            </div>
          ) : null}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-paper-line bg-paper-card text-[11px] text-ink-muted flex justify-between">
          <span>v1 唯讀 · edit / approve gate 是 D1 v2</span>
          <button onClick={onClose} className="text-ink hover:underline">
            關閉
          </button>
        </div>
      </div>
    </div>
  );
}
