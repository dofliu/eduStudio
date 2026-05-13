"""POST /proposals — ideate.py 自動企劃的 REST 端點 (v4 階段 2 B iter 14)。

設計見 docs/ideate-design.md。三條 endpoints:
  - GET /proposals           列出 PENDING 提案
  - POST /proposals/{id}/approve   核准 → 建 job + schedule_job
  - PATCH /proposals/{id}/ignore   忽略, 不建 job

approve 流程**不繞 require_review=True** (P0 #4 學術誠信底線) —
跟 /upload 走完全一樣的 store.create + schedule_job, require_review 由
server.jobs._resolve_default_review 依 source_type 預設 (exam_pdf=True)。

不在這層實作:
  - 跑 ideate 產 proposals.json (那是 CLI / 定時排程的工作, iter 22+ 補)
  - React UI ProposalsList page (iter 22)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.config import PROPOSALS_PATH
from core.ideate import (
    ProposalStatus,
    load_proposals,
    save_proposals,
)

from ..ideate_runner import run_ideate_async
from ..jobs import JobStore, get_default_store
from ..runner import schedule_job
from ..schemas import (
    CreateJobRequest,
    CreateJobResponse,
    JobOptions,
    JobSource,
    SourceType,
)


router = APIRouter(prefix="/proposals", tags=["proposals"])


# ============================================================
# Response models (對應 core.ideate.Proposal TypedDict)
# ============================================================


class ProposalResponse(BaseModel):
    """單一提案的 API 視圖 (對應 Proposal TypedDict)."""

    id: str
    generated_at: str
    source_file: str
    source_type: str
    suggested_title: str
    suggested_chapters: list[str] = Field(default_factory=list)
    reason: str
    estimated_duration_min: int
    status: str
    job_id: str | None = None


class ProposalListResponse(BaseModel):
    proposals: list[ProposalResponse]


class ProposalApproveResponse(BaseModel):
    proposal: ProposalResponse
    job: CreateJobResponse


class ProposalStatusUpdateRequest(BaseModel):
    """PATCH 用 — 目前只接受 ignored (approve 走專用 endpoint)."""

    status: Literal["ignored"]


class ScanFolderRequest(BaseModel):
    """POST /proposals/scan-folder 接的 body."""

    folder: str = Field(..., description="要掃的資料夾絕對路徑 (server 本機可讀)")
    source_type: Literal["auto", "exam_pdf", "slides_pdf", "document"] = Field(
        default="auto",
        description="source_type 強制值, auto = Gemini Vision 自動判斷每份 PDF",
    )
    scan_window_days: int = Field(default=30, ge=1, le=3650)
    max_proposals_per_file: int = Field(default=3, ge=1, le=10)


class ScanResponse(BaseModel):
    """POST /proposals/scan-folder 回應 — 跑完一輪 ideate 的 metrics."""

    ok: bool
    scanned: int = 0
    proposed: int = 0
    new: int = 0
    error: str | None = None


# ============================================================
# Helpers
# ============================================================


def _store() -> JobStore:
    return get_default_store()


def _load_all() -> list[dict]:
    """讀 proposals.json 內全部 (任何 status)."""
    return list(load_proposals(PROPOSALS_PATH))


def _find_proposal(proposals: list[dict], proposal_id: str) -> dict:
    """找特定 id, 找不到 raise 404."""
    for p in proposals:
        if p.get("id") == proposal_id:
            return p
    raise HTTPException(
        status.HTTP_404_NOT_FOUND,
        f"proposal_id={proposal_id} 不存在 (可能已被刪 / 從未產出)",
    )


def _persist(proposals: list[dict]) -> None:
    """atomic write 回 proposals.json."""
    save_proposals(PROPOSALS_PATH, proposals)


# ============================================================
# Routes
# ============================================================


@router.get("", response_model=ProposalListResponse)
async def list_proposals(only_pending: bool = True) -> ProposalListResponse:
    """列出所有提案. 預設只回 PENDING (UI 通常只顯示待決策的)。

    參數:
        only_pending: True (預設) 過濾掉 APPROVED / IGNORED / EXPIRED
    """
    proposals = _load_all()
    if only_pending:
        proposals = [p for p in proposals if p.get("status") == ProposalStatus.PENDING.value]
    return ProposalListResponse(proposals=[ProposalResponse(**p) for p in proposals])


@router.post(
    "/{proposal_id}/approve",
    response_model=ProposalApproveResponse,
    status_code=status.HTTP_201_CREATED,
)
async def approve_proposal(
    proposal_id: str,
    store: JobStore = Depends(_store),
) -> ProposalApproveResponse:
    """核准提案 → 走 /upload 同一條 schedule_job 流程。

    require_review 不在這層動 (依 source_type 預設, exam=True / 其他=False),
    UI 上若 user 想跳 review 要在 review page 改, 這條 endpoint 一律走預設。
    """
    proposals = _load_all()
    target = _find_proposal(proposals, proposal_id)

    if target.get("status") != ProposalStatus.PENDING.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"proposal_id={proposal_id} 不是 pending 狀態 (現在 {target.get('status')})",
        )

    # 建 job — 跟 /upload 走完全一樣的 store.create + schedule_job 流程
    try:
        source_type = SourceType(target["source_type"])
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"source_type={target['source_type']} 不是合法 SourceType",
        )

    req = CreateJobRequest(
        source_type=source_type,
        source=JobSource(path=target["source_file"]),
        options=JobOptions(),  # 預設, 不繞 require_review
    )
    rec = store.create(req)
    schedule_job(store, rec.id)

    # 更新 proposals.json: status=APPROVED + job_id
    target["status"] = ProposalStatus.APPROVED.value
    target["job_id"] = rec.id
    _persist(proposals)

    job_resp = CreateJobResponse(
        job_id=rec.id,
        state=rec.state,
        status_url=f"/jobs/{rec.id}",
    )
    return ProposalApproveResponse(
        proposal=ProposalResponse(**target),
        job=job_resp,
    )


@router.post("/scan-folder", response_model=ScanResponse)
async def scan_folder(
    req: ScanFolderRequest,
    store: JobStore = Depends(_store),
) -> ScanResponse:
    """掃一個指定資料夾, 跑 ideate 流程。

    UI 按鈕呼叫的就是這條 (取代 iter 26 的 /scan + yaml flow). 用戶在前端
    modal 填 folder path 跟 (進階) 參數, 後端組成 IdeateConfig 餵 run_ideate。

    流程: scan → propose (Gemini Vision) → dedupe → 寫 proposals.json。
    這條走 to_thread, 不阻 event loop, 但 await 完成才回 — UI 可能等 10+ 分鐘。

    錯誤回應 (validation 失敗): FastAPI 自動 422 + 詳情, caller 看 detail。
    執行錯誤 (Gemini quota / 檔案讀不到): 200 + ok=False + error msg。
    """
    folder = Path(req.folder)
    if not folder.exists():
        return ScanResponse(ok=False, error=f"資料夾不存在: {req.folder}")
    if not folder.is_dir():
        return ScanResponse(ok=False, error=f"不是資料夾: {req.folder}")

    # 組 ad-hoc IdeateConfig — UI 模式只掃單一資料夾
    config: dict = {
        "watched_folders": [
            {
                "path": str(folder.resolve()),
                "source_type": req.source_type,
                "scan_window_days": req.scan_window_days,
            }
        ],
        "llm_model": "gemini-2.5-flash",
        "max_proposals_per_file": req.max_proposals_per_file,
        "enabled": True,
    }
    result = await run_ideate_async(config, store=store)
    return ScanResponse(**result)


@router.patch("/{proposal_id}/ignore", response_model=ProposalResponse)
async def ignore_proposal(proposal_id: str) -> ProposalResponse:
    """忽略提案 (status=IGNORED). 不建 job, 純粹標記。"""
    proposals = _load_all()
    target = _find_proposal(proposals, proposal_id)

    if target.get("status") != ProposalStatus.PENDING.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"proposal_id={proposal_id} 不是 pending 狀態 (現在 {target.get('status')})",
        )

    target["status"] = ProposalStatus.IGNORED.value
    _persist(proposals)
    return ProposalResponse(**target)
