"""/jobs API routes — 把 server/jobs.py + runner.py 接到 FastAPI。

端點清單:
    POST   /jobs                          建立並排程
    GET    /jobs                          列出 (created_at desc)
    GET    /jobs/{id}                     取單一狀態
    DELETE /jobs/{id}                     刪除 (含磁碟資料)
    GET    /jobs/{id}/draft               取 deck.json (review / done 階段)
    PUT    /jobs/{id}/draft               覆寫 deck.json (僅 awaiting_review)
    POST   /jobs/{id}/approve             從 awaiting_review 進入 render
    GET    /jobs/{id}/artifacts/{name}    下載產物檔
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse

from ..jobs import JobStore, get_default_store
from ..runner import schedule_job, schedule_render
from ..schemas import (
    CreateJobRequest,
    CreateJobResponse,
    JobListResponse,
    JobRecord,
    JobState,
    UpdateDeckRequest,
)


router = APIRouter(prefix="/jobs", tags=["jobs"])


def _store() -> JobStore:
    return get_default_store()


def _require_job(job_id: str, store: JobStore = Depends(_store)) -> JobRecord:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    return rec


# ---------- CRUD ----------

@router.post("", response_model=CreateJobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(req: CreateJobRequest, store: JobStore = Depends(_store)) -> CreateJobResponse:
    """建立 job 並立即在背景排程。回應裡的 status_url 可拿來 poll 狀態。"""
    # 早期驗證: source.path 至少要存在,否則使用者很容易拼錯路徑
    src_path = Path(req.source.path)
    if not src_path.exists():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"source.path 不存在: {req.source.path}",
        )

    rec = store.create(req)
    schedule_job(store, rec.id)
    return CreateJobResponse(
        job_id=rec.id,
        state=rec.state,
        status_url=f"/jobs/{rec.id}",
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(store: JobStore = Depends(_store)) -> JobListResponse:
    return JobListResponse(jobs=store.list())


@router.get("/{job_id}", response_model=JobRecord)
async def get_job(rec: JobRecord = Depends(_require_job)) -> JobRecord:
    return rec


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(job_id: str, store: JobStore = Depends(_store)) -> None:
    if not store.delete(job_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")


# ---------- Draft (deck.json) ----------

@router.get("/{job_id}/draft")
async def get_draft(job_id: str, store: JobStore = Depends(_store)) -> JSONResponse:
    """取 deck.json — ingest 完之後就有,直到 job 被刪除前都可讀。"""
    deck_path = JobStore.deck_path(job_id)
    if not deck_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "deck.json 尚未產生 (ingest 未完成或已失敗)",
        )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    return JSONResponse(content=deck)


@router.put("/{job_id}/draft", response_model=JobRecord)
async def update_draft(
    job_id: str, body: UpdateDeckRequest, store: JobStore = Depends(_store),
) -> JobRecord:
    """覆寫 deck.json。僅 awaiting_review 狀態可改 (避免 race condition)。"""
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if rec.state != JobState.AWAITING_REVIEW:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"目前狀態 {rec.state.value}, 僅 awaiting_review 可改 deck",
        )
    JobStore.deck_path(job_id).write_text(
        json.dumps(body.deck, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 更新 timestamp 反映有手改過 (狀態維持不變)
    return store.update(job_id)


# ---------- Approve ----------

@router.post("/{job_id}/approve", response_model=JobRecord)
async def approve_job(job_id: str, store: JobStore = Depends(_store)) -> JobRecord:
    """從 awaiting_review 進入 rendering。

    僅 awaiting_review 狀態合法。done / failed 可重新跑 render: 但要先把
    job 改回 awaiting_review (目前不開放這條路, 避免誤觸覆寫成果)。
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if rec.state != JobState.AWAITING_REVIEW:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"approve 僅在 awaiting_review 可用 (目前 {rec.state.value})",
        )
    schedule_render(store, job_id)
    return store.get(job_id)


# ---------- Artifacts ----------

@router.get("/{job_id}/artifacts/{name}")
async def download_artifact(job_id: str, name: str, store: JobStore = Depends(_store)) -> FileResponse:
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    # 防 path traversal: 只接受 name 為單純檔名,不能含 / 或 ..
    if "/" in name or "\\" in name or ".." in name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法 artifact 檔名")
    target = JobStore.artifacts_dir(job_id) / name
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"artifact 不存在: {name}")
    return FileResponse(target, filename=name)
