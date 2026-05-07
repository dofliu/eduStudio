import { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { SlideEditor } from '../components/SlideEditor';
import { StatusBadge } from '../components/StatusBadge';
import { useToast } from '../components/Toast';
import type { Deck, JobRecord, Slide } from '../types';

const POLL_INTERVAL_MS = 4000;

export default function JobEditor() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const { show } = useToast();

  const [job, setJob] = useState<JobRecord | null>(null);
  const [deck, setDeck] = useState<Deck | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const reloadAll = useCallback(async () => {
    if (!jobId) return;
    try {
      const j = await api.getJob(jobId);
      setJob(j);
      // 只在 dirty=false 時才覆蓋本地 deck, 避免吃掉使用者尚未存檔的修改
      if (!dirty) {
        try {
          const d = await api.getDraft(jobId);
          setDeck(d);
        } catch {
          // 還沒有 deck (ingest 中) — 不算錯
          setDeck(null);
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
    // rendering / ingesting 中持續輪詢, 其他狀態 reload 一次就停
    const t = setInterval(reloadAll, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [reloadAll]);

  const updateSlide = (sectionIdx: number, slideIdx: number, next: Slide) => {
    if (!deck) return;
    const sections = [...deck.sections];
    const slides = [...sections[sectionIdx].slides];
    slides[slideIdx] = next;
    sections[sectionIdx] = { ...sections[sectionIdx], slides };
    setDeck({ ...deck, sections });
    setDirty(true);
  };

  const updateSectionTitle = (sectionIdx: number, title: string) => {
    if (!deck) return;
    const sections = [...deck.sections];
    sections[sectionIdx] = { ...sections[sectionIdx], title };
    setDeck({ ...deck, sections });
    setDirty(true);
  };

  const onSave = async () => {
    if (!deck || !jobId) return;
    setSaving(true);
    try {
      await api.saveDraft(jobId, deck);
      setDirty(false);
      show('已儲存');
    } catch (e) {
      show(`儲存失敗: ${e}`, 'error');
    } finally {
      setSaving(false);
    }
  };

  const onApprove = async () => {
    if (!jobId || !deck) return;
    if (!confirm('Approve 後會立刻開始渲染, 確定?')) return;
    setSaving(true);
    try {
      if (dirty) {
        await api.saveDraft(jobId, deck);
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

  if (!deck) {
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

  // v1 exam schema 不在這裡編
  if (!deck.sections) {
    return (
      <div>
        <div className="mb-4">
          <Link to="/" className="text-forest hover:underline text-sm">
            ← Back to Jobs
          </Link>
        </div>
        <div className="bg-white border border-border rounded p-6 text-center text-ink-muted">
          這是 v1 exam schema (考卷檢討), 請使用 Flask <code>app.py</code> 介面 (port 5000) 編輯。
        </div>
      </div>
    );
  }

  const totalSlides = deck.sections.reduce((s, sec) => s + sec.slides.length, 0);

  return (
    <div>
      <div className="mb-3">
        <Link to="/" className="text-forest hover:underline text-sm">
          ← Back to Jobs
        </Link>
      </div>

      {/* sticky toolbar */}
      <div className="sticky top-0 z-10 bg-forest-bg/95 backdrop-blur py-3 border-b border-border mb-4 flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-forest truncate">{deck.deck_title}</div>
          <div className="text-xs text-ink-muted">
            {deck.sections.length} sections · {totalSlides} slides
            {dirty && <span className="ml-2 text-orange-700">• 未存檔</span>}
          </div>
        </div>
        <StatusBadge state={job.state} />
        <button onClick={onSave} disabled={!canEdit || saving || !dirty} className="btn btn-primary">
          {saving ? '...' : '💾 Save'}
        </button>
        <button onClick={onApprove} disabled={!canEdit || saving} className="btn btn-primary">
          ✓ Approve & Render
        </button>
      </div>

      {!canEdit && (
        <div className="bg-stone-100 border border-border rounded p-3 mb-4 text-sm text-ink-muted">
          目前 state=<code className="font-mono">{job.state}</code>, 為唯讀模式。僅
          <code className="font-mono mx-1">awaiting_review</code> 可儲存 / approve。
        </div>
      )}

      {deck.sections.map((sec, sIdx) => (
        <section
          key={sec.id}
          className="bg-white border border-border rounded-md p-4 mb-4"
        >
          <div className="border-b-2 border-chalk-yellow pb-2 mb-3 flex items-center gap-2">
            <span className="font-semibold text-forest text-sm shrink-0">章 {sIdx + 1}:</span>
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
    </div>
  );
}
