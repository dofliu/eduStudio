// PR-3g: 單 step 編輯器 — 對應 v1 exam schema 的 Step
//
// 顯示三欄: _section (灰底小標, 唯讀) / display 板書 / narration 旁白
// 對齊 Track A app.py /edit 頁的版面但用 React 重畫, narration 字數即時提示。

import type { Step } from '../types';

interface Props {
  index: number;
  step: Step;
  readOnly: boolean;
  onChange: (next: Step) => void;
}

// 跟 Track A 同個分類字串
const SECTION_HINTS = [
  '題目解讀',
  '觀念切入',
  '公式導入',
  '代入計算',
  '單位檢查',
  '結果解讀',
  '易錯提醒',
  '填充作答',
];

const NARRATION_TARGET = { min: 60, max: 180, hardMax: 280 };

export function StepEditor({ index, step, readOnly, onChange }: Props) {
  const set = <K extends keyof Step>(key: K, value: Step[K]) =>
    onChange({ ...step, [key]: value });

  const narrationLen = step.narration.length;
  const narrationWarn =
    narrationLen > 0 &&
    (narrationLen < NARRATION_TARGET.min || narrationLen > NARRATION_TARGET.max);
  const narrationHard = narrationLen > NARRATION_TARGET.hardMax;

  const displayLen = step.display.length;
  const displayWarn = displayLen > 40;

  return (
    <div className="bg-forest-bg border border-border rounded p-3 mb-2">
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span className="font-mono text-xs text-ink-muted shrink-0">#{index + 1}</span>
        <select
          className="field-input text-xs py-1 px-2"
          value={step._section || ''}
          disabled={readOnly}
          onChange={(e) => set('_section', e.target.value || null)}
          title="章節分類 (Gemini 自動填, 可改)"
        >
          <option value="">(無分類)</option>
          {SECTION_HINTS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
          {/* Gemini 偶爾填非預設值, 保留原值 */}
          {step._section && !SECTION_HINTS.includes(step._section) && (
            <option value={step._section}>{step._section}</option>
          )}
        </select>
        {/* 簡報模式才有 bg_image / layout, 顯示為唯讀 hint */}
        {step.bg_type === 'slide' && step.bg_image && (
          <span className="text-xs text-ink-muted bg-stone-100 px-2 py-0.5 rounded">
            🖼 {step.bg_image.split('/').pop()} ({step.layout || 'full'})
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="field-label mb-0">💬 display (黑板)</label>
            <span
              className={
                displayWarn ? 'text-xs text-orange-700' : 'text-xs text-ink-muted'
              }
            >
              {displayLen} / 40
            </span>
          </div>
          <textarea
            className="field-input font-mono min-h-[70px] text-sm"
            value={step.display}
            disabled={readOnly}
            onChange={(e) => set('display', e.target.value)}
            placeholder="公式 / 等式 / 關鍵字 (≤ 40 字)"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="field-label mb-0">
              🗣 narration (旁白){' '}
              <span className="normal-case font-normal">
                (目標 {NARRATION_TARGET.min}~{NARRATION_TARGET.max} 字)
              </span>
            </label>
            <span
              className={
                narrationHard
                  ? 'text-xs text-red-700 font-semibold'
                  : narrationWarn
                  ? 'text-xs text-orange-700'
                  : 'text-xs text-ink-muted'
              }
            >
              {narrationLen} 字
            </span>
          </div>
          <textarea
            className="field-input min-h-[70px] text-sm"
            value={step.narration}
            disabled={readOnly}
            onChange={(e) => set('narration', e.target.value)}
            placeholder="老師口語講解, 自然口吻, 含停頓標點"
          />
        </div>
      </div>
    </div>
  );
}
