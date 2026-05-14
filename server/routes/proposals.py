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

from ..ideate_runner import get_scan_state, run_ideate_async, start_async_scan
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


class ProposalApproveRequest(BaseModel):
    """POST /proposals/{id}/approve 的 optional body (iter 40).

    讓 UI 在核准前選 pptx 主題 / 燒字幕等選項, 不必先核准再去 review page 改.
    全欄位 optional, 不傳就走 JobOptions() 預設 (forest / no hardsub).

    為什麼不直接吃整顆 JobOptions: 核准 endpoint 不該讓 caller 改 require_review,
    那是學術誠信底線 (硬規則 #1), 由 source_type 決定 (exam_pdf → True).
    所以這裡只開放真的「主題 / 字幕」這類無風險選項.
    """

    theme: Literal["forest", "navy", "frieren", "naruto", "journal"] | None = None
    hardsub: bool | None = None
    prepend_intro: bool | None = None     # iter 41: 串個人 intro 開場


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


class ScanAsyncResponse(BaseModel):
    """POST /proposals/scan-folder/async 回應 — 立刻回 scan_id, 不等完成."""

    scan_id: str


class ScanStatusResponse(BaseModel):
    """GET /proposals/scan-status/{scan_id} 回應 — 進度查詢."""

    state: str            # "running" | "done" | "failed"
    scanned: int = 0
    proposed: int = 0
    new: int = 0
    error: str | None = None
    message: str = ""     # 最近一條 progress 訊息
    started_at: str | None = None
    ended_at: str | None = None


# ============================================================
# Helpers
# ============================================================



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
    body: ProposalApproveRequest | None = None,
    store: JobStore = Depends(get_default_store),
) -> ProposalApproveResponse:
    """核准提案 → 走 /upload 同一條 schedule_job 流程。

    iter 40: 加 optional body (theme / hardsub) — UI 可在卡片上選主題後核准,
    不必走「先核准 → review page 改 → 重 render」這條繞路.

    require_review 不在這層動 (依 source_type 預設, exam=True / 其他=False),
    UI 上若 user 想跳 review 要在 review page 改, 這條 endpoint 一律走預設.
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

    # 把 body 上的選項 (theme / hardsub / prepend_intro) 套進 JobOptions
    opts_kwargs: dict = {}
    if body is not None:
        if body.theme is not None:
            opts_kwargs["theme"] = body.theme
        if body.hardsub is not None:
            opts_kwargs["hardsub"] = body.hardsub
        if body.prepend_intro is not None:
            opts_kwargs["prepend_intro"] = body.prepend_intro

    req = CreateJobRequest(
        source_type=source_type,
        source=JobSource(path=target["source_file"]),
        options=JobOptions(**opts_kwargs),  # 預設, 不繞 require_review
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


def _build_scan_config(req: "ScanFolderRequest", folder: Path) -> dict:
    """req → IdeateConfig dict 共用 helper (sync + async 兩條 endpoint 都用)."""
    return {
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


@router.post("/scan-folder/async", response_model=ScanAsyncResponse, status_code=status.HTTP_202_ACCEPTED)
async def scan_folder_async(
    req: ScanFolderRequest,
    store: JobStore = Depends(get_default_store),
) -> ScanAsyncResponse:
    """非同步觸發 ideate 掃描. 立刻回 scan_id, 不等完成。

    UI 拿 scan_id 後 poll GET /proposals/scan-status/{scan_id} 看進度。
    解決同步版 (POST /scan-folder) 等 10 分鐘 modal 卡住的 UX 問題。

    錯誤:
        folder 不存在 / 不是資料夾 → 400 (early validation, 不浪費 scan_id)
    """
    folder = Path(req.folder)
    if not folder.exists():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"資料夾不存在: {req.folder}",
        )
    if not folder.is_dir():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"不是資料夾: {req.folder}",
        )

    config = _build_scan_config(req, folder)
    scan_id = start_async_scan(config, store=store)
    return ScanAsyncResponse(scan_id=scan_id)


@router.get("/scan-status/{scan_id}", response_model=ScanStatusResponse)
async def get_scan_status(scan_id: str) -> ScanStatusResponse:
    """查 async scan 進度.

    回 ScanStatusResponse: state ("running"/"done"/"failed") + metrics + message。
    過 1 小時的 scan id (狀態 ended 後) 會被 GC, 拿不到時 404。
    """
    state = get_scan_state(scan_id)
    if state is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"scan_id={scan_id} 不存在 (可能過期 1 小時或從未產生)",
        )
    return ScanStatusResponse(**state)


@router.post("/scan-folder", response_model=ScanResponse)
async def scan_folder(
    req: ScanFolderRequest,
    store: JobStore = Depends(get_default_store),
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
    config = _build_scan_config(req, folder)
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
