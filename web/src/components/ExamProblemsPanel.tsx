// PR-3g: v1 exam schema 編輯面板 — 把 Track A Flask /edit 頁的逐題逐 step 編輯搬到 React
//
// 跟 deck schema panel 的差別:
//  - 沒有 "section" 階層, 是 problems[] 直接展開
//  - 每題有 problem 原文 (textarea, 可改) + 多個 step (display / narration)
//  - artifact 命名 = "{problem_id}.mp4" (對應 server runner.py)
//
// 樣式對齊 JobEditor 的 sections/slides 版本, 視覺一致。

import type { Exam, Problem, Step } from '../types';
import { StepEditor } from './StepEditor';

interface Props {
  exam: Exam;
  readOnly: boolean;
  onChange: (next: Exam) => void;
  /** PR-4a: 單題重 render. 父層傳入時每題 header 多一個 🎬 按鈕. 不傳則隱藏. */
  onRenderSection?: (sectionId: string, sectionLabel: string) => void;
}

export function ExamProblemsPanel({
  exam,
  readOnly,
  onChange,
  onRenderSection,
}: Props) {
  const updateProblem = (idx: number, next: Problem) => {
    const problems = [...exam.problems];
    problems[idx] = next;
    onChange({ ...exam, problems });
  };

  const updateProblemField = <K extends keyof Problem>(
    idx: number,
    key: K,
    value: Problem[K],
  ) => {
    const p = exam.problems[idx];
    updateProblem(idx, { ...p, [key]: value });
  };

  const updateStep = (probIdx: number, stepIdx: number, next: Step) => {
    const p = exam.problems[probIdx];
    const steps = [...p.steps];
    steps[stepIdx] = next;
    updateProblem(probIdx, { ...p, steps });
  };

  return (
    <>
      {exam.problems.map((p, pIdx) => (
        <section
          key={p.id}
          className="bg-white border border-border rounded-md p-4 mb-4"
        >
          <div className="border-b-2 border-chalk-yellow pb-2 mb-3">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span className="font-mono text-xs text-ink-muted shrink-0">
                {p.id}
              </span>
              <input
                type="text"
                className="field-input flex-1 text-base font-semibold"
                value={p.number}
                disabled={readOnly}
                onChange={(e) => updateProblemField(pIdx, 'number', e.target.value)}
              />
              {typeof p.score === 'number' && (
                <span className="text-xs text-ink-muted shrink-0">
                  {p.score} 分
                </span>
              )}
              <span className="text-xs text-ink-muted shrink-0">
                {p.steps.length} steps
              </span>
              {/* PR-4a: 單題重 render */}
              {onRenderSection && (
                <button
                  onClick={() =>
                    onRenderSection(p.id, `${p.number} (${p.id})`)
                  }
                  className="btn btn-ghost text-xs shrink-0"
                  title="只重渲染本題 (其他題不動)"
                >
                  🎬 重 render 本題
                </button>
              )}
            </div>
            <textarea
              className="field-input w-full min-h-[60px] text-sm"
              value={p.problem}
              disabled={readOnly}
              onChange={(e) => updateProblemField(pIdx, 'problem', e.target.value)}
              placeholder="題目原文"
            />
          </div>

          {p.steps.map((step, sIdx) => (
            <StepEditor
              key={sIdx}
              index={sIdx}
              step={step}
              readOnly={readOnly}
              onChange={(next) => updateStep(pIdx, sIdx, next)}
            />
          ))}
        </section>
      ))}
    </>
  );
}
