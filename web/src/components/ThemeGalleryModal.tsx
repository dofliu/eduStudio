/**
 * iter 72: 主題預覽長廊 modal.
 *
 * 觸發於 CreateJobForm / ProposalsList 的「🎨 預覽主題」按鈕. Modal 內列
 * 15 個主題 thumbnail (main slide + cover 兩張), 用戶點 thumbnail 就選定
 * 該主題並關 modal.
 *
 * Thumbnail PNG 由 backend 端 (/themes/preview/{theme}[/cover]) 渲染 + 緩存.
 */
import { useEffect, useState } from 'react';

interface ThemeInfo {
  id: string;
  label: string;
}

interface ThemeGalleryModalProps {
  currentTheme: string;
  onSelect: (theme: string) => void;
  onClose: () => void;
}

export function ThemeGalleryModal({ currentTheme, onSelect, onClose }: ThemeGalleryModalProps) {
  const [themes, setThemes] = useState<ThemeInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'slide' | 'cover'>('slide');

  useEffect(() => {
    fetch('/themes')
      .then((r) => r.json())
      .then((data) => {
        setThemes(data.themes || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 bg-forest-900/60 backdrop-blur-[3px] flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-paper-card w-full max-w-6xl max-h-[90vh] border border-paper-line rounded-sm shadow-lift overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-6 pt-5 pb-4 border-b border-paper-line flex items-center gap-4">
          <div className="flex-1">
            <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-ink-muted mb-1">
              theme · gallery
            </div>
            <h3 className="font-display text-[22px] text-forest-700 leading-tight">
              15 主題預覽
            </h3>
            <p className="text-[12px] text-ink-muted mt-0.5">
              點選 thumbnail 套用 — banner / 字型 / 簽名裝飾 / bullets layout 都依主題切換
            </p>
          </div>
          <div className="flex gap-1 text-xs">
            <button
              onClick={() => setView('slide')}
              className={
                'px-3 py-1.5 rounded-sm border transition-colors ' +
                (view === 'slide'
                  ? 'bg-forest-600 text-chalk-white border-forest-700'
                  : 'bg-paper-card border-paper-line text-ink-muted hover:bg-paper-warm')
              }
            >
              內頁
            </button>
            <button
              onClick={() => setView('cover')}
              className={
                'px-3 py-1.5 rounded-sm border transition-colors ' +
                (view === 'cover'
                  ? 'bg-forest-600 text-chalk-white border-forest-700'
                  : 'bg-paper-card border-paper-line text-ink-muted hover:bg-paper-warm')
              }
            >
              封面
            </button>
          </div>
          <button
            onClick={onClose}
            className="text-ink-muted hover:text-ink text-2xl leading-none px-2"
            aria-label="關閉"
          >
            ×
          </button>
        </div>

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-5 bg-paper-warm">
          {loading ? (
            <div className="text-center py-20 text-ink-muted">載入中…</div>
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              {themes.map((t) => {
                const isActive = t.id === currentTheme;
                const previewUrl =
                  view === 'cover'
                    ? `/themes/preview/${t.id}/cover`
                    : `/themes/preview/${t.id}`;
                return (
                  <button
                    key={t.id}
                    onClick={() => {
                      onSelect(t.id);
                      onClose();
                    }}
                    className={
                      'group text-left border rounded-sm overflow-hidden transition-all ' +
                      (isActive
                        ? 'border-forest-600 ring-2 ring-forest-500 ring-offset-1 shadow-lift'
                        : 'border-paper-line hover:border-forest-400 hover:shadow-card')
                    }
                  >
                    <div className="aspect-video bg-paper-card overflow-hidden">
                      <img
                        src={previewUrl}
                        alt={t.label}
                        loading="lazy"
                        className="w-full h-full object-cover group-hover:scale-[1.02] transition-transform"
                      />
                    </div>
                    <div className="px-3 py-2 bg-paper-card">
                      <div className="text-[12.5px] text-ink truncate font-medium">
                        {t.label}
                      </div>
                      <div className="text-[10px] font-mono text-ink-faint tracking-wider">
                        {t.id} {isActive && '· 使用中'}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-paper-line bg-paper-card text-[11px] text-ink-muted flex justify-between">
          <span>共 {themes.length} 個主題 · iter 58~71 全主題系統累積</span>
          <button onClick={onClose} className="text-ink hover:underline">
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
