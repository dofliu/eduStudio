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
import unicodedata
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

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

# 上傳大小上限 (bytes). 200 MB 大於合理教學 PDF, 小於記憶體炸點 (await file.read()
# 整檔載入). 真要超過 200 MB 應走分塊上傳; 現階段不需要。
MAX_UPLOAD_SIZE = 200 * 1024 * 1024

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

# S-4 上傳硬化: 副檔名白名單 (per source_type)。pdf 類只收 .pdf;
# document 另收純文字/markdown。
_PDF_EXTS = {".pdf"}
_DOC_EXTS = {".pdf", ".md", ".markdown", ".txt"}
ALLOWED_EXTS_BY_SOURCE = {
    SourceType.EXAM_PDF: _PDF_EXTS,
    SourceType.SLIDES_PDF: _PDF_EXTS,
    SourceType.DOCUMENT: _DOC_EXTS,
}

# MIME 白名單 (寬鬆): 瀏覽器常回 octet-stream 或空字串, 不能硬擋;
# 只擋「有給且明顯不是文件」的類型 (image/zip/executable…)。
_ALLOWED_CONTENT_TYPES = {
    "application/pdf", "application/x-pdf", "application/acrobat",
    "text/plain", "text/markdown", "text/x-markdown",
    "application/octet-stream", "",
}


def _validate_upload(filename: str, source_type: SourceType, content_type: str | None) -> None:
    """S-4: 副檔名 + MIME 白名單檢查。副檔名為強 gate, MIME 寬鬆輔助。"""
    ext = Path(filename).suffix.lower()
    allowed = ALLOWED_EXTS_BY_SOURCE[source_type]
    if ext not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"不接受的副檔名 {ext or '(無)'}; {source_type.value} 只收 {sorted(allowed)}",
        )
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct and ct not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"不接受的 MIME 類型: {ct}（只收 PDF / 純文字 / Markdown）",
        )


def _sanitize_filename(name: str) -> str:
    """清理上傳檔名 — 保留中文 / 英數 / 底線 / 橫線, 移除路徑字元跟 Windows 保留字。"""
    # S-4: 先做 Unicode NFC 正規化, 避免同形不同碼 / 組合字造成的檔名混淆。
    name = unicodedata.normalize("NFC", name).strip()
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



@router.post("", response_model=CreateJobResponse, status_code=status.HTTP_201_CREATED)
async def upload_and_create_job(
    request: Request,
    file: UploadFile = File(..., description="PDF / MD / TXT 檔案"),
    source_type: SourceType = Form(..., description="exam_pdf / slides_pdf / document"),
    options_json: str = Form(
        "{}",
        description="JobOptions 的 JSON 字串 (例: {\"mock\": true, \"require_review\": true})",
    ),
    project_id: str = Form(
        "", description="可選：歸屬的 Project（一課一工作空間）。空＝不歸屬，建全域 job",
    ),
    store: JobStore = Depends(get_default_store),
) -> CreateJobResponse:
    """收 multipart 檔案, 存到 pdfs/, 然後建 job 並排程。

    跟 /jobs POST 走完全一樣的流程, 差別只在 source.path 由 server 端決定
    (= 上傳後的儲存路徑), 不需要 caller 提供。

    project_id 有帶時把建好的 job 掛進該 Project.jobs[]（不存在的 pid 回 404，
    不靜默丟掉使用者選的歸屬）。
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

    # S-4: 副檔名 + MIME 白名單 (擋掉非文件類檔案)
    _validate_upload(file.filename, source_type, file.content_type)

    # 預檢 Content-Length: 避免明顯超大檔吃 await file.read() 把記憶體打滿
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            cl = int(content_length)
        except ValueError:
            cl = None
        if cl is not None and cl > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"檔案過大: {cl} bytes 超過上限 {MAX_UPLOAD_SIZE} bytes "
                f"({MAX_UPLOAD_SIZE // (1024 * 1024)} MB)",
            )

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
    # client 沒帶 Content-Length 或謊報時, read() 後再檢一次 (防呆)
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"檔案過大: {len(contents)} bytes 超過上限 {MAX_UPLOAD_SIZE} bytes "
            f"({MAX_UPLOAD_SIZE // (1024 * 1024)} MB)",
        )
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

    # 歸屬到 Project（一課一工作空間）：有帶 project_id 就掛進 project.jobs[]。
    if project_id:
        from core.project import ProjectNotFoundError
        from .projects import get_default_project_store
        try:
            get_default_project_store().add_job(project_id, rec.id)
        except ProjectNotFoundError as e:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {project_id}") from e

    return CreateJobResponse(
        job_id=rec.id,
        state=rec.state,
        status_url=f"/jobs/{rec.id}",
    )
