// PR-3k: CreateJobForm 加入上傳模式
//
// Source-type 與輸入方式的對應:
//   exam_pdf / slides_pdf / document  → file upload (預設) 或 path
//   repo                              → 只能 path (資料夾)
//   url                               → 只能 url
//
// upload 模式呼叫 POST /upload (multipart), path/url 模式呼叫 POST /jobs (JSON)。
// 建 job 後 onCreated() 觸發 JobsIndex 重新 poll。

import { useState } from 'react';
import { api } from '../api';
import { useToast } from './Toast';
import type { SourceType } from '../types';
import { ThemeGalleryModal } from './ThemeGalleryModal';

interface Props {
  onCreated: () => void;
}

const FILE_UPLOADABLE: SourceType[] = ['exam_pdf', 'slides_pdf', 'document'];
const PATH_ONLY: SourceType[] = ['repo'];
const URL_ONLY: SourceType[] = ['url'];

type InputMode = 'upload' | 'path' | 'url';

function defaultModeFor(s: SourceType): InputMode {
  if (URL_ONLY.includes(s)) return 'url';
  if (PATH_ONLY.includes(s)) return 'path';
  return 'upload';   // exam / slides / document 預設拖檔, 不必手動填路徑
}

export function CreateJobForm({ onCreated }: Props) {
  const { show } = useToast();
  const [open, setOpen] = useState(false);
  const [sourceType, setSourceType] = useState<SourceType>('slides_pdf');
  const [inputMode, setInputMode] = useState<InputMode>('upload');
  const [path, setPath] = useState('');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [requireReview, setRequireReview] = useState(false);
  const [mock, setMock] = useState(false);
  // PR-5a + iter 28 + iter 44: theme 只對 repo / document / url 有意義
  // iter 28 移 Frieren / Naruto / Journal 三主題
  // iter 44 加 10 套 dof-* (5 v1 沉穩 + 5 v2 衝擊)
  type ThemeName =
    | 'forest' | 'navy' | 'frieren' | 'naruto' | 'journal'
    | 'dof-editorial' | 'dof-podium' | 'dof-notebook' | 'dof-shinobi' | 'dof-elven'
    | 'dof-zine' | 'dof-arcade' | 'dof-risograph' | 'dof-supergraphic' | 'dof-brutalist';
  const [theme, setTheme] = useState<ThemeName>('forest');
  // PR-5c: 燒字幕選項, 對所有 source_type 都適用
  const [hardsub, setHardsub] = useState(false);
  // iter 41: intro 串接 (個人開場), 對所有 source_type 都適用
  const [prependIntro, setPrependIntro] = useState(false);
  // iter 43: 影片長度模式 — 只對 repo / document / url 有意義
  const [lengthMode, setLengthMode] = useState<'ultra_quick' | 'quick' | 'lecture'>('quick');
  // iter 56: AI 生圖, 只對 document / repo / url 有意義
  const [aiGenerateDiagrams, setAiGenerateDiagrams] = useState(false);
  // iter 57b: AI 生 mermaid syntax (cheap text gen)
  const [aiGenerateMermaid, setAiGenerateMermaid] = useState(false);
  // iter 62: 在 intro 之後 / 主內容前插封面頁 (主題 + 講者 + 日期 + 單位)
  const [prependCover, setPrependCover] = useState(false);
  // iter 62b: 封面 meta per-job override (空字串視同未設 — 後端 fallback env / 今天)
  const [coverSpeaker, setCoverSpeaker] = useState('');
  const [coverOrg, setCoverOrg] = useState('');
  const [coverDate, setCoverDate] = useState('');
  // iter 65: 封面 narration override (空字串 → 後端 fallback 模板)
  const [coverNarration, setCoverNarration] = useState('');
  // iter 63: 結尾頁 + meta override (跟封面對稱)
  const [appendOutro, setAppendOutro] = useState(false);
  const [outroThanks, setOutroThanks] = useState('');
  const [outroUrl, setOutroUrl] = useState('');
  const [outroNarration, setOutroNarration] = useState('');
  // iter 66: outro 個人影片串接 (跟 prepend_intro 對稱)
  const [appendOutroVideo, setAppendOutroVideo] = useState(false);
  // iter 67: outro 結尾頁 QR codes
  const [showQrOnOutro, setShowQrOnOutro] = useState(false);
  const [outroYoutubeUrl, setOutroYoutubeUrl] = useState('');
  // iter 72: 主題預覽 modal
  const [galleryOpen, setGalleryOpen] = useState(false);
  // iter 76 (A3): 自訂主題 3 色 override (空 = 用主題預設)
  const [paletteBg, setPaletteBg] = useState('');
  const [palettePrimary, setPalettePrimary] = useState('');
  const [paletteHighlight, setPaletteHighlight] = useState('');
  // iter 80 (D2): 字幕樣式 — 只 hardsub 時有效
  const [subtitleFontSize, setSubtitleFontSize] = useState<number | ''>('');
  const [subtitlePrimaryColor, setSubtitlePrimaryColor] = useState('');
  const [subtitleOutlineColor, setSubtitleOutlineColor] = useState('');
  // iter 83 (B1+B2): 影片長寬比 + 解析度
  const [aspectRatio, setAspectRatio] = useState<'16:9' | '9:16'>('16:9');
  const [resolution, setResolution] = useState<'1080p' | '1440p' | '4K'>('1080p');
  const [submitting, setSubmitting] = useState(false);

  // source_type 改變時自動切到合適的 input mode
  const onSourceTypeChange = (next: SourceType) => {
    setSourceType(next);
    setInputMode(defaultModeFor(next));
    setFile(null);
    setPath('');
    setUrl('');
  };

  const supportsUpload = FILE_UPLOADABLE.includes(sourceType);
  const supportsPath = !URL_ONLY.includes(sourceType);

  // theme 只對走 pptx renderer 的 source 有效 (repo / document / url)
  const themeApplicable: SourceType[] = ['repo', 'document', 'url'];
  const showTheme = themeApplicable.includes(sourceType);
  // iter 43: length_mode 同樣只對 repo / document / url 有意義
  // exam_pdf 由題數決定影片數, slides_pdf 由頁數決定, 不適用
  const showLengthMode = themeApplicable.includes(sourceType);

  const buildOptions = () => ({
    mock,
    require_review: requireReview,
    hardsub,
    prepend_intro: prependIntro,
    ...(showTheme ? { theme } : {}),    // 不適用就不送, 後端用預設
    ...(showLengthMode ? { length_mode: lengthMode } : {}),
    // iter 56: AI 生圖 (Gemini Flash Image) — opt-in, 跟 length_mode 同條件
    ...(showLengthMode ? { ai_generate_diagrams: aiGenerateDiagrams } : {}),
    // iter 57b: AI 生 mermaid syntax (Gemini text → mermaid.ink)
    ...(showLengthMode ? { ai_generate_mermaid: aiGenerateMermaid } : {}),
    // iter 62: 封面頁
    ...(showLengthMode ? { prepend_cover: prependCover } : {}),
    // iter 62b: 封面 meta override — 只在 prepend_cover 開且非空才送
    ...(showLengthMode && prependCover && coverSpeaker.trim()
      ? { cover_speaker: coverSpeaker.trim() } : {}),
    ...(showLengthMode && prependCover && coverOrg.trim()
      ? { cover_org: coverOrg.trim() } : {}),
    ...(showLengthMode && prependCover && coverDate.trim()
      ? { cover_date: coverDate.trim() } : {}),
    // iter 65: 封面 narration override (textarea, 不 trim 內容只 trim 外圍)
    ...(showLengthMode && prependCover && coverNarration.trim()
      ? { cover_narration: coverNarration.trim() } : {}),
    // iter 63: 結尾頁 + 三個 override
    ...(showLengthMode ? { append_outro: appendOutro } : {}),
    ...(showLengthMode && appendOutro && outroThanks.trim()
      ? { outro_thanks: outroThanks.trim() } : {}),
    ...(showLengthMode && appendOutro && outroUrl.trim()
      ? { outro_url: outroUrl.trim() } : {}),
    ...(showLengthMode && appendOutro && outroNarration.trim()
      ? { outro_narration: outroNarration.trim() } : {}),
    // iter 66: outro 個人影片串接
    ...(showLengthMode ? { append_outro_video: appendOutroVideo } : {}),
    // iter 67: outro QR codes
    ...(showLengthMode && appendOutro ? { show_qr_on_outro: showQrOnOutro } : {}),
    ...(showLengthMode && appendOutro && showQrOnOutro && outroYoutubeUrl.trim()
      ? { outro_youtube_url: outroYoutubeUrl.trim() } : {}),
    // iter 76 (A3): 自訂主題 3 色 (只在主題適用時送, 空字串不送讓後端 fallback)
    ...(showTheme && paletteBg ? { palette_bg: paletteBg } : {}),
    ...(showTheme && palettePrimary ? { palette_primary: palettePrimary } : {}),
    ...(showTheme && paletteHighlight ? { palette_highlight: paletteHighlight } : {}),
    // iter 80 (D2): 字幕樣式 (只 hardsub 時送)
    ...(hardsub && subtitleFontSize !== '' ? { subtitle_font_size: subtitleFontSize } : {}),
    ...(hardsub && subtitlePrimaryColor ? { subtitle_primary_color: subtitlePrimaryColor } : {}),
    ...(hardsub && subtitleOutlineColor ? { subtitle_outline_color: subtitleOutlineColor } : {}),
    // iter 83 (B1+B2): 長寬比 + 解析度 (只在主題適用 source 送, exam_pdf/slides_pdf 不影響)
    ...(aspectRatio !== '16:9' ? { aspect_ratio: aspectRatio } : {}),
    ...(resolution !== '1080p' ? { resolution: resolution } : {}),
  });

  const submit = async () => {
    setSubmitting(true);
    try {
      if (inputMode === 'upload') {
        if (!file) {
          show('請選檔', 'error');
          return;
        }
        const r = await api.uploadFile(file, sourceType, buildOptions());
        show(`已上傳 ${file.name} 並建 job ${r.job_id}`);
      } else {
        const source = inputMode === 'url' ? { url } : { path };
        const r = await api.createJob({
          source_type: sourceType,
          source,
          options: buildOptions(),
        });
        show(`已建立 job ${r.job_id}`);
      }
      // reset
      setPath('');
      setUrl('');
      setFile(null);
      setOpen(false);
      onCreated();
    } catch (e) {
      show(`建立失敗: ${e}`, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn btn-primary mb-4">
        + 新增 Job
      </button>
    );
  }

  // submit button 是否能按
  const canSubmit =
    !submitting &&
    ((inputMode === 'upload' && file) ||
      (inputMode === 'path' && path) ||
      (inputMode === 'url' && url));

  return (
    <div className="bg-white border border-border rounded-md p-4 mb-4">
      <div className="flex items-center mb-3">
        <h3 className="font-semibold text-forest">新增 Job</h3>
        <button
          onClick={() => setOpen(false)}
          className="ml-auto btn btn-ghost"
          aria-label="close"
        >
          ✕
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="field-label">Source type</label>
          <select
            className="field-input"
            value={sourceType}
            onChange={(e) => onSourceTypeChange(e.target.value as SourceType)}
          >
            <option value="exam_pdf">exam_pdf — 考卷 PDF</option>
            <option value="slides_pdf">slides_pdf — 簡報 PDF</option>
            <option value="repo">repo — 資料夾</option>
            <option value="document">document — PDF / MD / TXT 單檔</option>
            <option value="url">url — 網頁文章</option>
          </select>
        </div>

        <div>
          <label className="field-label">輸入方式</label>
          <div className="flex gap-3 items-center text-sm pt-2">
            {supportsUpload && (
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="inputMode"
                  checked={inputMode === 'upload'}
                  onChange={() => setInputMode('upload')}
                />
                上傳檔案
              </label>
            )}
            {supportsPath && (
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="inputMode"
                  checked={inputMode === 'path'}
                  onChange={() => setInputMode('path')}
                />
                Server 端路徑
              </label>
            )}
            {URL_ONLY.includes(sourceType) && (
              <span className="text-ink-muted">URL 字串</span>
            )}
          </div>
        </div>
      </div>

      {/* 輸入區依 mode 切換 */}
      {inputMode === 'upload' && (
        <div className="mt-3">
          <label className="field-label">選擇檔案</label>
          <input
            type="file"
            className="field-input"
            accept=".pdf,.md,.txt"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          {file && (
            <div className="text-xs text-ink-muted mt-1">
              {file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB
            </div>
          )}
        </div>
      )}

      {inputMode === 'path' && (
        <div className="mt-3">
          <label className="field-label">本機絕對路徑</label>
          <input
            type="text"
            className="field-input font-mono"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="D:/path/to/source"
          />
        </div>
      )}

      {inputMode === 'url' && (
        <div className="mt-3">
          <label className="field-label">URL</label>
          <input
            type="text"
            className="field-input font-mono"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
          />
        </div>
      )}

      {/* PR-5a: pptx 主題下拉, 只對 repo / document / url 顯示
          iter 44: 加 10 套 dof-* — v1 沉穩 / v2 衝擊兩家族
          iter 72: 加「🎨 預覽」按鈕開 ThemeGalleryModal */}
      {showTheme && (
        <div className="mt-3">
          <div className="flex items-center justify-between mb-1">
            <label className="field-label !mb-0">pptx 主題</label>
            <button
              type="button"
              onClick={() => setGalleryOpen(true)}
              className="text-xs text-forest-700 hover:underline"
            >
              🎨 預覽 15 主題
            </button>
          </div>
          <select
            className="field-input"
            value={theme}
            onChange={(e) => setTheme(e.target.value as ThemeName)}
          >
            <optgroup label="課程教學 (深底)">
              <option value="forest">🌲 Forest — 深綠 + 黃 (程式設計教學)</option>
              <option value="navy">🌐 Navy — 深藍 + 青 (AI / 工程)</option>
            </optgroup>
            <optgroup label="期刊 / 學術">
              <option value="journal">📜 Journal — 米白 + 墨綠紅 (期刊 / 書冊)</option>
            </optgroup>
            <optgroup label="漫畫風格">
              <option value="frieren">❄ Frieren — 藏青 + 銀白紫 (芙莉蓮)</option>
              <option value="naruto">🔥 Naruto — 焦糖 + 火影橘 (火影)</option>
            </optgroup>
            <optgroup label="DofLab v1 · 沉穩家族">
              <option value="dof-editorial">📰 Editorial — 雜誌編輯風 (對外演講 / Demo Day)</option>
              <option value="dof-podium">🎙 Podium — 講壇 / TED 感 (Conference / Keynote)</option>
              <option value="dof-notebook">📒 Notebook — 札記風 (Journal Club / 讀書會)</option>
              <option value="dof-shinobi">🥷 Shinobi — 忍者熱血 (黑客松 / 動員會)</option>
              <option value="dof-elven">🔮 Elven — 魔法幻境 (哲學 / 認知科學)</option>
            </optgroup>
            <optgroup label="DofLab v2 · 衝擊家族">
              <option value="dof-zine">📣 Zine — 雜誌海報 (年度回顧 / 宣言式)</option>
              <option value="dof-arcade">🕹 Arcade — 街機霓虹 (Hackathon / Tech demo)</option>
              <option value="dof-risograph">🎨 Risograph — 油墨疊印 (工作坊 / 跨界)</option>
              <option value="dof-supergraphic">🟥 Supergraphic — Pentagram 大色塊 (品牌簡介)</option>
              <option value="dof-brutalist">⚠ Brutalist — 野獸派宣言 (觀點 talk / 批判)</option>
            </optgroup>
          </select>
          {/* iter 76 (A3): 自訂主題 3 色 override — 空白用主題預設 */}
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
            <span className="text-ink-muted">自訂 3 色 (留空=用主題預設):</span>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="color"
                value={paletteBg || '#1e3a2e'}
                onChange={(e) => setPaletteBg(e.target.value)}
                className="w-7 h-7 cursor-pointer border border-paper-line"
                title="背景色 bg"
              />
              <span>bg</span>
              {paletteBg && (
                <button
                  type="button"
                  onClick={() => setPaletteBg('')}
                  className="ml-1 text-ink-faint hover:text-ink"
                  title="清除"
                >×</button>
              )}
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="color"
                value={palettePrimary || '#e8e6d8'}
                onChange={(e) => setPalettePrimary(e.target.value)}
                className="w-7 h-7 cursor-pointer border border-paper-line"
                title="主色 primary (標題 / bullet 文字)"
              />
              <span>primary</span>
              {palettePrimary && (
                <button
                  type="button"
                  onClick={() => setPalettePrimary('')}
                  className="ml-1 text-ink-faint hover:text-ink"
                  title="清除"
                >×</button>
              )}
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="color"
                value={paletteHighlight || '#f5d061'}
                onChange={(e) => setPaletteHighlight(e.target.value)}
                className="w-7 h-7 cursor-pointer border border-paper-line"
                title="強調色 highlight (底線 / banner)"
              />
              <span>highlight</span>
              {paletteHighlight && (
                <button
                  type="button"
                  onClick={() => setPaletteHighlight('')}
                  className="ml-1 text-ink-faint hover:text-ink"
                  title="清除"
                >×</button>
              )}
            </label>
          </div>
        </div>
      )}

      {/* iter 43: 影片長度模式 — 只對 repo / document / url 顯示
          (exam_pdf 由題數決定影片數, slides_pdf 由頁數決定) */}
      {showLengthMode && (
        <div className="mt-3">
          <label className="field-label">影片長度</label>
          <select
            className="field-input"
            value={lengthMode}
            onChange={(e) => setLengthMode(e.target.value as 'ultra_quick' | 'quick' | 'lecture')}
          >
            <option value="ultra_quick">⚡⚡ 極短影片 — 3~5 分鐘 (Shorts / TikTok / Reels)</option>
            <option value="quick">⚡ 快速講解 — 8~15 分鐘 (YT 影片)</option>
            <option value="lecture">📚 詳細授課 — 60~180 分鐘 (上課用)</option>
          </select>
        </div>
      )}

      {/* iter 83 (B1+B2): 長寬比 + 解析度 */}
      <div className="mt-3 flex gap-3">
        <div className="flex-1">
          <label className="field-label">長寬比</label>
          <select
            className="field-input"
            value={aspectRatio}
            onChange={(e) => setAspectRatio(e.target.value as '16:9' | '9:16')}
          >
            <option value="16:9">📺 16:9 橫向 (YouTube / 一般)</option>
            <option value="9:16">📱 9:16 縱向 (Shorts / TikTok / Reels)</option>
          </select>
          {aspectRatio === '9:16' && (
            <div className="text-[10px] text-accent-coral mt-0.5">
              ⚠ 縱向 v1: 主 layout 已適配, 但部分元素 (cover/outro/signature) 位置會偏, 留待後續調
            </div>
          )}
        </div>
        <div className="flex-1">
          <label className="field-label">解析度</label>
          <select
            className="field-input"
            value={resolution}
            onChange={(e) => setResolution(e.target.value as '1080p' | '1440p' | '4K')}
          >
            <option value="1080p">1080p — Full HD (預設)</option>
            <option value="1440p">1440p — 2K (~2× 時間)</option>
            <option value="4K">4K — UHD (~3× 時間)</option>
          </select>
        </div>
      </div>

      <div className="flex items-center gap-4 mt-3 text-sm flex-wrap">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={requireReview}
            onChange={(e) => setRequireReview(e.target.checked)}
          />
          停在 awaiting_review (人工確認後再渲染)
        </label>
        {/* PR-5c: 燒字幕選項 */}
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={hardsub}
            onChange={(e) => setHardsub(e.target.checked)}
          />
          燒字幕進 MP4 (離線播放看得到; YouTube 不必勾)
        </label>
        {/* iter 80 (D2): 字幕樣式 — 勾 hardsub 才秀 */}
        {hardsub && (
          <div className="ml-6 flex flex-wrap items-center gap-3 text-xs">
            <span className="text-ink-muted">字幕樣式:</span>
            <label className="flex items-center gap-1">
              字級
              <input
                type="number"
                min={12}
                max={48}
                value={subtitleFontSize}
                onChange={(e) => setSubtitleFontSize(e.target.value === '' ? '' : Number(e.target.value))}
                placeholder="22"
                className="w-14 border rounded px-1.5 py-0.5"
              />
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="color"
                value={subtitlePrimaryColor || '#ffffff'}
                onChange={(e) => setSubtitlePrimaryColor(e.target.value)}
                className="w-7 h-7 cursor-pointer border border-paper-line"
                title="字幕字色 (預設白)"
              />
              <span>字色</span>
              {subtitlePrimaryColor && (
                <button type="button" onClick={() => setSubtitlePrimaryColor('')}
                  className="ml-0.5 text-ink-faint hover:text-ink">×</button>
              )}
            </label>
            <label className="flex items-center gap-1 cursor-pointer">
              <input
                type="color"
                value={subtitleOutlineColor || '#000000'}
                onChange={(e) => setSubtitleOutlineColor(e.target.value)}
                className="w-7 h-7 cursor-pointer border border-paper-line"
                title="字幕描邊色 (預設黑)"
              />
              <span>描邊</span>
              {subtitleOutlineColor && (
                <button type="button" onClick={() => setSubtitleOutlineColor('')}
                  className="ml-0.5 text-ink-faint hover:text-ink">×</button>
              )}
            </label>
          </div>
        )}
        {/* iter 41: intro 串接 */}
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={prependIntro}
            onChange={(e) => setPrependIntro(e.target.checked)}
          />
          串個人 intro (~8 秒開場接到主影片前)
        </label>
        {/* iter 56: AI 生圖 (Gemini Flash Image) — 只對 document/repo/url 顯示 */}
        {showLengthMode && (
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={aiGenerateDiagrams}
              onChange={(e) => setAiGenerateDiagrams(e.target.checked)}
            />
            🎨 AI 生架構圖 (每章 1 張, Gemini Flash Image, 會計費)
          </label>
        )}
        {/* iter 57b: AI 生 mermaid syntax — text gen 便宜很多 */}
        {showLengthMode && (
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={aiGenerateMermaid}
              onChange={(e) => setAiGenerateMermaid(e.target.checked)}
            />
            📐 AI 生 Mermaid 流程圖 (每章 1 張, text gen 較便宜)
          </label>
        )}
        {/* iter 62: 封面頁 — intro 之後 / 主內容前 */}
        {showLengthMode && (
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={prependCover}
              onChange={(e) => setPrependCover(e.target.checked)}
            />
            🪪 插入封面頁 (主題 + 講者 + 日期 + 單位 + 開場口白)
          </label>
        )}
        {/* iter 62b: 開封面頁時才秀 meta override 三欄, 空白 → 後端 fallback */}
        {showLengthMode && prependCover && (
          <div className="ml-6 mt-1 flex flex-wrap gap-2 text-xs">
            <input
              type="text"
              value={coverSpeaker}
              onChange={(e) => setCoverSpeaker(e.target.value)}
              placeholder="講者 (留空=預設)"
              className="border rounded px-2 py-1 w-44"
            />
            <input
              type="text"
              value={coverOrg}
              onChange={(e) => setCoverOrg(e.target.value)}
              placeholder="單位 (留空=預設)"
              className="border rounded px-2 py-1 w-56"
            />
            <input
              type="text"
              value={coverDate}
              onChange={(e) => setCoverDate(e.target.value)}
              placeholder="日期 (留空=今天)"
              className="border rounded px-2 py-1 w-36"
            />
          </div>
        )}
        {/* iter 65: 封面開場口白覆寫 — 空白用模板, 填了直接拿來 TTS */}
        {showLengthMode && prependCover && (
          <div className="ml-6 mt-1">
            <textarea
              value={coverNarration}
              onChange={(e) => setCoverNarration(e.target.value)}
              placeholder="開場口白 (留空=模板「各位好, 我是X. 今天介紹X. 本內容由X帶來…」, 建議 60~180 字)"
              className="border rounded px-2 py-1 w-full text-xs"
              rows={3}
            />
          </div>
        )}
        {/* iter 63: 結尾頁 — 跟封面對稱, 加在主內容後 */}
        {showLengthMode && (
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={appendOutro}
              onChange={(e) => setAppendOutro(e.target.checked)}
            />
            🎬 加結尾頁 (謝謝聆聽 + 講者 + 單位 + URL + 結尾口白)
          </label>
        )}
        {showLengthMode && appendOutro && (
          <div className="ml-6 mt-1 space-y-1.5">
            <div className="flex flex-wrap gap-2 text-xs">
              <input
                type="text"
                value={outroThanks}
                onChange={(e) => setOutroThanks(e.target.value)}
                placeholder="主標題 (留空=謝謝聆聽)"
                className="border rounded px-2 py-1 w-44"
              />
              <input
                type="text"
                value={outroUrl}
                onChange={(e) => setOutroUrl(e.target.value)}
                placeholder="聯絡 URL (留空=doflab.cc)"
                className="border rounded px-2 py-1 w-56"
              />
            </div>
            <textarea
              value={outroNarration}
              onChange={(e) => setOutroNarration(e.target.value)}
              placeholder="結尾口白 (留空=模板「今天的內容到此告一段落, 感謝各位的時間…」)"
              className="border rounded px-2 py-1 w-full text-xs"
              rows={3}
            />
            {/* iter 67: 結尾頁 QR codes */}
            <label className="flex items-center gap-1.5 cursor-pointer text-xs">
              <input
                type="checkbox"
                checked={showQrOnOutro}
                onChange={(e) => setShowQrOnOutro(e.target.checked)}
              />
              📲 結尾頁畫 QR code (左下=網頁, 右下=頻道)
            </label>
            {showQrOnOutro && (
              <input
                type="text"
                value={outroYoutubeUrl}
                onChange={(e) => setOutroYoutubeUrl(e.target.value)}
                placeholder="YouTube 頻道 URL (留空=youtube.com/@dofliu)"
                className="border rounded px-2 py-1 w-full text-xs"
              />
            )}
          </div>
        )}
        {/* iter 66: outro 個人影片串接 (跟 intro 對稱, 串到 final 最後) */}
        {showLengthMode && (
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={appendOutroVideo}
              onChange={(e) => setAppendOutroVideo(e.target.checked)}
            />
            🎞️ 串接 outro 個人影片 (CLAUDE_OUTRO_VIDEO_PATH, 跟 intro 對稱)
          </label>
        )}
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={mock}
            onChange={(e) => setMock(e.target.checked)}
          />
          mock (不打 Gemini)
        </label>
      </div>

      <div className="mt-4 flex gap-2">
        <button onClick={submit} disabled={!canSubmit} className="btn btn-primary">
          {submitting ? '送出中…' : '送出'}
        </button>
        <button onClick={() => setOpen(false)} className="btn btn-ghost">
          取消
        </button>
      </div>

      {/* iter 72: 主題預覽 modal */}
      {galleryOpen && (
        <ThemeGalleryModal
          currentTheme={theme}
          onSelect={(t) => setTheme(t as ThemeName)}
          onClose={() => setGalleryOpen(false)}
        />
      )}
    </div>
  );
}
