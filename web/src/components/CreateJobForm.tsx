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
  const [lengthMode, setLengthMode] = useState<'quick' | 'lecture'>('quick');
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
          iter 44: 加 10 套 dof-* — v1 沉穩 / v2 衝擊兩家族 */}
      {showTheme && (
        <div className="mt-3">
          <label className="field-label">pptx 主題</label>
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
            onChange={(e) => setLengthMode(e.target.value as 'quick' | 'lecture')}
          >
            <option value="quick">⚡ 快速講解 — 8~15 分鐘 (YT 影片)</option>
            <option value="lecture">📚 詳細授課 — 60~180 分鐘 (上課用)</option>
          </select>
        </div>
      )}

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
    </div>
  );
}
