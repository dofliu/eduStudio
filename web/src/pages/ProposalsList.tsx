// v4 階段 2 B iter 14: 自動企劃 (Proposals) 列表頁
//
// ideate.py 跑出來的 proposals.json → UI 卡片 → 用戶按「核准」就建 job 進 review,
// 按「忽略」就 mark IGNORED 不再提案。設計見 docs/ideate-design.md。
//
// 不繞 require_review=True (P0 #4 學術誠信): approve 走跟 /upload 一樣的
// store.create + schedule_job, exam_pdf 還是會進 awaiting_review。

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api';
import { useToast } from '../components/Toast';
import type { Proposal, ScanStatusResponse, SourceType } from '../types';


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
  // iter 27: ad-hoc modal 取代 yaml — 用戶填 path 直接掃
  const [scanModal, setScanModal] = useState(false);
  const [scanFolder, setScanFolder] = useState('');
  const [scanType, setScanType] = useState<'auto' | 'exam_pdf' | 'slides_pdf' | 'document'>('auto');
  const [scanWindowDays, setScanWindowDays] = useState(30);
  const [scanMaxPerFile, setScanMaxPerFile] = useState(3);
  // iter 34: async polling — modal 跑 scan 時顯示即時進度
  const [scanStatus, setScanStatus] = useState<ScanStatusResponse | null>(null);
  const pollTimerRef = useRef<number | null>(null);

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

  const openScanModal = () => {
    setScanModal(true);
  };

  // iter 34: poll scan status 直到 done/failed
  const pollScanStatus = useCallback(
    (scanId: string) => {
      // 清舊 timer (防多次按)
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
      pollTimerRef.current = window.setInterval(async () => {
        try {
          const status = await api.getScanStatus(scanId);
          setScanStatus(status);
          if (status.state === 'done' || status.state === 'failed') {
            // 停止 polling
            if (pollTimerRef.current) {
              clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
            }
            setScanning(false);
            if (status.state === 'done') {
              show(`掃描完成: 候選 ${status.scanned} / 新提案 ${status.new}`, 'info');
              setScanModal(false);
              await load();
            } else {
              show(`掃描失敗: ${status.error ?? '未知錯誤'}`, 'error');
            }
          }
        } catch (e) {
          const msg = e instanceof ApiError ? e.message : String(e);
          show(`查詢狀態失敗: ${msg}`, 'error');
          if (pollTimerRef.current) {
            clearInterval(pollTimerRef.current);
            pollTimerRef.current = null;
          }
          setScanning(false);
        }
      }, 3000); // 3 秒 poll 一次
    },
    [load, show],
  );

  // 元件卸載時清 timer (避免 memory leak / setState on unmounted)
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, []);

  const handleScan = async () => {
    if (scanning) return;
    const folder = scanFolder.trim();
    if (!folder) {
      show('請輸入資料夾路徑', 'error');
      return;
    }
    setScanning(true);
    setScanStatus(null);
    try {
      // iter 34: 走 async 路徑, 立刻拿 scan_id 後 poll status
      const r = await api.scanFolderAsync({
        folder,
        source_type: scanType,
        scan_window_days: scanWindowDays,
        max_proposals_per_file: scanMaxPerFile,
      });
      pollScanStatus(r.scan_id);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      show(`掃描失敗: ${msg}`, 'error');
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
      onClick={openScanModal}
      disabled={scanning}
      className="btn btn-primary text-sm"
      title="掃指定資料夾, 跑 Gemini Vision 自動提案 (可能等 10+ 分)"
    >
      {scanning ? '⏳ 掃描中…' : '📂 掃資料夾產提案'}
    </button>
  );

  // iter 27: ad-hoc 掃描設定 modal — 點上面按鈕跳出, 填 path 後跑
  const scanModalEl = scanModal && (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onClick={() => !scanning && setScanModal(false)}
    >
      <div
        className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold mb-3">📂 掃資料夾產提案</h2>
        <div className="space-y-3 text-sm">
          <div>
            <label className="block text-xs font-medium mb-1">
              資料夾路徑 (server 本機絕對路徑)
            </label>
            <input
              type="text"
              value={scanFolder}
              onChange={(e) => setScanFolder(e.target.value)}
              placeholder="D:/Teaching/Materials/材料力學"
              className="w-full px-3 py-1.5 border rounded text-sm font-mono"
              disabled={scanning}
              autoFocus
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium mb-1">類型判斷</label>
              <select
                value={scanType}
                onChange={(e) => setScanType(e.target.value as typeof scanType)}
                className="w-full px-2 py-1.5 border rounded text-sm"
                disabled={scanning}
              >
                <option value="auto">auto (推薦, AI 自動判)</option>
                <option value="exam_pdf">exam_pdf (考題)</option>
                <option value="slides_pdf">slides_pdf (簡報)</option>
                <option value="document">document (文件)</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">天數 (近 N 天)</label>
              <input
                type="number"
                min={1}
                max={3650}
                value={scanWindowDays}
                onChange={(e) => setScanWindowDays(Number(e.target.value) || 30)}
                className="w-full px-2 py-1.5 border rounded text-sm"
                disabled={scanning}
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">每份 PDF 最多幾個提案</label>
            <input
              type="number"
              min={1}
              max={10}
              value={scanMaxPerFile}
              onChange={(e) => setScanMaxPerFile(Number(e.target.value) || 3)}
              className="w-full px-2 py-1.5 border rounded text-sm"
              disabled={scanning}
            />
          </div>

          {/* iter 34: 掃描中即時進度 */}
          {scanning && scanStatus && (
            <div className="mt-3 p-3 bg-stone-50 border border-border rounded">
              <div className="text-xs font-medium mb-2 text-ink-muted">即時進度</div>
              <div className="grid grid-cols-3 gap-2 text-center text-sm mb-2">
                <div>
                  <div className="text-lg font-semibold">{scanStatus.scanned}</div>
                  <div className="text-xs text-ink-muted">候選</div>
                </div>
                <div>
                  <div className="text-lg font-semibold">{scanStatus.proposed}</div>
                  <div className="text-xs text-ink-muted">產出提案</div>
                </div>
                <div>
                  <div className="text-lg font-semibold">{scanStatus.new}</div>
                  <div className="text-xs text-ink-muted">新 (dedupe 後)</div>
                </div>
              </div>
              {scanStatus.message && (
                <div className="text-xs text-ink-muted font-mono truncate">
                  {scanStatus.message}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="mt-5 flex gap-2 justify-end">
          <button
            onClick={() => setScanModal(false)}
            disabled={scanning}
            className="btn btn-ghost text-sm"
          >
            取消
          </button>
          <button
            onClick={handleScan}
            disabled={scanning || !scanFolder.trim()}
            className="btn btn-primary text-sm"
          >
            {scanning ? '⏳ 掃描中… (~10 分)' : '開始掃'}
          </button>
        </div>
      </div>
    </div>
  );

  if (proposals.length === 0) {
    return (
      <>
        <div className="text-center py-10">
          <div className="text-ink-muted mb-4">沒有 pending 的企劃。</div>
          <div className="mb-4">{scanButton}</div>
          <div className="text-xs text-ink-muted">
            點上面按鈕填入要掃的資料夾, Gemini Vision 會自動判斷每份 PDF 類型並提案影片。
          </div>
        </div>
        {scanModalEl}
      </>
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
      {scanModalEl}

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
