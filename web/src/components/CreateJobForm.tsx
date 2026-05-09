// PR-3k: CreateJobForm 加入上傳模式
//
// Source-type 與輸入方式的對應:
//   exam_pdf / slides_pdf / document  → file upload (預設) 或 path
//   repo                              → 只能 path (資料夾)
//   url                               → 只能 url
//
// upload 模式呼叫 POST /upload (multipart), path/url 模式呼叫 POST /jobs (JSON)。
// 建 job 後 onCreated() 觸發 JobsIndex 重新 poll。

import { useState } from 'react';
import { api } from '../api';
import { useToast } from './Toast';
import type { SourceType } from '../types';

interface Props {
  onCreated: () => void;
}

const FILE_UPLOADABLE: SourceType[] = ['exam_pdf', 'slides_pdf', 'document'];
const PATH_ONLY: SourceType[] = ['repo'];
const URL_ONLY: SourceType[] = ['url'];

type InputMode = 'upload' | 'path' | 'url';

function defaultModeFor(s: SourceType): InputMode {
  if (URL_ONLY.includes(s)) return 'url';
  if (PATH_ONLY.includes(s)) return 'path';
  return 'upload';   // exam / slides / document 預設拖檔, 不必手動填路徑
}

export function CreateJobForm({ onCreated }: Props) {
  const { show } = useToast();
  const [open, setOpen] = useState(false);
  const [sourceType, setSourceType] = useState<SourceType>('slides_pdf');
  const [inputMode, setInputMode] = useState<InputMode>('upload');
  const [path, setPath] = useState('');
  const [url, setUrl] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [requireReview, setRequireReview] = useState(false);
  const [mock, setMock] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // source_type 改變時自動切到合適的 input mode
  const onSourceTypeChange = (next: SourceType) => {
    setSourceType(next);
    setInputMode(defaultModeFor(next));
    setFile(null);
    setPath('');
    setUrl('');
  };

  const supportsUpload = FILE_UPLOADABLE.includes(sourceType);
  const supportsPath = !URL_ONLY.includes(sourceType);

  const submit = async () => {
    setSubmitting(true);
    try {
      if (inputMode === 'upload') {
        if (!file) {
          show('請選檔', 'error');
          return;
        }
        const r = await api.uploadFile(file, sourceType, {
          mock,
          require_review: requireReview,
        });
        show(`已上傳 ${file.name} 並建 job ${r.job_id}`);
      } else {
        const source = inputMode === 'url' ? { url } : { path };
        const r = await api.createJob({
          source_type: sourceType,
          source,
          options: { mock, require_review: requireReview },
        });
        show(`已建立 job ${r.job_id}`);
      }
      // reset
      setPath('');
      setUrl('');
      setFile(null);
      setOpen(false);
      onCreated();
    } catch (e) {
      show(`建立失敗: ${e}`, 'error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)} className="btn btn-primary mb-4">
        + 新增 Job
      </button>
    );
  }

  // submit button 是否能按
  const canSubmit =
    !submitting &&
    ((inputMode === 'upload' && file) ||
      (inputMode === 'path' && path) ||
      (inputMode === 'url' && url));

  return (
    <div className="bg-white border border-border rounded-md p-4 mb-4">
      <div className="flex items-center mb-3">
        <h3 className="font-semibold text-forest">新增 Job</h3>
        <button
          onClick={() => setOpen(false)}
          className="ml-auto btn btn-ghost"
          aria-label="close"
        >
          ✕
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="field-label">Source type</label>
          <select
            className="field-input"
            value={sourceType}
            onChange={(e) => onSourceTypeChange(e.target.value as SourceType)}
          >
            <option value="exam_pdf">exam_pdf — 考卷 PDF</option>
            <option value="slides_pdf">slides_pdf — 簡報 PDF</option>
            <option value="repo">repo — 資料夾</option>
            <option value="document">document — PDF / MD / TXT 單檔</option>
            <option value="url">url — 網頁文章</option>
          </select>
        </div>

        <div>
          <label className="field-label">輸入方式</label>
          <div className="flex gap-3 items-center text-sm pt-2">
            {supportsUpload && (
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="inputMode"
                  checked={inputMode === 'upload'}
                  onChange={() => setInputMode('upload')}
                />
                上傳檔案
              </label>
            )}
            {supportsPath && (
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="inputMode"
                  checked={inputMode === 'path'}
                  onChange={() => setInputMode('path')}
                />
                Server 端路徑
              </label>
            )}
            {URL_ONLY.includes(sourceType) && (
              <span className="text-ink-muted">URL 字串</span>
            )}
          </div>
        </div>
      </div>

      {/* 輸入區依 mode 切換 */}
      {inputMode === 'upload' && (
        <div className="mt-3">
          <label className="field-label">選擇檔案</label>
          <input
            type="file"
            className="field-input"
            accept=".pdf,.md,.txt"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          {file && (
            <div className="text-xs text-ink-muted mt-1">
              {file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB
            </div>
          )}
        </div>
      )}

      {inputMode === 'path' && (
        <div className="mt-3">
          <label className="field-label">本機絕對路徑</label>
          <input
            type="text"
            className="field-input font-mono"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="D:/path/to/source"
          />
        </div>
      )}

      {inputMode === 'url' && (
        <div className="mt-3">
          <label className="field-label">URL</label>
          <input
            type="text"
            className="field-input font-mono"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
          />
        </div>
      )}

      <div className="flex items-center gap-4 mt-3 text-sm">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={requireReview}
            onChange={(e) => setRequireReview(e.target.checked)}
          />
          停在 awaiting_review (人工確認後再渲染)
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={mock}
            onChange={(e) => setMock(e.target.checked)}
          />
          mock (不打 Gemini)
        </label>
      </div>

      <div className="mt-4 flex gap-2">
        <button onClick={submit} disabled={!canSubmit} className="btn btn-primary">
          {submitting ? '送出中…' : '送出'}
        </button>
        <button onClick={() => setOpen(false)} className="btn btn-ghost">
          取消
        </button>
      </div>
    </div>
  );
}
