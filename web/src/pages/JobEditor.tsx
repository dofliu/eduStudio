// JobEditor — Job 編輯頁的「外殼」: 載入 / 存檔 / approve 邏輯統一,
// 內容渲染依 schema 分流到 deck 或 exam 兩個 Panel。
//
// PR-3e: deck schema (sections / slides) 編輯
// PR-3f: done 階段顯示 artifact 列 + 📺 上傳到 YouTube 入口
// PR-3g: exam schema (problems / steps) 編輯, 取代 Flask app.py /edit 頁

import { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { ExamProblemsPanel } from '../components/ExamProblemsPanel';
import { SlideEditor } from '../components/SlideEditor';
import { StatusBadge } from '../components/StatusBadge';
import { useToast } from '../components/Toast';
import type { Deck, Draft, Exam, JobRecord, Slide } from '../types';
import { isDeckDraft, isExamDraft } from '../types';

const POLL_INTERVAL_MS = 4000;

export default function JobEditor() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { show } = useToast();

  const [job, setJob] = useState<JobRecord | null>(null);
  // 使用泛型 Draft, schema 由 type guard 在 render 時辨識
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const reloadAll = useCallback(async () => {
    if (!jobId) return;
    try {
      const j = await api.getJob(jobId);
      setJob(j);
      // 只在 dirty=false 時才覆蓋本地 draft, 避免吃掉使用者尚未存檔的修改
      if (!dirty) {
        try {
          // server /draft 端點型別宣告是 Deck, 但實際回傳是 dict.
          // 我們在 client 用 Draft (= Exam | Deck | unknown) 接, runtime 由 guard 分流
          const d = (await api.getDraft(jobId)) as unknown as Draft;
          setDraft(d);
        } catch {
          setDraft(null);
        }
      }
    } catch (e) {
      show(`載入失敗: ${e}`, 'error');
    } finally {
      setLoading(false);
    }
  }, [jobId, dirty, show]);

  useEffect(() => {
    reloadAll();
    // ingesting / rendering 中持續輪詢, 其他狀態 reload 一次也無妨
    const t = setInterval(reloadAll, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [reloadAll]);

  // ---- Deck schema mutators ----
  const updateSlide = (sectionIdx: number, slideIdx: number, next: Slide) => {
    if (!draft || !isDeckDraft(draft)) return;
    const sections = [...draft.sections];
    const slides = [...sections[sectionIdx].slides];
    slides[slideIdx] = next;
    sections[sectionIdx] = { ...sections[sectionIdx], slides };
    setDraft({ ...draft, sections });
    setDirty(true);
  };

  const updateSectionTitle = (sectionIdx: number, title: string) => {
    if (!draft || !isDeckDraft(draft)) return;
    const sections = [...draft.sections];
    sections[sectionIdx] = { ...sections[sectionIdx], title };
    setDraft({ ...draft, sections });
    setDirty(true);
  };

  // ---- Exam schema mutators (整顆替換, panel 內部負責 immutable update) ----
  const onExamChange = (next: Exam) => {
    setDraft(next);
    setDirty(true);
  };

  // ---- Save / Approve ----
  const onSave = async () => {
    if (!draft || !jobId) return;
    setSaving(true);
    try {
      // server schema 是 dict, cast 過去
      await api.saveDraft(jobId, draft as unknown as Deck);
      setDirty(false);
      show('已儲存');
    } catch (e) {
      show(`儲存失敗: ${e}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const onApprove = async () => {
    if (!jobId || !draft) return;
    if (!confirm('Approve 後會立刻開始渲染, 確定?')) return;
    setSaving(true);
    try {
      if (dirty) {
        await api.saveDraft(jobId, draft as unknown as Deck);
        setDirty(false);
      }
      await api.approve(jobId);
      show('已 Approve, 渲染中...');
      setTimeout(() => navigate('/'), 1500);
    } catch (e) {
      show(`Approve 失敗: ${e}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  if (loading && !job) {
    return <div className="text-center py-10 text-ink-muted">Loading…</div>;
  }
  if (!job) {
    return (
      <div className="text-center py-10">
        <p className="text-ink-muted mb-4">Job 不存在</p>
        <Link to="/" className="btn btn-ghost">
          ← Back to Jobs
        </Link>
      </div>
    );
  }

  const canEdit = job.state === 'awaiting_review';

  if (!draft) {
    return (
      <div>
        <div className="mb-4">
          <Link to="/" className="text-forest hover:underline text-sm">
            ← Back to Jobs
          </Link>
        </div>
        <div className="bg-white border border-border rounded p-6 text-center">
          <StatusBadge state={job.state} />
          <p className="mt-4 text-ink-muted">
            deck.json 尚未產生 (job 在 {job.state} 階段)。畫面會自動更新…
          </p>
        </div>
      </div>
    );
  }

  // ---- Schema 辨識 ----
  const isExam = isExamDraft(draft);
  const isDeck = isDeckDraft(draft);

  if (!isExam && !isDeck) {
    return (
      <div>
        <div className="mb-4">
          <Link to="/" className="text-forest hover:underline text-sm">
            ← Back to Jobs
          </Link>
        </div>
        <div className="bg-white border border-border rounded p-6 text-center text-ink-muted">
          無法辨識 schema (既無 problems 也無 sections), 請檢查 jobs/&lt;id&gt;/deck.json
        </div>
      </div>
    );
  }

  // ---- 統計資訊 (toolbar 顯示) ----
  const title = isExam
    ? (draft as Exam).exam_title
    : (draft as Deck).deck_title;
  const subtitle = isExam
    ? (() => {
        const e = draft as Exam;
        const totalSteps = e.problems.reduce((s, p) => s + p.steps.length, 0);
        return `${e.problems.length} 題 · ${totalSteps} steps`;
      })()
    : (() => {
        const d = draft as Deck;
        const totalSlides = d.sections.reduce((s, sec) => s + sec.slides.length, 0);
        return `${d.sections.length} sections · ${totalSlides} slides`;
      })();

  const mp4s = job.artifacts.filter((a) => a.kind === 'mp4');

  return (
    <div>
      <div className="mb-3">
        <Link to="/" className="text-forest hover:underline text-sm">
          ← Back to Jobs
        </Link>
      </div>

      {/* PR-3f: render 完成後顯示 artifact 列 + YouTube 上傳入口 */}
      {job.state === 'done' && mp4s.length > 0 && (
        <div className="bg-white border border-border rounded-md p-4 mb-4">
          <div className="font-semibold text-forest mb-2">📦 Artifacts ({mp4s.length})</div>
          <div className="space-y-2">
            {mp4s.map((a) => {
              const yt = job.youtube_uploads?.[a.name];
              return (
                <div
                  key={a.name}
                  className="flex items-center gap-2 text-sm border-t border-border pt-2 first:border-t-0 first:pt-0 flex-wrap"
                >
                  <span className="font-mono">{a.name}</span>
                  <span className="text-ink-muted text-xs">
                    {(a.size_bytes / 1024 / 1024).toFixed(1)} MB
                  </span>
                  <a
                    href={api.artifactUrl(job.id, a.name)}
                    className="text-forest underline"
                  >
                    ▶ 預覽
                  </a>
                  <Link
                    to={`/jobs/${job.id}/publish/${encodeURIComponent(a.name)}`}
                    className={
                      'btn btn-ghost text-xs ' +
                      (yt?.state === 'done' ? 'text-green-700' : '')
                    }
                  >
                    📺{' '}
                    {yt?.state === 'done'
                      ? '已上傳 (查看)'
                      : yt?.state === 'uploading'
                      ? `上傳中 ${yt.progress_percent}%`
                      : yt?.state === 'failed'
                      ? '上傳失敗 (重試)'
                      : '上傳到 YouTube'}
                  </Link>
                  {yt?.url && (
                    <a
                      href={yt.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-forest underline break-all"
                    >
                      {yt.url}
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* sticky toolbar */}
      <div className="sticky top-0 z-10 bg-forest-bg/95 backdrop-blur py-3 border-b border-border mb-4 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-forest truncate">
            {isExam && '📝 '}
            {isDeck && '🎬 '}
            {title}
          </div>
          <div className="text-xs text-ink-muted">
            {subtitle}
            {dirty && <span className="ml-2 text-orange-700">• 未存檔</span>}
          </div>
        </div>
        <StatusBadge state={job.state} />
        <button
          onClick={onSave}
          disabled={!canEdit || saving || !dirty}
          className="btn btn-primary"
        >
          {saving ? '...' : '💾 Save'}
        </button>
        <button
          onClick={onApprove}
          disabled={!canEdit || saving}
          className="btn btn-primary"
        >
          ✓ Approve & Render
        </button>
      </div>

      {!canEdit && (
        <div className="bg-stone-100 border border-border rounded p-3 mb-4 text-sm text-ink-muted">
          目前 state=<code className="font-mono">{job.state}</code>, 為唯讀模式。僅
          <code className="font-mono mx-1">awaiting_review</code> 可儲存 / approve。
        </div>
      )}

      {/* ---- Schema-specific panel ---- */}
      {isExam && (
        <ExamProblemsPanel
          exam={draft as Exam}
          readOnly={!canEdit}
          onChange={onExamChange}
        />
      )}

      {isDeck && (
        <>
          {(draft as Deck).sections.map((sec, sIdx) => (
            <section
              key={sec.id}
              className="bg-white border border-border rounded-md p-4 mb-4"
            >
              <div className="border-b-2 border-chalk-yellow pb-2 mb-3 flex items-center gap-2">
                <span className="font-semibold text-forest text-sm shrink-0">
                  章 {sIdx + 1}:
                </span>
                <input
                  type="text"
                  className="field-input flex-1 text-base font-semibold"
                  value={sec.title}
                  disabled={!canEdit}
                  onChange={(e) => updateSectionTitle(sIdx, e.target.value)}
                />
                <span className="text-xs text-ink-muted shrink-0">
                  {sec.slides.length} slides
                </span>
              </div>
              {sec.slides.map((sl, slIdx) => (
                <SlideEditor
                  key={sl.id}
                  slide={sl}
                  readOnly={!canEdit}
                  onChange={(next) => updateSlide(sIdx, slIdx, next)}
                />
              ))}
            </section>
          ))}
        </>
      )}
    </div>
  );
}
