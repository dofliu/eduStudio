// JobEditor — UI redesign 套用後的版本
//
// 邏輯完全保留:
//   - job / draft / loading / saving / dirty state
//   - reloadAll polling
//   - updateSlide / updateSectionTitle / onExamChange / onSave / onApprove / onRenderSection
//   - 所有 schema 辨識 (isExamDraft / isDeckDraft)
//   - LogPanel / SlideEditor / ExamProblemsPanel 子元件原樣使用
//
// 視覺改動:
//   - 全域 sticky toolbar 改成 Topbar 風格
//   - Deck 模式從「整頁 scroll 所有 slides」改成 3-pane (左 list / 中 preview / 右 SlideEditor)
//     左 list 的 activeSlideId 是純 UI state, 不影響 save/render 行為
//   - Exam 模式維持 ExamProblemsPanel 的整頁流, 只換 wrapper 樣式
//   - Artifacts / YouTube / 警示 banner / log panel 全部保留, 改新版視覺

import { useEffect, useState, useCallback, useMemo } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { ExamProblemsPanel } from '../components/ExamProblemsPanel';
import { LogPanel } from '../components/LogPanel';
import { OutlineModal } from '../components/OutlineModal';
import { SlideEditor } from '../components/SlideEditor';
import { useToast } from '../components/Toast';
import { Btn, StatusPill, SourceBadge, Meter } from '../components/ui';
import type { Deck, Draft, Exam, JobRecord, Slide } from '../types';
import { isDeckDraft, isExamDraft } from '../types';

const POLL_INTERVAL_MS = 4000;

