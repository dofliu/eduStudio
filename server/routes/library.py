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

def _read_deck_title(store: JobStore, job_id: str) -> str:
    """從 jobs/<id>/deck.json 抓 exam_title / deck_title, 找不到就退到 job_id。"""
    deck_path = store.deck_path(job_id)
    if not deck_path.exists():
        return job_id
    # try 要包到最後 return: 不只 json.loads 會炸, deck 非 dict (頂層是 list /
    # str) 時 deck.get 噴 AttributeError, title 是 non-str truthy (例 42 / [..])
    # 時 .strip() 也炸 — 任一條都該 graceful 退 job_id, 不該讓整頁 Library 掛 500.
    try:
        import json
        deck = json.loads(deck_path.read_text(encoding="utf-8"))
        return (deck.get("exam_title") or deck.get("deck_title") or job_id).strip()
    except Exception:
        return job_id


# ---------- Route ----------

@router.get("", response_model=LibraryResponse)
async def list_library(store: JobStore = Depends(get_default_store)) -> LibraryResponse:
    """跨所有 job 列出 mp4。新到舊 (job created_at desc)。

    iter 47: 若 job 有 final.mp4 (iter 45 多章合成), library 只列 final.mp4 —
    那是主交付, 各章獨立 mp4 是除錯 / re-render 用, 不該佔 library 版面.
    沒 final.mp4 (考卷單題影片 / 單章 deck) 走原 logic 全列.
    """
    items: list[LibraryItem] = []
    for job in store.list():    # 已經 created_at desc
        # 只關心已渲染完成或進行中的, ingesting / failed 不在這頁出現
        # (FAILED 沒 mp4, ingesting 也沒)
        mp4s = [a for a in job.artifacts if a.kind == "mp4"]
        if not mp4s:
            continue

        # iter 47: 有 final.mp4 就只列它, 各章 mp4 隱去
        final_mp4 = next((a for a in mp4s if a.name == "final.mp4"), None)
        listed_mp4s = [final_mp4] if final_mp4 else mp4s

        deck_title = _read_deck_title(store, job.id)
        artifacts_dir = store.artifacts_dir(job.id)
        for a in listed_mp4s:
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
