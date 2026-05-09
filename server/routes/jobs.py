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
from ..runner import schedule_job, schedule_render, schedule_section_render
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


# ---------- Job log tail (PR-4c) ----------

@router.get("/{job_id}/log")
async def get_job_log(
    job_id: str, tail: int = 200, store: JobStore = Depends(_store),
) -> JSONResponse:
    """讀 jobs/<id>/log.jsonl 末尾 N 筆 log, 給 React UI 即時看 render 進度。

    回傳: {"entries": [{ts, level, logger, msg, job_id, stage?, ...}, ...]}
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if tail < 1 or tail > 2000:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "tail 必須在 1~2000 之間",
        )
    from core.logging_setup import read_job_log
    log_path = JobStore.job_dir(job_id) / "log.jsonl"
    entries = read_job_log(log_path, tail=tail)
    return JSONResponse(content={"entries": entries})


# ---------- Section render (PR-4a) ----------

def _deck_has_section_id(deck: dict, section_id: str) -> bool:
    """deck 可能是 v1 exam (problems) 或新 deck schema (sections), 兩邊找。"""
    for p in deck.get("problems", []):
        if p.get("id") == section_id:
            return True
    for s in deck.get("sections", []):
        if s.get("id") == section_id:
            return True
    return False


@router.post("/{job_id}/sections/{section_id}/render", response_model=JobRecord)
async def render_section(
    job_id: str, section_id: str, store: JobStore = Depends(_store),
) -> JobRecord:
    """重新渲染單一 section / problem (PR-4a)。

    使用情境: render 完發現某章 narration 想改, 改完按這個重跑該章 mp4,
    其他章保留既有 artifact 不動。50 頁簡報改一章可省 ~30 分鐘。

    狀態檢查:
    - DONE: 正常 re-render 該章 (覆蓋舊 mp4)
    - FAILED: 用於上次 render 在某章炸了, 修完 deck 後想只重跑那一章
    - 其他狀態 (rendering / ingesting / awaiting_review / pending) → 409
    """
    rec = store.get(job_id)
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"job {job_id} 不存在")
    if rec.state not in (JobState.DONE, JobState.FAILED):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"section render 僅在 done / failed 可用 (目前 {rec.state.value})",
        )

    deck_path = JobStore.deck_path(job_id)
    if not deck_path.exists():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "deck.json 不存在, 無法 render",
        )
    deck = json.loads(deck_path.read_text(encoding="utf-8"))
    if not _deck_has_section_id(deck, section_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"section_id={section_id} 在 deck 中找不到",
        )

    schedule_section_render(store, job_id, section_id)
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
