// v4 階段 2 B iter 14: 自動企劃 (Proposals) 列表頁
//
// ideate.py 跑出來的 proposals.json → UI 卡片 → 用戶按「核准」就建 job 進 review,
// 按「忽略」就 mark IGNORED 不再提案。設計見 docs/ideate-design.md。
//
// 不繞 require_review=True (P0 #4 學術誠信): approve 走跟 /upload 一樣的
// store.create + schedule_job, exam_pdf 還是會進 awaiting_review。

import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api';
import { useToast } from '../components/Toast';
import type { Proposal, SourceType } from '../types';


const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  exam_pdf: '考卷',
  slides_pdf: '簡報',
  repo: 'Repo',
  document: '文件',
  url: '網頁',
};


export default function ProposalsList() {
  const { show } = useToast();
  const navigate = useNavigate();
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.listProposals(true);
      setProposals(r.proposals);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      show(`讀 proposals 失敗: ${msg}`, 'error');
      setProposals([]);
    } finally {
      setLoading(false);
    }
  }, [show]);

  useEffect(() => { load(); }, [load]);

  const handleApprove = async (p: Proposal) => {
    setBusyId(p.id);
    try {
      const r = await api.approveProposal(p.id);
      show(`已核准, job ${r.job.job_id} 已排程`, 'info');
      // 直接跳到 JobEditor 進 review
      navigate(`/jobs/${r.job.job_id}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      show(`核准失敗: ${msg}`, 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleScan = async () => {
    if (scanning) return;
    setScanning(true);
    try {
      const r = await api.scanProposals();
      if (!r.ok) {
        show(`掃描失敗: ${r.error ?? '未知錯誤'}`, 'error');
      } else {
        show(`掃描完成: 候選 ${r.scanned} / 新提案 ${r.new}`, 'info');
        await load();    // 重抓清單看新提案
      }
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      show(`掃描失敗: ${msg}`, 'error');
    } finally {
      setScanning(false);
    }
  };

  const handleIgnore = async (p: Proposal) => {
    if (!confirm(`確定要忽略「${p.suggested_title}」?之後 ideate 不會再提這份檔。`)) {
      return;
    }
    setBusyId(p.id);
    try {
      await api.ignoreProposal(p.id);
      show('已忽略', 'info');
      // 從清單移除
      setProposals(prev => prev.filter(x => x.id !== p.id));
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      show(`忽略失敗: ${msg}`, 'error');
    } finally {
      setBusyId(null);
    }
  };

  if (loading) {
    return <div className="text-center py-10 text-ink-muted">Loading proposals…</div>;
  }

  // 共用的「掃資料夾」按鈕 — 空清單跟有資料時都用
  const scanButton = (
    <button
      onClick={handleScan}
      disabled={scanning}
      className="btn btn-primary text-sm"
      title="從 ideate_config.yaml 讀 watched_folders, 跑 Gemini Vision 提案 (可能等 10+ 分)"
    >
      {scanning ? '⏳ 掃描中… (Gemini 跑 10+ 分)' : '📂 掃資料夾產提案'}
    </button>
  );

  if (proposals.length === 0) {
    return (
      <div className="text-center py-10">
        <div className="text-ink-muted mb-4">沒有 pending 的企劃。</div>
        <div className="mb-4">{scanButton}</div>
        <div className="text-xs text-ink-muted">
          先 <code>cp ideate_config.example.yaml ideate_config.yaml</code> 設定 watched_folders,
          再按上面按鈕。或設 <code>IDEATE_AUTO_SCAN=1</code> 環境變數讓 server 自動定時跑。
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">📋 自動企劃 (待決策 {proposals.length} 件)</h1>
        <div className="flex gap-2">
          {scanButton}
          <button onClick={load} className="btn btn-ghost text-sm">↻ 重新載入</button>
        </div>
      </div>

      <ul className="space-y-3">
        {proposals.map(p => (
          <li
            key={p.id}
            className="bg-white border border-border rounded-md p-4 hover:shadow-sm"
          >
            <div className="flex items-start gap-3 mb-2">
              <span className="px-2 py-0.5 bg-stone-100 rounded text-xs text-ink-muted shrink-0">
                {SOURCE_TYPE_LABEL[p.source_type] ?? p.source_type}
              </span>
              <h2 className="text-base font-medium flex-1">{p.suggested_title}</h2>
              <span className="text-xs text-ink-muted shrink-0">
                ~{p.estimated_duration_min} 分
              </span>
            </div>

            <div className="text-xs text-ink-muted mb-2 font-mono break-all">
              {p.source_file}
            </div>

            <p className="text-sm text-ink mb-3">{p.reason}</p>

            {p.suggested_chapters.length > 0 && (
              <div className="mb-3 text-xs text-ink-muted">
                <span className="font-medium">建議章節:</span>{' '}
                {p.suggested_chapters.join(' / ')}
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => handleApprove(p)}
                disabled={busyId === p.id}
                className="btn btn-primary text-sm"
              >
                {busyId === p.id ? '處理中…' : '✓ 核准 (建 job + review)'}
              </button>
              <button
                onClick={() => handleIgnore(p)}
                disabled={busyId === p.id}
                className="btn btn-ghost text-sm"
              >
                ✗ 忽略
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
