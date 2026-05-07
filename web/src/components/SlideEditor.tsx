import type { Slide } from '../types';

interface Props {
  slide: Slide;
  readOnly: boolean;
  onChange: (next: Slide) => void;
}

const NARRATION_TARGET = { min: 100, max: 200, hardMax: 280 };

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

  return (
    <div className="bg-forest-bg border border-border rounded p-3 mb-3">
      <div className="font-mono text-xs text-ink-muted mb-2">{slide.id}</div>

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
