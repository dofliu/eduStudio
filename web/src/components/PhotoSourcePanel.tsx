// Google 相簿 → 相片簡報 的多步驟流程面板。
//
// 因 Google 2025 改版, 讀取使用者相簿須走 Photos Picker API:
//   ① 檢查是否已授權 (未授權 → 提示在伺服器本機跑 tools.photos_auth)
//   ② 建 Picker session → 開新分頁讓使用者挑照片 → 輪詢是否選好
//   ③ 選好後 → 產生相片簡報 (vision 選圖+配文 → deck → 影片/PPTX)
import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useToast } from './Toast';

interface Props {
  onCreated: () => void;
}

type Status = 'checking' | 'authorized' | 'unauthorized';

export function PhotoSourcePanel({ onCreated }: Props) {
  const { show } = useToast();
  const [status, setStatus] = useState<Status>('checking');
  const [sessionId, setSessionId] = useState('');
  const [pickerUri, setPickerUri] = useState('');
  const [ready, setReady] = useState(false);
  const [polling, setPolling] = useState(false);
  const [titleHint, setTitleHint] = useState('');
  const [maxSelect, setMaxSelect] = useState<number | ''>('');
  const [requireReview, setRequireReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    api.photosStatus()
      .then((s) => setStatus(s.authorized ? 'authorized' : 'unauthorized'))
      .catch(() => setStatus('unauthorized'));
    return () => { if (pollTimer.current) clearInterval(pollTimer.current); };
  }, []);

  const startPicker = async () => {
    setBusy(true);
    try {
      const s = await api.createPhotoSession();
      setSessionId(s.session_id);
      setPickerUri(s.picker_uri);
      setReady(false);
      window.open(s.picker_uri, '_blank', 'noopener');
      // 輪詢是否已選好
      setPolling(true);
      pollTimer.current = setInterval(async () => {
        try {
          const p = await api.pollPhotoSession(s.session_id);
          if (p.media_items_set) {
            setReady(true);
            setPolling(false);
            if (pollTimer.current) clearInterval(pollTimer.current);
          }
        } catch { /* 忽略單次輪詢錯誤 */ }
      }, 3000);
    } catch (e) {
      show(`開啟相簿選取器失敗: ${e}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    setBusy(true);
    try {
      const r = await api.generatePhotos({
        session_id: sessionId,
        title_hint: titleHint || undefined,
        max_select: maxSelect === '' ? null : Number(maxSelect),
        require_review: requireReview,
      });
      show(`已建立相片簡報 job ${r.job_id}，處理中…`);
      onCreated();
    } catch (e) {
      show(`產生失敗: ${e}`, 'error');
    } finally {
      setBusy(false);
    }
  };

  if (status === 'checking') {
    return <div className="mt-3 text-sm text-ink-muted">檢查 Google 相簿授權中…</div>;
  }
  if (status === 'unauthorized') {
    return (
      <div className="mt-3 text-sm bg-paper-warm border border-paper-line rounded px-3 py-2 leading-relaxed">
        尚未授權 Google 相簿。請在<b>伺服器本機</b>執行一次：
        <div className="mt-1"><code className="text-forest-700">python -m tools.photos_auth</code></div>
        授權完成後回到這裡重新整理即可。（需先在 Google Cloud 啟用 Photos Picker API 並放好
        <code> client_secret*.json</code>。）
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-col gap-3">
      <div className="flex items-center gap-3 flex-wrap">
        <button className="btn btn-primary btn-sm" onClick={startPicker} disabled={busy}>
          {sessionId ? '重新選照片' : '① 開啟 Google 相簿選照片'}
        </button>
        {polling && <span className="text-xs text-ink-muted">已開啟選取器，選好後回來…（自動偵測中）</span>}
        {ready && <span className="text-xs text-forest-700">✅ 已選好照片</span>}
        {pickerUri && !ready && (
          <a href={pickerUri} target="_blank" rel="noopener noreferrer"
             className="text-xs text-forest-600 underline decoration-dotted">沒跳出來？點這開啟</a>
        )}
      </div>

      {ready && (
        <div className="flex flex-col gap-2 border-t border-paper-line pt-3">
          <label className="field-label">主題脈絡（可空，幫 AI 取標題/配文）</label>
          <input className="field-input" value={titleHint}
                 onChange={(e) => setTitleHint(e.target.value)}
                 placeholder="例：宜蘭三日遊 / 系上迎新" />
          <div className="flex items-center gap-4 flex-wrap text-sm">
            <label className="flex items-center gap-1.5">
              最多保留
              <input type="number" min={1} className="field-input !w-20 !py-0.5" value={maxSelect}
                     onChange={(e) => setMaxSelect(e.target.value === '' ? '' : Number(e.target.value))}
                     placeholder="全部" />
              張
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={requireReview}
                     onChange={(e) => setRequireReview(e.target.checked)} />
              產生後停下讓我編輯 caption 再渲染
            </label>
          </div>
          <button className="btn btn-primary btn-sm self-start" onClick={generate} disabled={busy}>
            ② 產生相片簡報（影片 + 可匯出 PPTX）
          </button>
          <span className="text-xs text-ink-muted">
            AI 會品質過濾（模糊/重複）並為每張配一句說明。完成後：影片在 job 頁預覽、
            按「📊 匯出 PPTX」下載簡報、或在 SlideEditor 微調文字後重渲染。
          </span>
        </div>
      )}
    </div>
  );
}
