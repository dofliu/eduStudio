"""POST /upload — multipart PDF/MD/TXT 上傳並建立 job (PR-3k)。

之前 Track A 的 /upload 用 Flask 接 multipart, 把檔案存到 pdfs/ 然後 dispatch
solve.py / slide_ingest.py。Track B 的 /jobs 只接 JSON + source.path, 使用者
得自己把檔案放到 server 看得到的路徑。這個端點補上多部分上傳, 讓 React UI
可以直接拖檔。

設計:
- 接受 source_type ∈ {exam_pdf, slides_pdf, document}; repo / url 不能上傳
- 檔案存到 PROJECT_ROOT/pdfs/<sanitized>.<ext>, 同名加時間戳避免覆蓋
- 內部呼叫既有 /jobs POST 的 create_job 邏輯 (透過 store.create + schedule_job)
- 前端送 FormData, 不是 JSON

Response 跟 /jobs POST 一致 (CreateJobResponse), 前端可重用刷新邏輯。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from core.config import PROJECT_ROOT

from ..jobs import JobStore, get_default_store
from ..runner import schedule_job
from ..schemas import (
    CreateJobRequest,
    CreateJobResponse,
    JobOptions,
    JobSource,
    SourceType,
)


router = APIRouter(prefix="/upload", tags=["uploads"])


PDFS_DIR = PROJECT_ROOT / "pdfs"

# 檔名清理: 跟 Track A app.py 同套規則, 避免 path injection / Windows 保留字
_FNAME_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *[f"COM{i}" for i in range(1, 10)],
    *[f"LPT{i}" for i in range(1, 10)],
}

# 上傳允許的 source_type (其他類型沒有對應的檔案概念)
UPLOADABLE_SOURCE_TYPES = {
    SourceType.EXAM_PDF,
    SourceType.SLIDES_PDF,
    SourceType.DOCUMENT,
}


def _sanitize_filename(name: str) -> str:
    """清理上傳檔名 — 保留中文 / 英數 / 底線 / 橫線, 移除路徑字元跟 Windows 保留字。"""
    name = name.strip()
    name = _FNAME_BAD.sub("", name)
    name = re.sub(r"\.\.+", "", name)
    name = name.strip(". ")
    if not name:
        name = "upload"
    base, dot, ext = name.rpartition(".")
    if base.upper() in _WIN_RESERVED:
        base = f"_{base}"
    return f"{base}{dot}{ext}" if dot else name


def _unique_target_path(directory: Path, filename: str) -> Path:
    """同名檔已存在時加時間戳, 不覆蓋既有檔。"""
    target = directory / filename
    if not target.exists():
        return target
    base, dot, ext = filename.rpartition(".")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"{base}_{ts}{dot}{ext}" if dot else f"{filename}_{ts}"
    return directory / new_name


def _store() -> JobStore:
    return get_default_store()


@router.post("", response_model=CreateJobResponse, status_code=status.HTTP_201_CREATED)
async def upload_and_create_job(
    file: UploadFile = File(..., description="PDF / MD / TXT 檔案"),
    source_type: SourceType = Form(..., description="exam_pdf / slides_pdf / document"),
    options_json: str = Form(
        "{}",
        description="JobOptions 的 JSON 字串 (例: {\"mock\": true, \"require_review\": true})",
    ),
    store: JobStore = Depends(_store),
) -> CreateJobResponse:
    """收 multipart 檔案, 存到 pdfs/, 然後建 job 並排程。

    跟 /jobs POST 走完全一樣的流程, 差別只在 source.path 由 server 端決定
    (= 上傳後的儲存路徑), 不需要 caller 提供。
    """
    if source_type not in UPLOADABLE_SOURCE_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"source_type={source_type.value} 不支援檔案上傳。"
            f"只接受 {[s.value for s in UPLOADABLE_SOURCE_TYPES]}, "
            f"repo / url 請走 POST /jobs JSON",
        )

    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "缺檔名")

    # 解析 options
    try:
        opts_dict = json.loads(options_json) if options_json else {}
        if not isinstance(opts_dict, dict):
            raise ValueError("options_json 不是 JSON 物件")
    except Exception as e:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"options_json 解析失敗: {e}",
        )
    options = JobOptions(**opts_dict)

    # 存檔
    PDFS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(file.filename)
    target = _unique_target_path(PDFS_DIR, safe_name)

    contents = await file.read()
    if not contents:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "上傳的檔案是空的")
    target.write_bytes(contents)

    # 建 job, schedule render — 等同 POST /jobs 的後半段流程
    req = CreateJobRequest(
        source_type=source_type,
        source=JobSource(path=str(target.resolve())),
        options=options,
    )
    rec = store.create(req)
    schedule_job(store, rec.id)

    return CreateJobResponse(
        job_id=rec.id,
        state=rec.state,
        status_url=f"/jobs/{rec.id}",
    )
