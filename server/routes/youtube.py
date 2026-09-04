"""/jobs/{id}/artifacts/{name}/... YouTube 上傳路由 (PR-3f)。

設計重點:
- 上傳是長時間操作 (4MB chunks resumable), 必須丟到 asyncio task 跑, route 立即回應
- progress 寫進 YoutubeUpload.progress_percent, 前端輪詢 youtube_status
- OAuth token 不存在時回 412 PRECONDITION_FAILED, 提示 user 跑 publish.py 一次

端點 (掛在主 jobs router 之外, 因為 prefix 不同):
    GET   /jobs/{id}/artifacts/{name}/youtube_meta      預填 metadata
    POST  /jobs/{id}/artifacts/{name}/publish           觸發上傳
    GET   /jobs/{id}/artifacts/{name}/youtube_status    輪詢狀態
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from ..background import spawn
from ..jobs import JobStore, get_default_store
from ..schemas import JobRecord, YoutubeUpload, YoutubeUploadState, utc_now


router = APIRouter(prefix="/jobs", tags=["youtube"])



def _require_artifact(job_id: str, name: str, store: JobStore) -> tuple[JobRecord, Path]:
    """取 (job_record, artifact 絕對路徑) 或丟 404 / 400。"""
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法 artifact 檔名")
    artifacts_dir = store.artifacts_dir(job_id)
    target = artifacts_dir / name
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"artifact 不存在: {name}")
    if target.suffix.lower() != ".mp4":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"只支援 .mp4 上傳, 收到: {target.suffix}",
        )
    return rec, target


# ---------- 預填 metadata ----------

@router.get("/{job_id}/artifacts/{name}/youtube_meta")
async def get_youtube_meta(
    job_id: str, name: str, store: JobStore = Depends(get_default_store),
) -> dict:
    """根據 deck.json + artifact stem 算預填 (title / description / tags / privacy)。

    若該 artifact 已上傳過, 直接回上次的 metadata (避免重新生成蓋掉 user 編輯)。
    """
    rec, _ = _require_artifact(job_id, name, store)

    existing = rec.youtube_uploads.get(name)
    if existing and existing.state == YoutubeUploadState.DONE:
        return existing.model_dump()

    # artifact stem 當預填基底 (考卷類 = problem_id; html_animation = 影片檔名)
    stem = Path(name).stem

    # 找 deck.json。html_animation 這類非 deck 來源沒有 deck.json, 不該 404 擋住上傳 —
    # 退化成「用檔名當標題」的最小預填, 其餘讓使用者在上傳前自行編輯。
    deck_path = store.deck_path(job_id)
    if not deck_path.exists():
        meta = {
            "title": stem,
            "description": "",
            "tags": [],
            "privacy": "unlisted",
            "category": "27",
        }
    else:
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        from core import auto_youtube_meta
        meta = auto_youtube_meta(deck, stem, source_type=rec.source_type.value)

    # 如果有 existing pending / failed 紀錄, 把 user 之前編過的覆蓋上去
    # (state=DONE 的已在開頭 return 了)
    if existing:
        for key in ("title", "description", "tags", "privacy", "category"):
            v = getattr(existing, key, None)
            if v:
                meta[key] = v

    return meta


# ---------- 觸發上傳 ----------

class PublishRequest(BaseModel):
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    privacy: str = "unlisted"
    category: str = "27"

    model_config = ConfigDict(extra="allow")


async def _do_publish(store: JobStore, job_id: str, name: str,
                      req: PublishRequest, video_path: Path) -> None:
    """背景 task: 跑 core.publish_artifact, 把進度與結果寫回 store。

    為什麼 catch 寬:
    - HttpError (上傳失敗) / OAuthBootstrapRequired / 任何 IO error
      都該標 failed 寫進 state, 不能讓 task crash 後 server 不知道
    """
    from core import publish_artifact, OAuthBootstrapRequired

    # 找同名 srt (例: q1.mp4 -> q1.srt)
    srt_path = video_path.with_suffix(".srt")
    if not srt_path.exists():
        srt_path = None

    # 進度 callback — 每 chunk 寫一次盤, IO 量小可接受
    def _on_progress(pct: int) -> None:
        store.patch_youtube_upload(job_id, name, progress_percent=pct)

    try:
        # to_thread: googleapiclient 是 sync, 不能 block event loop
        result = await asyncio.to_thread(
            publish_artifact,
            video_path,
            title=req.title,
            description=req.description,
            tags=req.tags,
            privacy=req.privacy,
            category=req.category,
            srt_path=srt_path,
            on_progress=_on_progress,
        )
    except OAuthBootstrapRequired as e:
        store.patch_youtube_upload(
            job_id, name,
            state=YoutubeUploadState.FAILED,
            error=f"OAuth 未授權: {e}",
        )
        return
    except Exception as e:
        store.patch_youtube_upload(
            job_id, name,
            state=YoutubeUploadState.FAILED,
            error=f"上傳失敗: {e}",
        )
        return

    store.patch_youtube_upload(
        job_id, name,
        state=YoutubeUploadState.DONE,
        video_id=result.video_id,
        url=result.url,
        caption_id=result.caption_id,
        caption_error=result.caption_error,
        progress_percent=100,
        uploaded_at=utc_now(),
    )


@router.post("/{job_id}/artifacts/{name}/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish(
    job_id: str, name: str, req: PublishRequest,
    store: JobStore = Depends(get_default_store),
) -> YoutubeUpload:
    """觸發背景上傳。

    重複呼叫: 若該 artifact 正在 UPLOADING, 回 409。
    若已 DONE 想重傳, 要先 DELETE state (目前不開, v3.2 再加)。
    """
    rec, video_path = _require_artifact(job_id, name, store)

    existing = rec.youtube_uploads.get(name)
    if existing and existing.state == YoutubeUploadState.UPLOADING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"artifact {name} 正在上傳中 (進度 {existing.progress_percent}%)",
        )
    if existing and existing.state == YoutubeUploadState.DONE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"artifact {name} 已上傳, video_id={existing.video_id}",
        )

    upload = YoutubeUpload(
        state=YoutubeUploadState.UPLOADING,
        title=req.title,
        description=req.description,
        tags=req.tags,
        privacy=req.privacy,
        category=req.category,
        progress_percent=0,
        started_at=utc_now(),
    )
    store.set_youtube_upload(job_id, name, upload)

    # 背景跑, 不 await。上傳是純網路等待, 不佔 render 名額(limit=False),
    # 但仍要走 spawn 保強參照, 免得 task 被 GC 掉導致上傳靜默中斷。
    spawn(
        _do_publish(store, job_id, name, req, video_path),
        name=f"youtube:{job_id}:{name}",
        limit=False,
    )

    return upload


# ---------- 輪詢狀態 ----------

@router.get("/{job_id}/artifacts/{name}/youtube_status", response_model=YoutubeUpload)
async def youtube_status(
    job_id: str, name: str, store: JobStore = Depends(get_default_store),
) -> YoutubeUpload:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    upload = rec.youtube_uploads.get(name)
    if upload is None:
        # 沒上傳過視為 pending 空白 record (前端輪詢前可能就跑這條)
        return YoutubeUpload()
    return upload


# ---------- 多語字幕軌（發布站多語上傳，方案 A）----------

class CaptionsRequest(BaseModel):
    """為已上傳的影片加多語字幕軌。languages = 目標語言（canonical 連字號）。"""

    languages: list[str]
    source_lang: str = "zh-TW"


async def _do_translate_and_upload(video_id: str, srt_text: str, source_lang: str,
                                   languages: list[str]) -> list[dict]:
    """逐語言翻譯 SRT → 暫存 → 上傳字幕軌。translate/上傳都 blocking → to_thread。"""
    import os
    import tempfile

    from core.caption_translate import translate_srt
    from core.langcode import to_underscore
    from core.translation.service import translator

    def _translate_fn(text: str, s: str, t: str) -> str:
        return translator.translate(text, to_underscore(s) or "auto", to_underscore(t) or t)

    captions, temp_paths = [], []
    for lang in languages:
        translated = await asyncio.to_thread(
            translate_srt, srt_text, source_lang, lang, _translate_fn)
        fd, path = tempfile.mkstemp(suffix=f".{lang}.srt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(translated)
        temp_paths.append(path)
        captions.append({"language": lang, "name": lang, "srt_path": Path(path)})
    try:
        from core import upload_captions
        return await asyncio.to_thread(upload_captions, video_id, captions)
    finally:
        for p in temp_paths:
            try:
                os.remove(p)
            except OSError:
                pass


@router.post("/{job_id}/artifacts/{name}/captions", status_code=status.HTTP_202_ACCEPTED)
async def add_captions(
    job_id: str, name: str, req: CaptionsRequest,
    store: JobStore = Depends(get_default_store),
) -> dict:
    """為已上傳的影片加多語字幕軌：翻譯既有 SRT → 各語上傳成 caption track。

    前置：該 artifact 必須已上傳（youtube_uploads[name].state==DONE 且有 video_id），
    且 artifacts/ 下有同名 .srt 當翻譯來源。回各語言上傳結果。
    """
    rec, _video = _require_artifact(job_id, name, store)
    upload = rec.youtube_uploads.get(name)
    if upload is None or upload.state != YoutubeUploadState.DONE or not upload.video_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "請先把影片上傳到 YouTube，再加多語字幕軌",
        )
    srt_path = store.artifacts_dir(job_id) / (Path(name).stem + ".srt")
    if not srt_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"找不到來源字幕 {srt_path.name}，無法翻譯成多語",
        )
    if not req.languages:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "languages 不可為空")

    srt_text = srt_path.read_text(encoding="utf-8")
    from core import OAuthBootstrapRequired
    try:
        results = await _do_translate_and_upload(
            upload.video_id, srt_text, req.source_lang, req.languages)
    except OAuthBootstrapRequired as e:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, str(e)) from e
    return {"video_id": upload.video_id, "captions": results}
