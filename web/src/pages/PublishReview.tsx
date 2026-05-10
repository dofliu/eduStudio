// PR-3f: YouTube 上傳審查頁
//
// 流程:
//  1. mount 時 GET youtube_meta 拿預填 + GET youtube_status 看目前狀態
//  2. user 編輯 form, 按上傳 -> POST publish 觸發背景上傳
//  3. UPLOADING 期間 2 秒 poll 一次 youtube_status, 到 DONE / FAILED 停
//
// 注意: video player 走 /jobs/<id>/artifacts/<name> 端點 (FastAPI FileResponse),
// 跨網域 / chunked 都自動處理。

import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { api } from '../api';
import { useToast } from '../components/Toast';
import type { YoutubeUpload } from '../types';

const POLL_INTERVAL_MS = 2000;

export default function PublishReview() {
  const { jobId, artifactName } = useParams<{
    jobId: string;
    artifactName: string;
  }>();
  const navigate = useNavigate();
  const { show } = useToast();

  // form state — 跟 server YoutubeUpload schema 對齊
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [tagsRaw, setTagsRaw] = useState(''); // 用逗號分隔的字串, submit 前再 split
  const [privacy, setPrivacy] = useState('unlisted');
  const [category, setCategory] = useState('27');

  const [status, setStatus] = useState<YoutubeUpload | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  // 同步雙擊防呆: setSubmitting 是 async, 雙擊兩個 onSubmit closure 可能都看到
  // submitting=false 而各自送一次 publish (server 端會 409, 但 UX 看到上傳成功 + 409 交錯)
  const submittingRef = useRef(false);

  const reload = useCallback(async () => {
    if (!jobId || !artifactName) return;
    try {
      const s = await api.youtubeStatus(jobId, artifactName);
      setStatus(s);
      // 只在 form 還沒被 user 動過 (loading=true) 時用 server 值預填
      if (loading) {
        if (s.state !== 'pending' || s.title) {
          // 已上傳過 / 上次填過, 用既有值
          setTitle(s.title);
          setDescription(s.description);
          setTagsRaw(s.tags.join(', '));
          setPrivacy(s.privacy);
          setCategory(s.category);
        } else {
          // 純新, 拿 auto_youtube_meta 預填
          const meta = await api.getYoutubeMeta(jobId, artifactName);
          setTitle(meta.title);
          setDescription(meta.description);
          setTagsRaw(meta.tags.join(', '));
          setPrivacy(meta.privacy);
          setCategory(meta.category);
        }
        setLoading(false);
      }
    } catch (e) {
      show(`載入失敗: ${e}`, 'error');
      setLoading(false);
    }
  }, [jobId, artifactName, loading, show]);

  useEffect(() => {
    reload();
  }, [reload]);

  // 只有 UPLOADING 才需要持續輪詢, 其他狀態靜態顯示就夠
  useEffect(() => {
    if (status?.state !== 'uploading') return;
    const t = setInterval(() => {
      if (!jobId || !artifactName) return;
      api.youtubeStatus(jobId, artifactName).then(setStatus).catch(() => {});
    }, POLL_INTERVAL_MS);
    return () => clearInterval(t);
  }, [status?.state, jobId, artifactName]);

  const onSubmit = async () => {
    if (submittingRef.current) return;     // 同步擋雙擊
    if (!jobId || !artifactName) return;
    if (!title.trim()) {
      show('標題不能空白', 'error');
      return;
    }
    if (!confirm('開始上傳到 YouTube? 預設 unlisted, 確認無誤再切 public。')) return;
    submittingRef.current = true;
    setSubmitting(true);
    try {
      const tags = tagsRaw
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
      const next = await api.publish(jobId, artifactName, {
        title,
        description,
        tags,
        privacy,
        category,
      });
      setStatus(next);
      show('上傳已開始, 輪詢進度中...');
    } catch (e) {
      show(`上傳失敗: ${e}`, 'error');
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  if (!jobId || !artifactName) {
    return (
      <div className="text-center py-10 text-ink-muted">缺少 jobId / artifactName</div>
    );
  }

  const videoUrl = api.artifactUrl(jobId, artifactName);
  const isDone = status?.state === 'done';
  const isUploading = status?.state === 'uploading';
  const isFailed = status?.state === 'failed';
  const canEdit = !isDone && !isUploading;

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <Link to={`/jobs/${jobId}`} className="text-forest hover:underline text-sm">
          ← Back to Job
        </Link>
        <span className="text-ink-muted text-sm">·</span>
        <Link to="/" className="text-forest hover:underline text-sm">
          Jobs Index
        </Link>
      </div>

      <h1 className="text-xl font-semibold text-forest mb-1">📺 上傳到 YouTube</h1>
      <div className="text-sm text-ink-muted mb-4">
        Job <code className="font-mono">{jobId}</code> · Artifact{' '}
        <code className="font-mono">{artifactName}</code>
      </div>

      {/* video preview */}
      <div className="bg-black rounded-md mb-4 overflow-hidden">
        <video
          controls
          src={videoUrl}
          className="w-full aspect-video"
          preload="metadata"
        >
          您的瀏覽器不支援 video 標籤
        </video>
      </div>

      {loading ? (
        <div className="text-center py-10 text-ink-muted">Loading metadata…</div>
      ) : (
        <div className="bg-white border border-border rounded-md p-5">
          {/* state banner */}
          {isDone && status && (
            <div className="bg-green-50 border border-green-300 rounded p-3 mb-4">
              <div className="font-semibold text-green-800">✅ 已上傳成功</div>
              <div className="text-sm mt-1">
                <a
                  href={status.url || '#'}
                  target="_blank"
                  rel="noreferrer"
                  className="text-forest underline break-all"
                >
                  {status.url}
                </a>
              </div>
              <div className="text-xs text-ink-muted mt-1">
                video_id: <code className="font-mono">{status.video_id}</code>
                {status.caption_id && (
                  <span className="ml-2">
                    · caption_id: <code className="font-mono">{status.caption_id}</code>
                  </span>
                )}
                {status.caption_error && (
                  <span className="ml-2 text-orange-700">
                    ⚠ 字幕失敗: {status.caption_error}
                  </span>
                )}
              </div>
            </div>
          )}
          {isUploading && status && (
            <div className="bg-blue-50 border border-blue-300 rounded p-3 mb-4">
              <div className="font-semibold text-blue-800">⏳ 上傳中…</div>
              <div className="w-full bg-stone-200 rounded h-2 mt-2 overflow-hidden">
                <div
                  className="h-full bg-blue-500 transition-all"
                  style={{ width: `${status.progress_percent}%` }}
                />
              </div>
              <div className="text-xs text-ink-muted mt-1">
                {status.progress_percent}% · 大檔可能要數分鐘, 不要關閉頁面也 OK,
                背景仍會跑。
              </div>
            </div>
          )}
          {isFailed && status && (
            <div className="bg-red-50 border border-red-300 rounded p-3 mb-4">
              <div className="font-semibold text-red-800">❌ 上傳失敗</div>
              <div className="text-sm mt-1 break-all">{status.error}</div>
              <div className="text-xs text-ink-muted mt-2">
                ※ 若是 OAuth 未授權 (token 不存在), 請在本機 terminal 跑一次:
                <pre className="mt-1 p-2 bg-stone-100 rounded text-xs whitespace-pre-wrap">
                  {'python publish.py --video <任一已渲染 mp4> --title 測試 --privacy private'}
                </pre>
                完成後重整本頁再次按上傳。
              </div>
            </div>
          )}

          {/* form */}
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-forest block mb-1">
                標題 <span className="text-ink-muted text-xs">(YouTube 上限 100 字元)</span>
              </label>
              <input
                type="text"
                className="field-input w-full"
                value={title}
                disabled={!canEdit}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={100}
              />
              <div className="text-xs text-ink-muted text-right mt-1">
                {title.length} / 100
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-forest block mb-1">
                說明{' '}
                <span className="text-ink-muted text-xs">
                  (預設含章節時間軸, 上限 5000 字元)
                </span>
              </label>
              <textarea
                className="field-input w-full font-mono text-sm"
                rows={12}
                value={description}
                disabled={!canEdit}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={5000}
              />
              <div className="text-xs text-ink-muted text-right mt-1">
                {description.length} / 5000
              </div>
            </div>

            <div>
              <label className="text-sm font-medium text-forest block mb-1">
                標籤 <span className="text-ink-muted text-xs">(逗號分隔)</span>
              </label>
              <input
                type="text"
                className="field-input w-full"
                value={tagsRaw}
                disabled={!canEdit}
                onChange={(e) => setTagsRaw(e.target.value)}
                placeholder="考卷解析, 教學影片, Dof 老師"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-forest block mb-1">隱私</label>
                <select
                  className="field-input w-full"
                  value={privacy}
                  disabled={!canEdit}
                  onChange={(e) => setPrivacy(e.target.value)}
                >
                  <option value="private">private (僅自己)</option>
                  <option value="unlisted">unlisted (有連結就能看, 預設)</option>
                  <option value="public">public (公開)</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-forest block mb-1">類別</label>
                <select
                  className="field-input w-full"
                  value={category}
                  disabled={!canEdit}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option value="27">27 - Education</option>
                  <option value="28">28 - Science & Tech</option>
                  <option value="22">22 - People & Blogs</option>
                </select>
              </div>
            </div>
          </div>

          {/* actions */}
          {canEdit && (
            <div className="flex gap-2 mt-5 pt-4 border-t border-border">
              <button
                onClick={onSubmit}
                disabled={submitting || isUploading || !title.trim()}
                className="btn btn-primary"
              >
                {submitting ? '提交中…' : '⬆ 上傳到 YouTube'}
              </button>
              <button
                onClick={() => navigate(`/jobs/${jobId}`)}
                disabled={submitting}
                className="btn btn-ghost"
              >
                取消
              </button>
            </div>
          )}
          {isDone && (
            <div className="flex gap-2 mt-5 pt-4 border-t border-border">
              <button onClick={() => navigate(`/jobs/${jobId}`)} className="btn btn-ghost">
                ← 返回 Job
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