export default function JobEditor() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { show } = useToast();

  const [job, setJob] = useState<JobRecord | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  // 新增的 UI state (純前端, 不影響任何 API/save 行為)
  const [activeSlideId, setActiveSlideId] = useState<string | null>(null);
  // iter 81 (D1 v1): outline modal
  const [outlineOpen, setOutlineOpen] = useState(false);

  const reloadAll = useCallback(async () => {
    if (!jobId) return;
    try {
      const j = await api.getJob(jobId);
      setJob(j);
      if (!dirty) {
        try {
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
    const t = setInterval(reloadAll, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [reloadAll]);

  // ── Deck mutators ──────────────────────────────────────────────────────
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

  // ── Exam mutator ───────────────────────────────────────────────────────
  const onExamChange = (next: Exam) => {
    setDraft(next);
    setDirty(true);
  };

  // ── Save / Approve / Render ────────────────────────────────────────────
  const onSave = async () => {
    if (!draft || !jobId) return;
    setSaving(true);
    try {
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
    const isRetryAction = job?.state === 'failed';
    // iter 55: done 狀態下重新渲染整支 (覆蓋既有所有 mp4 + final.mp4)
    const isRerenderAll = job?.state === 'done';
    let confirmMsg: string;
    if (isRerenderAll) {
      confirmMsg = '重新渲染整支? 既有所有章節 mp4 + final.mp4 都會被覆蓋, 確定?';
    } else if (isRetryAction) {
      confirmMsg = '重試 render? 用目前 deck.json 跑 (上次失敗的 stage 會被覆蓋)';
    } else {
      confirmMsg = 'Approve 後會立刻開始渲染, 確定?';
    }
    if (!confirm(confirmMsg)) return;
    setSaving(true);
    try {
      if (dirty) {
        await api.saveDraft(jobId, draft as unknown as Deck);
        setDirty(false);
      }
      await api.approve(jobId);
      const msg = isRerenderAll
        ? '已觸發重新渲染整支...'
        : (isRetryAction ? '已重新觸發 render...' : '已 Approve, 渲染中...');
      show(msg);
      setTimeout(() => navigate('/'), 1500);
    } catch (e) {
      const label = isRerenderAll ? '重新渲染' : (isRetryAction ? '重試' : 'Approve');
      show(`${label} 失敗: ${e}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const onRenderSection = async (sectionId: string, sectionLabel: string) => {
    if (!jobId || !draft) return;
    if (!confirm(`重新渲染「${sectionLabel}」? 其他章不會動。`)) return;
    setSaving(true);
    try {
      if (dirty) {
        await api.saveDraft(jobId, draft as unknown as Deck);
        setDirty(false);
      }
      await api.renderSection(jobId, sectionId);
      show(`已觸發 ${sectionLabel} 重渲染, 進度看 JobsIndex 或本頁 state badge`);
    } catch (e) {
      show(`section render 失敗: ${e}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const canRenderSection = job?.state === 'done' || job?.state === 'failed';

  // ── 攤平的 deck slide list (only 在 isDeck 時用) ────────────────────────
  const flatSlides = useMemo(() => {
    if (!draft || !isDeckDraft(draft)) return [] as Array<{
      slide: Slide; sectionIdx: number; slideIdx: number; sectionTitle: string;
    }>;
    return draft.sections.flatMap((sec, si) =>
      sec.slides.map((sl, sli) => ({
        slide: sl,
        sectionIdx: si,
        slideIdx: sli,
        sectionTitle: sec.title,
      })),
    );
  }, [draft]);

  // 預設選第一張
  useEffect(() => {
    if (!activeSlideId && flatSlides.length > 0) {
      setActiveSlideId(flatSlides[0].slide.id);
    }
  }, [activeSlideId, flatSlides]);

  // ── early returns ──────────────────────────────────────────────────────
  if (loading && !job) {
    return <div className="text-center py-10 text-ink-muted">Loading…</div>;
  }
  if (!job) {
    return (
      <div className="text-center py-10">
        <p className="text-ink-muted mb-4">Job 不存在</p>
        <Link to="/" className="text-forest-600 hover:underline">← Back to Jobs</Link>
      </div>
    );
  }

  const canEdit =
    job.state === 'awaiting_review' ||
    job.state === 'failed' ||
    job.state === 'done';
  const isRetry = job.state === 'failed';
  const showStaleArtifactWarning = job.state === 'done' && dirty;

  if (!draft) {
    return (
      <div className="px-10 py-8 max-w-4xl">
        <Link to="/" className="text-forest-600 hover:underline text-[12px] font-mono">← Back to Jobs</Link>
        <div className="bg-paper-card border border-paper-line rounded-sm p-8 text-center mt-4">
          <StatusPill state={job.state} />
          <p className="mt-4 text-ink-muted">deck.json 尚未產生 (job 在 {job.state} 階段)。畫面會自動更新…</p>
        </div>
      </div>
    );
  }

  const isExam = isExamDraft(draft);
  const isDeck = isDeckDraft(draft);

  if (!isExam && !isDeck) {
    return (
      <div className="px-10 py-8 max-w-4xl">
        <Link to="/" className="text-forest-600 hover:underline text-[12px] font-mono">← Back to Jobs</Link>
        <div className="bg-paper-card border border-paper-line rounded-sm p-8 text-center mt-4 text-ink-muted">
          無法辨識 schema (既無 problems 也無 sections), 請檢查 jobs/&lt;id&gt;/deck.json
        </div>
      </div>
    );
  }

  const title = isExam ? (draft as Exam).exam_title : (draft as Deck).deck_title;
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
  const finalMp4 = mp4s.find((a) => a.name === 'final.mp4');
  const sectionMp4s = mp4s.filter((a) => a.name !== 'final.mp4');

  // 攤平結構, 找目前 active slide (deck 模式)
  const active = isDeck
    ? flatSlides.find((s) => s.slide.id === activeSlideId) || flatSlides[0]
    : null;

  return (
    <div className="flex flex-col h-screen">
      {/* ── Compact header (一橫排, 不再堆 3 行) ─────────────────────── */}
      <header className="border-b border-paper-line bg-paper px-7 py-2.5 flex items-center gap-3">
        <Link to="/" className="text-[11px] font-mono text-forest-600 hover:underline shrink-0" title="Back to Jobs">←</Link>

        <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-ink-muted shrink-0">04 · EDIT</span>

        <h1 className="font-display text-[20px] leading-[1.15] text-forest-700 truncate flex-1 min-w-0">
          {isExam ? '📝 ' : '🎬 '}{title}
        </h1>

        <span className="text-[10.5px] text-ink-muted font-mono shrink-0 hidden md:inline">{subtitle}</span>
        <SourceBadge type={job.source_type} size="sm" />
        <StatusPill state={job.state} size="sm" />
        {dirty && (
          <span className="text-[10.5px] font-mono text-accent-coral inline-flex items-center gap-1 shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-coral"></span>未存檔
          </span>
        )}

        <div className="flex items-center gap-1.5 shrink-0">
          {/* iter 81 (D1 v1): outline 預覽 — exam_pdf 沒 outline 所以隱藏 */}
          {!isExam && (
            <Btn kind="ghost" size="sm" onClick={() => setOutlineOpen(true)}>
              📋 outline
            </Btn>
          )}
          <Btn kind="ghost" size="sm" onClick={onSave} disabled={!canEdit || saving || !dirty}>
            {saving ? '...' : '💾 Save'}
          </Btn>
          {/* iter 55: done 狀態加「重新渲染整支」按鈕, 覆蓋所有既有 mp4 + final.
              awaiting_review / failed 用既有 Approve / 重試 按鈕. */}
          {(job.state === 'awaiting_review' || job.state === 'failed') && (
            <Btn
              kind="primary"
              size="sm"
              onClick={onApprove}
              disabled={!canEdit || saving}
              title={isRetry ? '用目前 deck.json 重新跑 render' : undefined}
            >
              {isRetry ? '🔄 重試' : '✓ Approve & Render'}
            </Btn>
          )}
          {job.state === 'done' && (
            <Btn
              kind="primary"
              size="sm"
              onClick={onApprove}
              disabled={!canEdit || saving}
              title="用目前 deck.json 重 render 全部章節, 覆蓋既有所有 mp4 + final.mp4"
            >
              🔁 重新渲染整支
            </Btn>
          )}
        </div>
      </header>

      {/* ── Banners + artifacts — 一橫排策略, banner 限高 ────────────── */}
      <div className="px-7 py-2 space-y-1.5 border-b border-paper-line">
        <LogPanel jobId={job.id} jobState={job.state} />

        {isRetry && job.error && (
          <div className="border-l-2 border-accent-coral pl-3 py-1 bg-paper-warm flex items-center gap-2 text-[11.5px]">
            <span className="font-mono uppercase tracking-[0.18em] text-accent-coral shrink-0">err</span>
            <span className="text-ink font-mono break-all truncate">{job.error}</span>
            <span className="text-ink-muted shrink-0 ml-auto">可直接按「🔄 重試」</span>
          </div>
        )}

        {showStaleArtifactWarning && (
          <div className="border-l-2 border-chalk-yellowDark pl-3 py-1 bg-chalk-yellow/15 text-[11.5px] text-ink">
            ⚠ deck 已改, mp4 仍是舊版。先 💾 Save, 再到下方對應章節「🎬 重 render 本章」。
          </div>
        )}

        {!canEdit && (
          <div className="bg-paper-warm border border-paper-line rounded-sm px-2.5 py-1 text-[11.5px] text-ink-muted">
            state=<code className="font-mono text-ink">{job.state}</code> · 唯讀模式
          </div>
        )}

        {/* Artifacts — 改成一個 details, 預設摺疊, 不再吃掉版面 */}
        {job.state === 'done' && mp4s.length > 0 && (
          <details className="border border-paper-line rounded-sm bg-paper-card" open>
            <summary className="cursor-pointer px-3 py-1.5 flex items-center gap-2 text-[12px] select-none">
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-muted shrink-0">artifacts</span>
              {finalMp4 && (
                <>
                  <span className="font-mono">🎬 {finalMp4.name}</span>
                  <span className="text-[10.5px] text-ink-muted font-mono">{(finalMp4.size_bytes / 1024 / 1024).toFixed(1)} MB</span>
                  <a
                    href={api.artifactUrl(job.id, finalMp4.name)}
                    onClick={(e) => e.stopPropagation()}
                    className="text-forest-600 underline decoration-dotted"
                  >▶ 預覽</a>
                  <Link
                    to={`/jobs/${job.id}/publish/${encodeURIComponent(finalMp4.name)}`}
                    onClick={(e) => e.stopPropagation()}
                    className="text-forest-600 underline decoration-dotted"
                  >
                    📺 {(() => {
                      const yt = job.youtube_uploads?.[finalMp4.name];
                      return yt?.state === 'done' ? '已上傳'
                        : yt?.state === 'uploading' ? `${yt.progress_percent}%`
                        : yt?.state === 'failed' ? '上傳失敗'
                        : '上傳 YT';
                    })()}
                  </Link>
                </>
              )}
              {sectionMp4s.length > 0 && (
                <span className="text-[10.5px] text-ink-muted ml-auto shrink-0">+{sectionMp4s.length} 章獨立 ▾</span>
              )}
            </summary>
            {sectionMp4s.length > 0 && (
              <div className="px-3 pb-2 pt-0.5 space-y-1">
                {sectionMp4s.map((a) => {
                  const yt = job.youtube_uploads?.[a.name];
                  return (
                    <div key={a.name} className="flex items-center gap-2 text-[11.5px] flex-wrap border-t border-paper-line pt-1.5">
                      <span className="font-mono">{a.name}</span>
                      <span className="text-[10.5px] text-ink-muted font-mono">{(a.size_bytes / 1024 / 1024).toFixed(1)} MB</span>
                      <a href={api.artifactUrl(job.id, a.name)} className="text-forest-600 underline decoration-dotted">▶</a>
                      <Link
                        to={`/jobs/${job.id}/publish/${encodeURIComponent(a.name)}`}
                        className={'underline decoration-dotted ' + (yt?.state === 'done' ? 'text-forest-700' : 'text-forest-600')}
                      >
                        📺 {yt?.state === 'done' ? '已上傳'
                          : yt?.state === 'uploading' ? `${yt.progress_percent}%`
                          : yt?.state === 'failed' ? '失敗'
                          : '上傳'}
                      </Link>
                    </div>
                  );
                })}
              </div>
            )}
          </details>
        )}
      </div>

      {/* ── 主編輯區 ────────────────────────────────────────────────── */}
      {isDeck ? (
        <DeckThreePane
          deck={draft as Deck}
          flatSlides={flatSlides}
          active={active}
          activeSlideId={activeSlideId}
          setActiveSlideId={setActiveSlideId}
          canEdit={canEdit}
          canRenderSection={canRenderSection}
          saving={saving}
          updateSlide={updateSlide}
          updateSectionTitle={updateSectionTitle}
          onRenderSection={onRenderSection}
          jobId={jobId}
        />
      ) : (
        <div className="flex-1 overflow-y-auto scrollbar-thin px-10 py-4">
          {/* Exam 維持原 ExamProblemsPanel 的整頁流, 加個 hint */}
          <div className="mb-4 text-[12px] text-ink-muted">每題下方有 step list, 改完按上方的 💾 Save 存草稿。</div>
          <ExamProblemsPanel
            exam={draft as Exam}
            readOnly={!canEdit}
            onChange={onExamChange}
            onRenderSection={canRenderSection ? onRenderSection : undefined}
          />
        </div>
      )}

      {/* iter 81 (D1 v1): outline 預覽 modal */}
      {outlineOpen && jobId && (
        <OutlineModal jobId={jobId} onClose={() => setOutlineOpen(false)} />
      )}
    </div>
  );
}

// ─── Deck 3-pane workspace ────────────────────────────────────────────────

interface ThreePaneProps {
  deck: Deck;
  flatSlides: Array<{ slide: Slide; sectionIdx: number; slideIdx: number; sectionTitle: string }>;
  active: { slide: Slide; sectionIdx: number; slideIdx: number; sectionTitle: string } | null | undefined;
  activeSlideId: string | null;
  setActiveSlideId: (id: string) => void;
  canEdit: boolean;
  canRenderSection: boolean;
  saving: boolean;
  updateSlide: (sectionIdx: number, slideIdx: number, next: Slide) => void;
  updateSectionTitle: (sectionIdx: number, title: string) => void;
  onRenderSection: (sectionId: string, sectionLabel: string) => void;
  jobId?: string;   // iter 54: 透傳給 SlideEditor 讓 figure picker 拉 list
}

function DeckThreePane({
  deck, flatSlides, active, activeSlideId, setActiveSlideId,
  canEdit, canRenderSection, saving,
  updateSlide, updateSectionTitle, onRenderSection,
  jobId,
}: ThreePaneProps) {
  const totalSlides = flatSlides.length;
  const activeFlatIdx = flatSlides.findIndex((s) => s.slide.id === activeSlideId);

  return (
    <div className="flex-1 flex overflow-hidden min-h-0">
      {/* LEFT — slide list, 一個 section 一段 */}
      <div className="w-[260px] shrink-0 border-r border-paper-line flex flex-col bg-paper">
        <div className="px-4 py-3 border-b border-paper-line">
          <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-muted">slides · {totalSlides}</span>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {deck.sections.map((sec, si) => (
            <div key={sec.id} className="border-b border-paper-line last:border-b-0">
              <div className="px-4 py-2.5 bg-paper-warm sticky top-0 z-10">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-[10px] text-ink-faint num shrink-0">CH {String(si + 1).padStart(2, '0')}</span>
                  <input
                    type="text"
                    className="flex-1 bg-transparent text-[12px] font-medium text-forest-700 focus:outline-none focus:ring-1 focus:ring-chalk-yellow rounded-sm px-1 -mx-1"
                    value={sec.title}
                    disabled={!canEdit}
                    onChange={(e) => updateSectionTitle(si, e.target.value)}
                  />
                  <span className="font-mono text-[10px] text-ink-muted shrink-0">{sec.slides.length}</span>
                </div>
              </div>
              {sec.slides.map((sl, sli) => {
                const sel = sl.id === activeSlideId;
                const flatIdx = deck.sections.slice(0, si).reduce((s, x) => s + x.slides.length, 0) + sli;
                return (
                  <button
                    key={sl.id}
                    onClick={() => setActiveSlideId(sl.id)}
                    className={
                      'w-full text-left px-4 py-2.5 flex gap-3 items-start border-l-2 transition-colors ' +
                      (sel ? 'bg-chalk-yellow/40 border-forest-600' : 'border-transparent hover:bg-paper-warm')
                    }
                  >
                    <span className="font-mono text-[10px] text-ink-faint num shrink-0 mt-0.5 w-5">{String(flatIdx + 1).padStart(2, '0')}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[12.5px] font-medium text-ink leading-tight truncate">{sl.title}</div>
                      <div className="text-[10.5px] text-ink-muted mt-0.5">
                        {sl.bullets.length} bullets · {sl.narration.length}字
                      </div>
                    </div>
                    {sl.code_snippet && <span className="font-mono text-[9px] text-accent-plum mt-1">{'</>'}</span>}
                  </button>
                );
              })}
              {canRenderSection && (
                <div className="px-4 py-2 bg-paper">
                  <Btn
                    kind="quiet"
                    size="sm"
                    className="!w-full !justify-center !text-[11px]"
                    onClick={() => onRenderSection(sec.id, `章 ${si + 1} ${sec.title}`)}
                    disabled={saving}
                  >
                    🎬 重 render 本章
                  </Btn>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* MIDDLE — preview */}
      <div className="flex-1 overflow-y-auto scrollbar-thin paper-grain min-w-0">
        {active && (
          <div className="py-7 px-8">
            <div className="flex items-center gap-3 mb-5 text-[12px] text-ink-muted flex-wrap">
              <span className="font-mono">section {String(active.sectionIdx + 1).padStart(2, '0')}</span>
              <span>→</span>
              <span className="truncate">{active.sectionTitle}</span>
              <span>→</span>
              <span className="font-mono">slide {activeFlatIdx + 1} / {totalSlides}</span>
              <div className="ml-auto flex items-center gap-1">
                <Btn
                  kind="quiet"
                  size="sm"
                  onClick={() => setActiveSlideId(flatSlides[Math.max(0, activeFlatIdx - 1)].slide.id)}
                  disabled={activeFlatIdx <= 0}
                >← 上一張</Btn>
                <Btn
                  kind="quiet"
                  size="sm"
                  onClick={() => setActiveSlideId(flatSlides[Math.min(flatSlides.length - 1, activeFlatIdx + 1)].slide.id)}
                  disabled={activeFlatIdx >= flatSlides.length - 1}
                >下一張 →</Btn>
              </div>
            </div>

            <SlidePreview slide={active.slide} theme={null} />

            {/* narration / meta strip */}
            <div className="mt-6">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-muted">narration · 老師口語旁白</span>
                <div className="flex items-center gap-3 text-[11px] text-ink-muted">
                  <span>{active.slide.narration.length} 字</span>
                  <span className="font-mono">est. {Math.round(active.slide.narration.length / 4.2)}s</span>
                  <span className="font-mono">bullets · {active.slide.bullets.length}</span>
                </div>
              </div>
              <div className="rounded-sm border-l-2 border-forest-500 bg-paper-card px-4 py-3.5 text-[13.5px] leading-relaxed text-ink">
                {active.slide.narration || <span className="text-ink-muted italic">(尚無 narration)</span>}
              </div>
            </div>

            {/* slide preview chart bottom — narration length 對齊提示 */}
            <NarrationGauge length={active.slide.narration.length} />
          </div>
        )}
      </div>

      {/* RIGHT — SlideEditor */}
      <div className="w-[400px] shrink-0 border-l border-paper-line bg-paper flex flex-col overflow-hidden">
        <div className="px-5 py-3 border-b border-paper-line flex items-center">
          <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-muted">edit · slide {activeFlatIdx + 1}</span>
          <span className="ml-auto text-[10px] font-mono text-ink-faint">{active?.slide.id}</span>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin p-4">
          {active ? (
            <SlideEditor
              key={active.slide.id}
              slide={active.slide}
              readOnly={!canEdit}
              onChange={(next) => updateSlide(active.sectionIdx, active.slideIdx, next)}
              jobId={jobId}
            />
          ) : (
            <div className="text-[12px] text-ink-muted text-center py-8">選一張 slide 開始編輯</div>
          )}
        </div>
      </div>
    </div>
  );
}

function NarrationGauge({ length }: { length: number }) {
  const min = 100, max = 200, hard = 280;
  const pct = Math.min(1, length / hard);
  const status = length === 0 ? 'empty'
    : length < min ? 'short'
    : length > hard ? 'over'
    : length > max ? 'long'
    : 'ok';
  const color =
    status === 'ok'    ? 'text-forest-600' :
    status === 'over'  ? 'text-accent-coral' :
    status === 'long'  ? 'text-chalk-yellowDark' :
                         'text-ink-muted';
  return (
    <div className="mt-4">
      <div className="flex items-center justify-between mb-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-ink-muted">
        <span>narration 長度</span>
        <span className={color}>{length} / 目標 {min}~{max}</span>
      </div>
      <div className="relative">
        <Meter
          value={pct}
          tone={status === 'over' ? 'coral' : status === 'long' ? 'yellow' : 'forest'}
        />
        <div className="absolute top-0 h-1 w-px bg-ink-faint" style={{ left: `${(min / hard) * 100}%` }} />
        <div className="absolute top-0 h-1 w-px bg-ink-faint" style={{ left: `${(max / hard) * 100}%` }} />
      </div>
    </div>
  );
}

// ── 16:9 slide preview ───────────────────────────────────────────────────
// 注意: 這只是「視覺預覽」, 真正 render 仍由 server pptx renderer 跑.
// 不要在這裡塞太多邏輯, 它只負責把 deck.json 的內容用近似的版型顯示出來.

function SlidePreview({ slide, theme }: { slide: Slide; theme: string | null }) {
  const themeMap: Record<string, { bg: string; fg: string; body: string; accent: string }> = {
    forest:  { bg: '#152822', fg: '#ffd96b', body: '#e8e6d8', accent: '#b4dcc8' },
    navy:    { bg: '#1a2a4a', fg: '#ffd96b', body: '#e8e6d8', accent: '#b4dcc8' },
    journal: { bg: '#f2ecd6', fg: '#1e3a2e', body: '#2a3a32', accent: '#7a3c52' },
    naruto:  { bg: '#1e0e08', fg: '#ffc88c', body: '#f0d4a8', accent: '#c8553d' },
  };
  const t = themeMap[theme || 'forest'] || themeMap.forest;
  const hasCode = !!slide.code_snippet;
  // 簡報模式 (slides_pdf): 用實際投影片圖, 不繪製近似版型
  const slideImgUrl = slide.bg_image ? api.slideImageUrl(slide.bg_image) : null;

  if (slideImgUrl) {
    return (
      <div className="rounded-sm overflow-hidden shadow-lift border border-paper-edge bg-black" style={{ aspectRatio: '16/9' }}>
        <img src={slideImgUrl} alt={slide.title} className="w-full h-full object-contain" loading="lazy" />
      </div>
    );
  }

  return (
    <div className="rounded-sm overflow-hidden shadow-lift border border-paper-edge" style={{ aspectRatio: '16/9' }}>
      <div
        className="w-full h-full p-10 flex flex-col"
        style={{ background: t.bg, color: t.body, fontFamily: (theme === 'journal') ? '"Instrument Serif", serif' : 'inherit' }}
      >
        <div className="flex items-baseline gap-3 mb-6">
          <div className="font-mono text-[12px] uppercase tracking-[0.2em] opacity-60" style={{ color: t.accent }}>
            slide · {slide.id}
          </div>
          <div className="h-px flex-1" style={{ background: 'currentColor', opacity: 0.15 }}></div>
        </div>
        <h2 className="text-[40px] leading-[1.05] mb-7 font-display" style={{ color: t.fg }}>{slide.title}</h2>

        {hasCode ? (
          <div className="grid grid-cols-[1fr_1.3fr] gap-7 flex-1 min-h-0">
            <ul className="space-y-3.5 self-start">
              {slide.bullets.map((b, i) => (
                <li key={i} className="flex gap-3 text-[18px] leading-[1.35]">
                  <span style={{ color: t.accent }} className="font-mono text-[16px] mt-0.5">▸</span>
                  <span>{b}</span>
                </li>
              ))}
            </ul>
            <div className="rounded-sm border self-start w-full" style={{ borderColor: 'rgba(255,255,255,0.12)', background: 'rgba(0,0,0,0.25)' }}>
              <div className="px-3 py-1.5 font-mono text-[11px] border-b" style={{ borderColor: 'rgba(255,255,255,0.1)', color: t.accent }}>
                {slide.code_lang || 'code'} · preview
              </div>
              <pre className="px-4 py-3 font-mono text-[12px] leading-[1.55] whitespace-pre-wrap overflow-hidden" style={{ color: t.body }}>{slide.code_snippet}</pre>
            </div>
          </div>
        ) : (
          <ul className="space-y-4 flex-1">
            {slide.bullets.map((b, i) => (
              <li key={i} className="flex gap-4 text-[22px] leading-[1.3]">
                <span style={{ color: t.accent }} className="font-mono text-[20px] mt-1">▸</span>
                <span>{b}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-auto flex items-center justify-between text-[11px] font-mono" style={{ color: t.accent, opacity: 0.55 }}>
          <span>autoSolverVideo · preview</span>
          <span>{slide.id}</span>
        </div>
      </div>
    </div>
  );
}
