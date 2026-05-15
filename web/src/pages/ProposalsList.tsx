// ProposalsList — UI redesign 套用後的版本
// 邏輯完全保留: 所有 state (themeByProposal / prependIntroByProposal / lengthModeByProposal /
//                          scanModal / scanFolder / scanType / scanWindowDays / scanMaxPerFile /
//                          scanStatus / pollTimerRef)、所有 handler (load / handleApprove /
//                          handleIgnore / handleScan / pollScanStatus)、polling effect 全部沿用
// 只改 return 的 JSX 與 className

import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError } from '../api';
import { useToast } from '../components/Toast';
import { Btn, Topbar, SourceBadge, Field, Input, Select, Meter, VideoThumb } from '../components/ui';
import { SOURCE_META } from '../components/ui/SourceBadge';
import type { Proposal, ScanStatusResponse, SourceType } from '../types';

// iter 40: theme 只對走 PptxStyleRenderer 的 source 適用
const THEME_APPLICABLE: SourceType[] = ['repo', 'document', 'url'];
type ThemeName =
  | 'forest' | 'navy' | 'frieren' | 'naruto' | 'journal'
  | 'dof-editorial' | 'dof-podium' | 'dof-notebook' | 'dof-shinobi' | 'dof-elven'
  | 'dof-zine' | 'dof-arcade' | 'dof-risograph' | 'dof-supergraphic' | 'dof-brutalist';
const THEME_OPTIONS: { value: ThemeName; label: string; sub: string }[] = [
  { value: 'forest',           label: 'Forest',     sub: '深綠 · 程式教學' },
  { value: 'navy',             label: 'Navy',       sub: '深藍 · AI / 工程' },
  { value: 'journal',          label: 'Journal',    sub: '米白 · 期刊' },
  { value: 'frieren',          label: 'Frieren',    sub: '藏青 · 芙莉蓮' },
  { value: 'naruto',           label: 'Naruto',     sub: '焦糖 · 火影' },
  { value: 'dof-editorial',    label: 'Editorial',  sub: '雜誌 · 演講' },
  { value: 'dof-podium',       label: 'Podium',     sub: 'TED · 講壇' },
  { value: 'dof-notebook',     label: 'Notebook',   sub: '札記 · 讀書會' },
  { value: 'dof-shinobi',      label: 'Shinobi',    sub: '忍者 · 熱血' },
  { value: 'dof-elven',        label: 'Elven',      sub: '幻境 · 哲學' },
  { value: 'dof-zine',         label: 'Zine',       sub: '海報 · 宣言' },
  { value: 'dof-arcade',       label: 'Arcade',     sub: '霓虹 · Demo' },
  { value: 'dof-risograph',    label: 'Risograph',  sub: '油墨 · 工作坊' },
  { value: 'dof-supergraphic', label: 'Super-G',    sub: '色塊 · 品牌' },
  { value: 'dof-brutalist',    label: 'Brutalist',  sub: '野獸派 · 批判' },
];

