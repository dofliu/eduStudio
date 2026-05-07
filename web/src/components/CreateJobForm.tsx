import { useState } from 'react';
import { api } from '../api';
import { useToast } from './Toast';
import type { SourceType } from '../types';

interface Props {
  onCreated: () => void;
}

export function CreateJobForm({ onCreated }: Props) {
  const { show } = useToast();
  const [open, setOpen] = useState(false);
  const [sourceType, setSourceType] = useState<SourceType>('repo');
  const [path, setPath] = useState('');
  const [url, setUrl] = useState('');
  const [requireReview, setRequireReview] = useState(false);
  const [mock, setMock] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const isUrlType = sourceType === 'url';

  const submit = async () => {
    setSubmitting(true);
    try {
      const source = isUrlType ? { url } : { path };
      const r = await api.createJob({
        source_type: sourceType,
        source,
        options: { mock, require_review: requireReview },
      });
      show(`已建立 job ${r.job_id}`);
      setPath('');
      setUrl('');
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
            onChange={(e) => setSourceType(e.target.value as SourceType)}
          >
            <option value="exam_pdf">exam_pdf — 考卷 PDF</option>
            <option value="slides_pdf">slides_pdf — 簡報 PDF</option>
            <option value="repo">repo — 資料夾</option>
            <option value="document">document — PDF / MD / TXT 單檔</option>
            <option value="url">url — 網頁文章</option>
          </select>
        </div>

        <div>
          <label className="field-label">{isUrlType ? 'URL' : 'Path (本機絕對路徑)'}</label>
          <input
            type="text"
            className="field-input font-mono"
            value={isUrlType ? url : path}
            onChange={(e) =>
              isUrlType ? setUrl(e.target.value) : setPath(e.target.value)
            }
            placeholder={
              isUrlType ? 'https://example.com/article' : 'D:/path/to/source'
            }
          />
        </div>
      </div>

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
        <button
          onClick={submit}
          disabled={submitting || (!isUrlType ? !path : !url)}
          className="btn btn-primary"
        >
          {submitting ? '送出中...' : '送出'}
        </button>
        <button onClick={() => setOpen(false)} className="btn btn-ghost">
          取消
        </button>
      </div>
    </div>
  );
}
