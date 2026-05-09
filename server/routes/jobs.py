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
    from ..schemas import SourceType

    # 依 source_type 做早期驗證 — 拼錯路徑 / 缺欄位的常見錯誤先攔下
    if req.source_type == SourceType.URL:
        url = (req.source.url or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "source_type=url 時必須提供 source.url (http:// 或 https://)",
            )
    else:
        if not req.source.path:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"source_type={req.source_type.value} 時必須提供 source.path",
            )
        if not Path(req.source.path).exists():
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
    """覆寫 deck.json。

    可編輯的狀態:
    - awaiting_review: ingest 完成等人工 review (主路徑)
    - failed:          render 失敗後可改 deck.json 再重試 (PR-3j 加入,
                       避免使用者要從頭跑 ingest 30 分鐘)

    其他狀態擋住, 避免 race condition (例: rendering 中改 deck 會跟在跑的渲染衝突)。
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if rec.state not in (JobState.AWAITING_REVIEW, JobState.FAILED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"目前狀態 {rec.state.value}, 僅 awaiting_review / failed 可改 deck",
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
    """進入 rendering 階段。可在兩種狀態觸發:

    - awaiting_review: 主路徑, 第一次 review 通過開始渲染
    - failed:          重試 render (PR-3j 加入)。deck.json 視為已 review,
                       新一輪 _run_render_phase 會把 state=FAILED 翻 RENDERING,
                       error 清掉, 加新的 "render" stage。

    擋住 rendering / done / pending / ingesting (避免覆寫進行中或既有成果)。
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if rec.state not in (JobState.AWAITING_REVIEW, JobState.FAILED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"approve 僅在 awaiting_review / failed 可用 (目前 {rec.state.value})",
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