export default function ProposalsList() {
  const { show } = useToast();
  const navigate = useNavigate();
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [openCfg, setOpenCfg] = useState<string | null>(null);
  // 各卡片獨立狀態 (沿用原 code 的命名)
  const [themeByProposal, setThemeByProposal] = useState<Record<string, ThemeName>>({});
  const [prependIntroByProposal, setPrependIntroByProposal] = useState<Record<string, boolean>>({});
  const [lengthModeByProposal, setLengthModeByProposal] = useState<Record<string, 'quick' | 'lecture'>>({});
  // iter 56: AI 生圖 opt-in per-card (Gemini Flash Image, 會計費)
  const [aiGenByProposal, setAiGenByProposal] = useState<Record<string, boolean>>({});
  // scan modal state
  const [scanModal, setScanModal] = useState(false);
  const [scanFolder, setScanFolder] = useState('');
  const [scanType, setScanType] = useState<'auto' | 'exam_pdf' | 'slides_pdf' | 'document'>('auto');
  const [scanWindowDays, setScanWindowDays] = useState(30);
  const [scanMaxPerFile, setScanMaxPerFile] = useState(3);
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
      const themeApplicable = THEME_APPLICABLE.includes(p.source_type);
      const theme = themeApplicable ? (themeByProposal[p.id] ?? 'forest') : undefined;
      const prependIntro = prependIntroByProposal[p.id] ?? false;
      const lengthMode = themeApplicable ? lengthModeByProposal[p.id] : undefined;
      const aiGen = themeApplicable ? (aiGenByProposal[p.id] ?? false) : false;
      const body: {
        theme?: string;
        prepend_intro?: boolean;
        length_mode?: string;
        ai_generate_diagrams?: boolean;
      } = {};
      if (theme) body.theme = theme;
      if (prependIntro) body.prepend_intro = true;
      if (lengthMode && lengthMode !== 'quick') body.length_mode = lengthMode;
      if (aiGen) body.ai_generate_diagrams = true;
      const r = await api.approveProposal(p.id, Object.keys(body).length > 0 ? body : undefined);
      show(`已核准, job ${r.job.job_id} 已排程`, 'info');
      navigate(`/jobs/${r.job.job_id}`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      show(`核准失敗: ${msg}`, 'error');
    } finally {
      setBusyId(null);
    }
  };

  const pollScanStatus = useCallback((scanId: string) => {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    pollTimerRef.current = window.setInterval(async () => {
      try {
        const status = await api.getScanStatus(scanId);
        setScanStatus(status);
        if (status.state === 'done' || status.state === 'failed') {
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
    }, 3000);
  }, [load, show]);

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
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
    if (!confirm(`確定要忽略「${p.suggested_title}」?之後 ideate 不會再提這份檔。`)) return;
    setBusyId(p.id);
    try {
      await api.ignoreProposal(p.id);
      show('已忽略', 'info');
      setProposals(prev => prev.filter(x => x.id !== p.id));
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      show(`忽略失敗: ${msg}`, 'error');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <Topbar
        eyebrow="02 · Proposals"
        title="自動企劃"
        subtitle="Gemini Vision 掃過你資料夾裡的新檔案,挑出值得拍的題材排好排程。你的工作只剩下 yes / no。"
        right={
          <>
            <Btn kind="ghost" size="md" onClick={load}>↻ 重新載入</Btn>
            <Btn kind="secondary" size="md" onClick={() => setScanModal(true)}>⌕ 掃資料夾</Btn>
          </>
        }
      />

      <div className="flex-1 overflow-y-auto scrollbar-thin">
        <div className="px-10 py-7 max-w-[1200px]">
          <div className="grid grid-cols-3 gap-3 mb-7">
            <ProposalStat n={proposals.length} l="待決策" tone="forest" />
            <ProposalStat n="—" l="近 7 天新檔" />
            <ProposalStat n="—" l="本月已核准" />
          </div>

          <div className="flex items-baseline justify-between mb-4">
            <h2 className="font-display text-[26px] text-forest-700">
              待決策 · <span className="text-ink-muted">{proposals.length} 件</span>
            </h2>
          </div>

          {loading ? (
            <div className="text-center py-10 text-ink-muted">Loading proposals…</div>
          ) : proposals.length === 0 ? (
            <div className="text-center py-16 border border-dashed border-paper-edge rounded-sm">
              <div className="text-ink-muted mb-4">沒有 pending 的企劃。</div>
              <Btn kind="secondary" size="md" onClick={() => setScanModal(true)}>⌕ 掃資料夾產提案</Btn>
              <div className="text-[11px] text-ink-faint mt-3">Gemini Vision 會自動判斷每份 PDF 類型並提案影片</div>
            </div>
          ) : (
            <div className="space-y-3">
              {proposals.map(p => (
                <ProposalCard
                  key={p.id}
                  p={p}
                  open={openCfg === p.id}
                  busy={busyId === p.id}
                  themeValue={themeByProposal[p.id] ?? 'forest'}
                  lengthValue={lengthModeByProposal[p.id] ?? 'quick'}
                  introValue={prependIntroByProposal[p.id] ?? false}
                  aiGenValue={aiGenByProposal[p.id] ?? false}
                  onToggle={() => setOpenCfg(openCfg === p.id ? null : p.id)}
                  onApprove={() => handleApprove(p)}
                  onIgnore={() => handleIgnore(p)}
                  onThemeChange={(v) => setThemeByProposal(prev => ({ ...prev, [p.id]: v }))}
                  onLengthChange={(v) => setLengthModeByProposal(prev => ({ ...prev, [p.id]: v }))}
                  onIntroChange={(v) => setPrependIntroByProposal(prev => ({ ...prev, [p.id]: v }))}
                  onAiGenChange={(v) => setAiGenByProposal(prev => ({ ...prev, [p.id]: v }))}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {scanModal && (
        <ScanModal
          folder={scanFolder} onFolderChange={setScanFolder}
          type={scanType} onTypeChange={setScanType}
          windowDays={scanWindowDays} onWindowDaysChange={setScanWindowDays}
          maxPerFile={scanMaxPerFile} onMaxPerFileChange={setScanMaxPerFile}
          scanning={scanning}
          status={scanStatus}
          onClose={() => !scanning && setScanModal(false)}
          onScan={handleScan}
        />
      )}
    </div>
  );
}

// ── Sub-components (all presentational) ────────────────────────────────────

function ProposalStat({ n, l, tone }: { n: number | string; l: string; tone?: 'forest' }) {
  return (
    <div className={'border rounded-sm px-4 py-3 ' + (tone === 'forest' ? 'bg-forest-600 text-chalk-yellow border-forest-700' : 'bg-paper-card border-paper-line')}>
      <div className={'font-display text-[40px] leading-none ' + (tone === 'forest' ? 'text-chalk-yellow' : 'text-forest-700')}>{n}</div>
      <div className={'mt-1 text-[11px] font-mono uppercase tracking-[0.16em] ' + (tone === 'forest' ? 'text-chalk-white/70' : 'text-ink-muted')}>{l}</div>
    </div>
  );
}

interface CardProps {
  p: Proposal;
  open: boolean;
  busy: boolean;
  themeValue: ThemeName;
  lengthValue: 'quick' | 'lecture';
  introValue: boolean;
  aiGenValue: boolean;       // iter 56: AI 生圖 opt-in
  onToggle: () => void;
  onApprove: () => void;
  onIgnore: () => void;
  onThemeChange: (v: ThemeName) => void;
  onLengthChange: (v: 'quick' | 'lecture') => void;
  onIntroChange: (v: boolean) => void;
  onAiGenChange: (v: boolean) => void;
}

function ProposalCard({
  p, open, busy, themeValue, lengthValue, introValue, aiGenValue,
  onToggle, onApprove, onIgnore,
  onThemeChange, onLengthChange, onIntroChange, onAiGenChange,
}: CardProps) {
  const themeApplicable = THEME_APPLICABLE.includes(p.source_type);

  return (
    <article className={'border rounded-sm bg-paper-card transition-all ' + (open ? 'border-forest-500 shadow-lift' : 'border-paper-line shadow-card')}>
      <div className="px-5 py-4 flex items-start gap-5">
        <div className="w-[140px] shrink-0">
          <VideoThumb title={p.suggested_title} theme={themeApplicable ? themeValue : null} duration={`~${p.estimated_duration_min} 分`} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5 flex-wrap">
            <SourceBadge type={p.source_type} />
            <span className="text-[11px] text-ink-muted">
              預估 <span className="font-mono num text-forest-700 font-medium">{p.estimated_duration_min}</span> 分
            </span>
            <span className="ml-auto font-mono text-[10px] text-ink-faint">{p.id}</span>
          </div>
          <h3 className="font-display text-[22px] leading-[1.15] text-forest-700">{p.suggested_title}</h3>
          <div className="font-mono text-[11px] text-ink-muted mt-1 break-all">{p.source_file}</div>
          <p className="text-[13px] text-ink mt-2.5 leading-relaxed max-w-2xl">{p.reason}</p>

          {p.suggested_chapters.length > 0 && (
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-muted shrink-0">建議章節</span>
              {p.suggested_chapters.map((c, i) => (
                <span key={i} className="text-[11.5px] text-ink-muted border border-paper-edge bg-paper rounded-sm px-2 py-0.5">
                  <span className="font-mono num text-ink-faint mr-1.5">{String(i + 1).padStart(2, '0')}</span>{c}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="shrink-0 flex flex-col gap-2 w-[140px]">
          <Btn kind="primary" size="md" className="!w-full !justify-center" onClick={onApprove} disabled={busy}>
            {busy ? '處理中…' : '✓ 核准'}
          </Btn>
          <Btn kind="ghost" size="md" className="!w-full !justify-center" onClick={onToggle} disabled={busy}>
            {open ? '收合 ↑' : '⚙ 進階'}
          </Btn>
          <Btn kind="quiet" size="md" className="!w-full !justify-center" onClick={onIgnore} disabled={busy}>✗ 忽略</Btn>
        </div>
      </div>

      {open && (
        <div className="px-5 pb-5 pt-3 border-t border-paper-line bg-paper">
          <div className="grid grid-cols-3 gap-5">
            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-muted mb-2">
                pptx 主題 {!themeApplicable && <span className="text-ink-faint">(此類型不適用)</span>}
              </div>
              <div className="grid grid-cols-2 gap-1.5 max-h-[260px] overflow-y-auto scrollbar-thin pr-1">
                {THEME_OPTIONS.map(o => {
                  const sel = themeValue === o.value && themeApplicable;
                  return (
                    <button
                      key={o.value}
                      onClick={() => themeApplicable && onThemeChange(o.value)}
                      disabled={!themeApplicable || busy}
                      className={
                        'text-left p-2 rounded-sm border text-[11.5px] transition-colors ' +
                        (sel
                          ? 'border-forest-600 bg-forest-600 text-chalk-white'
                          : 'border-paper-edge bg-paper-card hover:bg-paper-warm disabled:opacity-40')
                      }
                    >
                      <div className={sel ? 'font-medium' : 'font-medium text-ink'}>{o.label}</div>
                      <div className={'text-[10px] mt-0.5 ' + (sel ? 'text-chalk-white/70' : 'text-ink-muted')}>{o.sub}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-muted mb-2">長度模式</div>
              {themeApplicable ? (
                <div className="space-y-1.5">
                  {[
                    ['quick',   '⚡ 快速', '8~15 分鐘 · 摘要重點'],
                    ['lecture', '📚 授課', '60~180 分鐘 · 完整講解'],
                  ].map(([v, l, d]) => {
                    const sel = lengthValue === v;
                    return (
                      <button
                        key={v}
                        onClick={() => onLengthChange(v as 'quick' | 'lecture')}
                        disabled={busy}
                        className={
                          'w-full text-left p-2.5 rounded-sm border transition-colors ' +
                          (sel
                            ? 'border-forest-600 bg-forest-600 text-chalk-white'
                            : 'border-paper-edge bg-paper-card hover:bg-paper-warm')
                        }
                      >
                        <div className={'text-[12.5px] font-medium ' + (sel ? '' : 'text-ink')}>{l}</div>
                        <div className={'text-[11px] mt-0.5 ' + (sel ? 'text-chalk-white/70' : 'text-ink-muted')}>{d}</div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <div className="text-[11.5px] text-ink-muted">考卷 / 簡報類型由內容決定長度,不適用此選項。</div>
              )}

              <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-muted mb-2 mt-5">附加</div>
              <label className="flex items-center gap-2 p-2.5 rounded-sm border border-paper-edge bg-paper-card cursor-pointer hover:bg-paper-warm mb-2">
                <input
                  type="checkbox"
                  checked={introValue}
                  onChange={(e) => onIntroChange(e.target.checked)}
                  disabled={busy}
                  className="w-3.5 h-3.5 accent-forest-600"
                />
                <div className="flex-1">
                  <div className="text-[12.5px] text-ink">串個人 intro 開場</div>
                  <div className="text-[11px] text-ink-muted">~8 秒接到主影片前</div>
                </div>
              </label>
              {/* iter 56: AI 生圖 (Gemini Flash Image) — 只對適用 source_type 顯示 */}
              {themeApplicable && (
                <label className="flex items-center gap-2 p-2.5 rounded-sm border border-paper-edge bg-paper-card cursor-pointer hover:bg-paper-warm">
                  <input
                    type="checkbox"
                    checked={aiGenValue}
                    onChange={(e) => onAiGenChange(e.target.checked)}
                    disabled={busy}
                    className="w-3.5 h-3.5 accent-forest-600"
                  />
                  <div className="flex-1">
                    <div className="text-[12.5px] text-ink">🎨 AI 生架構圖</div>
                    <div className="text-[11px] text-ink-muted">每章 1 張, Gemini Flash Image, 會計費</div>
                  </div>
                </label>
              )}
            </div>

            <div>
              <div className="text-[10px] font-mono uppercase tracking-[0.16em] text-ink-muted mb-2">最終配置</div>
              <div className="rounded-sm border border-paper-edge bg-paper-card p-3 text-[12px] space-y-1.5">
                <Row k="來源" v={SOURCE_META[p.source_type].label} />
                <Row k="主題" v={themeApplicable ? themeValue : '— (固定底圖)'} />
                <Row k="長度" v={themeApplicable ? (lengthValue === 'quick' ? '快速' : '授課') : '—'} />
                <Row k="Intro" v={introValue ? '串接' : '不串'} />
                {themeApplicable && (
                  <Row k="AI 生圖" v={aiGenValue ? '啟用' : '關閉'} />
                )}
                <div className="flex justify-between border-t border-paper-line pt-1.5 mt-1.5">
                  <span className="text-ink-muted">預估</span>
                  <span className="font-mono num font-medium text-forest-700">{p.estimated_duration_min} 分</span>
                </div>
              </div>
              <Btn kind="primary" size="md" className="!w-full !justify-center mt-3" onClick={onApprove} disabled={busy}>
                {busy ? '處理中…' : '✓ 用此配置核准'}
              </Btn>
              <div className="text-[10.5px] text-ink-muted mt-2 text-center">核准後直接跳到 Edit 進 review</div>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2">
      <span className="text-ink-muted shrink-0">{k}</span>
      <span className="font-medium text-right truncate">{v}</span>
    </div>
  );
}

// ── Scan modal ─────────────────────────────────────────────────────────────

interface ScanModalProps {
  folder: string;
  onFolderChange: (v: string) => void;
  type: 'auto' | 'exam_pdf' | 'slides_pdf' | 'document';
  onTypeChange: (v: 'auto' | 'exam_pdf' | 'slides_pdf' | 'document') => void;
  windowDays: number;
  onWindowDaysChange: (v: number) => void;
  maxPerFile: number;
  onMaxPerFileChange: (v: number) => void;
  scanning: boolean;
  status: ScanStatusResponse | null;
  onClose: () => void;
  onScan: () => void;
}

function ScanModal(props: ScanModalProps) {
  const {
    folder, onFolderChange, type, onTypeChange,
    windowDays, onWindowDaysChange, maxPerFile, onMaxPerFileChange,
    scanning, status, onClose, onScan,
  } = props;
  return (
    <div className="fixed inset-0 z-40 bg-forest-900/40 backdrop-blur-[2px] flex items-center justify-center p-6" onClick={onClose}>
      <div className="bg-paper-card w-full max-w-xl border border-paper-line rounded-sm shadow-lift overflow-hidden" onClick={(e) => e.stopPropagation()}>
        <div className="px-7 pt-7 pb-5 border-b border-paper-line">
          <div className="text-[11px] font-mono uppercase tracking-[0.2em] text-ink-muted mb-2">scan · gemini vision</div>
          <h3 className="font-display text-[26px] text-forest-700 leading-tight">掃資料夾產提案</h3>
          <p className="text-[13px] text-ink-muted mt-1">指一個本機資料夾,AI 會逐檔判斷類型並建議拍攝題材,大約 5~10 分鐘。</p>
        </div>

        <div className="p-7 space-y-5">
          <Field label="資料夾路徑" hint="server 本機絕對路徑">
            <Input
              value={folder}
              onChange={(e) => onFolderChange(e.target.value)}
              placeholder="D:/Teaching/Materials/材料力學"
              className="font-mono"
              disabled={scanning}
              autoFocus
            />
          </Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="類型判斷">
              <Select value={type} onChange={(e) => onTypeChange(e.target.value as ScanModalProps['type'])} disabled={scanning}>
                <option value="auto">auto · AI 自動判 (推薦)</option>
                <option value="exam_pdf">exam_pdf · 考題</option>
                <option value="slides_pdf">slides_pdf · 簡報</option>
                <option value="document">document · 文件</option>
              </Select>
            </Field>
            <Field label="掃描天數">
              <Input
                type="number"
                value={windowDays}
                onChange={(e) => onWindowDaysChange(Number(e.target.value) || 30)}
                className="font-mono"
                disabled={scanning}
              />
            </Field>
          </div>
          <Field label="每份 PDF 最多幾個提案">
            <Input
              type="number"
              value={maxPerFile}
              onChange={(e) => onMaxPerFileChange(Number(e.target.value) || 3)}
              className="font-mono"
              disabled={scanning}
            />
          </Field>

          {scanning && status && (
            <div className="rounded-sm border border-paper-line bg-paper p-4">
              <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-ink-muted mb-3">即時進度</div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                  <div className="font-display text-[26px] text-forest-700 num">{status.scanned}</div>
                  <div className="text-[10px] text-ink-muted font-mono uppercase tracking-[0.16em]">候選</div>
                </div>
                <div>
                  <div className="font-display text-[26px] text-forest-700 num">{status.proposed}</div>
                  <div className="text-[10px] text-ink-muted font-mono uppercase tracking-[0.16em]">提案</div>
                </div>
                <div>
                  <div className="font-display text-[26px] text-forest-700 num">{status.new}</div>
                  <div className="text-[10px] text-ink-muted font-mono uppercase tracking-[0.16em]">新增</div>
                </div>
              </div>
              {status.message && (
                <div className="mt-3 font-mono text-[11px] text-ink-muted truncate">→ {status.message}</div>
              )}
              <div className="mt-2"><Meter value={0.5} /></div>
            </div>
          )}
        </div>

        <div className="px-7 py-5 border-t border-paper-line bg-paper flex items-center justify-end gap-2">
          <Btn kind="ghost" size="md" onClick={onClose} disabled={scanning}>取消</Btn>
          <Btn kind="primary" size="md" onClick={onScan} disabled={scanning || !folder.trim()}>
            {scanning ? '⏱ 掃描中…' : '⌕ 開始掃'}
          </Btn>
        </div>
      </div>
    </div>
  );
}
