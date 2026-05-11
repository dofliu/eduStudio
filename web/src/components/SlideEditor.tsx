import { api } from '../api';
import type { Slide } from '../types';

interface Props {
  slide: Slide;
  readOnly: boolean;
  onChange: (next: Slide) => void;
}

const NARRATION_TARGET = { min: 100, max: 200, hardMax: 280 };
// Phase 4: split-left 右半文字區能塞的 bullets 大概是 4~5 條 (多行) / 12 條 (單行) 上限,
// 超過會被 renderer 靜默截斷。給編輯者一個 visible cue。
const SPLIT_LEFT_BULLETS_SOFT_MAX = 5;

export function SlideEditor({ slide, readOnly, onChange }: Props) {
  const set = <K extends keyof Slide>(key: K, value: Slide[K]) =>
    onChange({ ...slide, [key]: value });

  const setBullet = (idx: number, value: string) => {
    const bullets = [...slide.bullets];
    bullets[idx] = value;
    set('bullets', bullets);
  };
  const addBullet = () => set('bullets', [...slide.bullets, '']);
  const removeBullet = (idx: number) =>
    set('bullets', slide.bullets.filter((_, i) => i !== idx));

  const narrationLen = slide.narration.length;
  const narrationWarn =
    narrationLen > 0 && (narrationLen < NARRATION_TARGET.min || narrationLen > NARRATION_TARGET.max);
  const narrationHard = narrationLen > NARRATION_TARGET.hardMax;

  // PR-3h: 簡報 slide 才有 bg_image (其他 source 為 undefined)。
  // 簡報模式 bullets / code 沒意義, 隱藏那些欄位讓畫面乾淨。
  const isSlideMode = !!slide.bg_image;
  const slideImgUrl = api.slideImageUrl(slide.bg_image);
  // Phase 4: split-left 右半才會渲染 title + bullets, full 仍然只放投影片本身
  const layout = slide.layout || 'full';
  const showBulletsInSlideMode = isSlideMode && layout === 'split-left';

  return (
    <div className="bg-forest-bg border border-border rounded p-3 mb-3">
      <div className="font-mono text-xs text-ink-muted mb-2">
        {slide.id}
        {isSlideMode && (
          <span className="ml-2 text-chalk-yellow">📊 簡報模式 ({layout})</span>
        )}
      </div>

      {/* PR-3h: 簡報縮圖預覽 — 點開大圖 */}
      {isSlideMode && slideImgUrl && (
        <div className="mb-3 bg-stone-900 rounded p-2">
          <a href={slideImgUrl} target="_blank" rel="noreferrer" title="點擊看大圖">
            <img
              src={slideImgUrl}
              alt={slide.title}
              className="w-full max-w-md rounded border border-border block mx-auto"
              loading="lazy"
            />
          </a>
        </div>
      )}

      <div className="mb-3">
        <label className="field-label">Title</label>
        <input
          type="text"
          className="field-input"
          value={slide.title}
          disabled={readOnly}
          onChange={(e) => set('title', e.target.value)}
        />
      </div>

      {/* Phase 4: 簡報模式 layout 切換 (full = 投影片整版, split-left = 左圖右字) */}
      {isSlideMode && (
        <div className="mb-3">
          <label className="field-label">Layout</label>
          <select
            className="field-input"
            value={layout}
            disabled={readOnly}
            onChange={(e) => set('layout', e.target.value || 'full')}
          >
            <option value="full">full — 投影片整版</option>
            <option value="split-left">split-left — 左圖 + 右側 title/bullets</option>
          </select>
        </div>
      )}

      {/* 非簡報模式 OR 簡報模式 + split-left 都顯示 bullets (split-left 的右半要靠它). */}
      {/* 但 code/file_path 永遠不在簡報模式渲染, 簡報模式整段隱藏避免誤導. */}
      {!isSlideMode ? (
        <>
          <div className="mb-3">
            <label className="field-label">Bullets</label>
            <ul className="space-y-1.5">
              {slide.bullets.map((b, i) => (
                <li key={i} className="flex gap-1.5">
                  <input
                    type="text"
                    className="field-input flex-1"
                    value={b}
                    disabled={readOnly}
                    onChange={(e) => setBullet(i, e.target.value)}
                  />
                  {!readOnly && (
                    <button
                      onClick={() => removeBullet(i)}
                      className="btn btn-ghost"
                      title="刪除"
                    >
                      ×
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {!readOnly && (
              <button onClick={addBullet} className="btn btn-ghost mt-2">
                + add bullet
              </button>
            )}
          </div>

          <div className="mb-3">
            <label className="field-label">Code snippet (留空 = 不放程式碼)</label>
            <textarea
              className="field-input font-mono min-h-[100px]"
              value={slide.code_snippet || ''}
              disabled={readOnly}
              onChange={(e) => set('code_snippet', e.target.value || null)}
            />
          </div>

          <div className="mb-3">
            <label className="field-label">File path (code 來源, 例 core/foo.py)</label>
            <input
              type="text"
              className="field-input font-mono"
              value={slide.file_path || ''}
              disabled={readOnly}
              onChange={(e) => set('file_path', e.target.value || null)}
            />
          </div>
        </>
      ) : showBulletsInSlideMode ? (
        <div className="mb-3">
          <label className="field-label">
            Bullets{' '}
            <span className="normal-case font-normal text-ink-muted">
              (渲染在右半,建議 ≤ {SPLIT_LEFT_BULLETS_SOFT_MAX} 條,過多會被截斷)
            </span>
          </label>
          {slide.bullets.length > SPLIT_LEFT_BULLETS_SOFT_MAX && (
            <div className="text-xs text-orange-700 mb-1">
              ⚠ 目前 {slide.bullets.length} 條超出建議上限,渲染時最末幾條可能被截掉
            </div>
          )}
          <ul className="space-y-1.5">
            {slide.bullets.map((b, i) => (
              <li key={i} className="flex gap-1.5">
                <input
                  type="text"
                  className="field-input flex-1"
                  value={b}
                  disabled={readOnly}
                  onChange={(e) => setBullet(i, e.target.value)}
                />
                {!readOnly && (
                  <button
                    onClick={() => removeBullet(i)}
                    className="btn btn-ghost"
                    title="刪除"
                  >
                    ×
                  </button>
                )}
              </li>
            ))}
          </ul>
          {!readOnly && (
            <button onClick={addBullet} className="btn btn-ghost mt-2">
              + add bullet
            </button>
          )}
        </div>
      ) : null}

      <div className="mb-1">
        <div className="flex items-center justify-between mb-1">
          <label className="field-label mb-0">
            Narration <span className="normal-case font-normal">(目標 100~200 字)</span>
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
          className="field-input min-h-[80px]"
          value={slide.narration}
          disabled={readOnly}
          onChange={(e) => set('narration', e.target.value)}
        />
      </div>
    </div>
  );
}
