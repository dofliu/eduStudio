"""GET /library — 跨 job 把所有 mp4 artifact 平鋪 (PR-3m)。

Track A 的 /library 把所有考卷 / 簡報的 mp4 列在一頁, 方便瀏覽 + 一鍵上傳。
Track B 之前只有 JobsIndex (列 job, 不平鋪 artifact), 這條補上。

設計:
- 純讀, 從 JobStore + 掃 jobs/<id>/artifacts/
- 每筆 = 一支 mp4, 帶 job 與 artifact 兩端的 metadata
- Filter / sort 在前端做 (資料量小, 不必後端分頁)
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..jobs import JobStore, get_default_store
from ..schemas import SourceType, YoutubeUpload, YoutubeUploadState


router = APIRouter(prefix="/library", tags=["library"])


def _store() -> JobStore:
    return get_default_store()


# ---------- Schema ----------

class LibraryItem(BaseModel):
    """單支 mp4 的扁平 view, 給 React Library 頁直接用。"""
    job_id: str
    artifact_name: str          # "q1.mp4" / "ch1.mp4"
    source_type: SourceType
    deck_title: str             # exam_title / deck_title (從 deck.json 抓)
    mp4_size_bytes: int
    srt_exists: bool             # 同名 .srt 存在 → 上傳能帶字幕
    youtube: YoutubeUpload | None = None     # 上傳記錄, 沒上傳過為 None
    artifact_url: str            # GET /jobs/{id}/artifacts/{name}, 給 <video src>
    publish_url: str             # /ui/jobs/{id}/publish/{name}, 給 React Router


class LibraryResponse(BaseModel):
    items: list[LibraryItem]
    total: int = Field(..., description="總 mp4 數 (含已上傳 / 未上傳)")


# ---------- Helper ----------

def _read_deck_title(job_id: str) -> str:
    """從 jobs/<id>/deck.json 抓 exam_title / deck_title, 找不到就退到 job_id。"""
    deck_path = JobStore.deck_path(job_id)
    if not deck_path.exists():
        return job_id
    try:
        import json
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
    except Exception:
        return job_id
    return (deck.get("exam_title") or deck.get("deck_title") or job_id).strip()


# ---------- Route ----------

@router.get("", response_model=LibraryResponse)
async def list_library(store: JobStore = Depends(_store)) -> LibraryResponse:
    """跨所有 job 列出 mp4。新到舊 (job created_at desc)。"""
    items: list[LibraryItem] = []
    for job in store.list():    # 已經 created_at desc
        # 只關心已渲染完成或進行中的, ingesting / failed 不在這頁出現
        # (FAILED 沒 mp4, ingesting 也沒)
        mp4s = [a for a in job.artifacts if a.kind == "mp4"]
        if not mp4s:
            continue
        deck_title = _read_deck_title(job.id)
        artifacts_dir = JobStore.artifacts_dir(job.id)
        for a in mp4s:
            srt_path = artifacts_dir / Path(a.name).with_suffix(".srt").name
            yt = job.youtube_uploads.get(a.name) if job.youtube_uploads else None
            items.append(LibraryItem(
                job_id=job.id,
                artifact_name=a.name,
                source_type=job.source_type,
                deck_title=deck_title,
                mp4_size_bytes=a.size_bytes,
                srt_exists=srt_path.exists(),
                youtube=yt,
                artifact_url=f"/jobs/{job.id}/artifacts/{a.name}",
                publish_url=f"/ui/jobs/{job.id}/publish/{a.name}",
            ))
    return LibraryResponse(items=items, total=len(items))
