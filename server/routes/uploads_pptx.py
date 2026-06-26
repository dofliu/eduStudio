"""POST /upload/pptx — 上傳 .pptx 原檔, 為缺圖頁就地補圖 (原文字可編輯)。

跟 slides_pdf 補圖的差別: slides_pdf 把每頁渲成圖, 原文字變不可編輯。這條走
core.pptx_augment, 直接在原始 .pptx 上把 AI 配圖加進缺圖頁的空白區, 原本的文字
方塊全部保留可編輯。產出的 <stem>_augmented.pptx 落在 job artifacts/ 供下載。

獨立背景 task (PENDING → RENDERING → DONE/FAILED), 不經 deck/ingest pipeline。
需要 LibreOffice (pptx→pdf 分析) — 缺它則 job FAILED 並說明。
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from ..jobs import JobStore, get_default_store
from ..ratelimit import rate_limit
from ..schemas import (
    CreateJobRequest, CreateJobResponse, JobOptions, JobSource, JobState, SourceType,
)
from .uploads import MAX_UPLOAD_SIZE, _sanitize_filename, _unique_target_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["uploads"])

_PPTX_EXTS = {".pptx"}


async def _render_pptx_job(
    store: JobStore, job_id: str, *, src_pptx: Path, out_pptx: Path,
    only_missing: bool, mock: bool,
) -> None:
    store.update(job_id, state=JobState.RENDERING)
    try:
        from core.pptx_augment import augment_pptx
        summary = await asyncio.to_thread(
            augment_pptx, src_pptx, out_pptx,
            work_dir=store.job_dir(job_id) / "work",
            only_missing=only_missing, mock=mock,
        )
        logger.info("PPTX 補圖 job %s: %s", job_id, summary)
    except Exception as e:  # noqa: BLE001
        logger.exception("PPTX 補圖失敗 (job=%s)", job_id)
        store.update(job_id, state=JobState.FAILED, error=f"PPTX 補圖失敗: {e}")
        return
    store.refresh_artifacts(job_id)
    store.update(job_id, state=JobState.DONE)


@router.post(
    "/pptx",
    response_model=CreateJobResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit)],
)
async def upload_pptx(
    request: Request,
    file: UploadFile = File(..., description=".pptx 原檔"),
    only_missing: bool = Form(True, description="True 只補偵測到的缺圖頁; False 每頁都生"),
    options_json: str = Form("{}", description="JobOptions JSON (目前只用 mock)"),
    project_id: str = Form("", description="可選: 歸屬的 Project"),
    store: JobStore = Depends(get_default_store),
) -> CreateJobResponse:
    """收 .pptx, 背景就地補圖, 產出可編輯的 <stem>_augmented.pptx 供下載。"""
    if not file.filename or Path(file.filename).suffix.lower() not in _PPTX_EXTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "只接受 .pptx 檔")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"檔案過大, 超過上限 {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
        )
    contents = await file.read()
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上傳的 PPTX 是空的")
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"檔案過大, 超過上限 {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
        )

    try:
        opts = json.loads(options_json) if options_json else {}
        if not isinstance(opts, dict):
            raise ValueError("options_json 不是 JSON 物件")
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"options_json 解析失敗: {e}")
    options = JobOptions(mock=bool(opts.get("mock", False)), require_review=False)

    rec = store.create(CreateJobRequest(
        source_type=SourceType.PPTX, source=JobSource(), options=options,
    ))

    # 原檔落地到 jobs/<id>/source/
    src_dir = store.job_dir(rec.id) / "source"
    src_dir.mkdir(parents=True, exist_ok=True)
    src_pptx = _unique_target_path(src_dir, _sanitize_filename(file.filename))
    src_pptx.write_bytes(contents)
    rec = store.update(rec.id, source=JobSource(path=str(src_pptx.resolve())))

    if project_id:
        from core.project import ProjectNotFoundError
        from .projects import get_default_project_store
        try:
            get_default_project_store().add_job(project_id, rec.id)
        except ProjectNotFoundError as e:
            store.delete(rec.id)
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {project_id}") from e

    stem = Path(_sanitize_filename(file.filename)).stem or "deck"
    out_pptx = store.artifacts_dir(rec.id) / f"{stem}_augmented.pptx"
    asyncio.create_task(_render_pptx_job(
        store, rec.id, src_pptx=src_pptx, out_pptx=out_pptx,
        only_missing=only_missing, mock=bool(options.mock),
    ))

    return CreateJobResponse(job_id=rec.id, state=rec.state, status_url=f"/jobs/{rec.id}")
