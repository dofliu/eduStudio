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

from ..jobs import JobStore, get_default_store
from ..schemas import JobRecord, YoutubeUpload, YoutubeUploadState, utc_now


router = APIRouter(prefix="/jobs", tags=["youtube"])


def _store() -> JobStore:
    return get_default_store()


def _require_artifact(job_id: str, name: str, store: JobStore) -> tuple[JobRecord, Path]:
    """取 (job_record, artifact 絕對路徑) 或丟 404 / 400。"""
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法 artifact 檔名")
    artifacts_dir = JobStore.artifacts_dir(job_id)
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
    job_id: str, name: str, store: JobStore = Depends(_store),
) -> dict:
    """根據 deck.json + artifact stem 算預填 (title / description / tags / privacy)。

    若該 artifact 已上傳過, 直接回上次的 metadata (避免重新生成蓋掉 user 編輯)。
    """
    rec, _ = _require_artifact(job_id, name, store)

    existing = rec.youtube_uploads.get(name)
    if existing and existing.state == YoutubeUploadState.DONE:
        return existing.model_dump()

    # 找 deck.json
    deck_path = JobStore.deck_path(job_id)
    if not deck_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "deck.json 不存在, 無法產預填 metadata",
        )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))

    # artifact name = "{problem_id}.mp4", 取 stem 當 problem_id
    problem_id = Path(name).stem

    from core import auto_youtube_meta
    meta = auto_youtube_meta(deck, problem_id, source_type=rec.source_type.value)

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
    store: JobStore = Depends(_store),
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

    # 背景跑, 不 await
    asyncio.create_task(_do_publish(store, job_id, name, req, video_path))

    return upload


# ---------- 輪詢狀態 ----------

@router.get("/{job_id}/artifacts/{name}/youtube_status", response_model=YoutubeUpload)
async def youtube_status(
    job_id: str, name: str, store: JobStore = Depends(_store),
) -> YoutubeUpload:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    upload = rec.youtube_uploads.get(name)
    if upload is None:
        # 沒上傳過視為 pending 空白 record (前端輪詢前可能就跑這條)
        return YoutubeUpload()
    return upload
