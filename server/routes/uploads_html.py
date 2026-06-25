"""POST /upload/html — HTML 動畫網頁 → MP4, 接上既有 /library + YouTube 上傳。

定位
----
既有 /upload (uploads.py) 收 PDF/MD/TXT 走 deck/ingest pipeline。這個端點補上
另一條來源: 一支自含的 HTML 動畫 (或一個 http(s) URL) → 用 core.html_video 逐
frame 截圖渲成 MP4, 落在 job 的 artifacts/ 下。產出後跟其他影片一視同仁 —
/library 會列出它, server/routes/youtube.py 的「一鍵上傳」即可直接接手。

為什麼不走 run_job / deck pipeline
----------------------------------
HTML 動畫沒有 exam / deck schema 的概念 (沒有 problems / sections / narration),
ingest→review→render 那條流程不適用。這裡用獨立的背景 task 直接渲染:
PENDING → RENDERING → DONE/FAILED, 不經 awaiting_review。html_animation job 不
require_review (沒有 AI 產出的考題數字, 不觸及硬規則 #1)。

server 重啟若中斷渲染中的 job, JobStore.resume_interrupted() 會把 RENDERING 的
job 標 FAILED 讓使用者重試 (跟其他 track 一致), 不會誤呼叫 run_job。
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from ..jobs import JobStore, get_default_store
from ..ratelimit import rate_limit
from ..schemas import (
    CreateJobRequest,
    CreateJobResponse,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)
from .uploads import MAX_UPLOAD_SIZE, _sanitize_filename, _unique_target_path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/upload", tags=["uploads"])

# 合法 HTML 副檔名 (單一自含檔; 多檔 / 含外部 asset 的包裹本期不收, 走 URL 即可)
_HTML_EXTS = {".html", ".htm"}

# 安全上界: HTML 動畫沒有「結束」, 由 caller 指定錄多長; 設上限避免無意中錄超長
# 把磁碟 / CPU 吃滿 (frame 數 = duration * fps)。
_MAX_DURATION_S = 600.0      # 10 分鐘
_MAX_FPS = 60
_MAX_DIMENSION = 3840        # 4K 邊長上限


def _validate_dimensions(duration: float, fps: int, width: int, height: int) -> None:
    if not (0 < duration <= _MAX_DURATION_S):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"duration 必須介於 0 ~ {_MAX_DURATION_S:.0f} 秒, 收到 {duration}",
        )
    if not (0 < fps <= _MAX_FPS):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"fps 必須介於 1 ~ {_MAX_FPS}, 收到 {fps}",
        )
    for label, v in (("width", width), ("height", height)):
        if not (0 < v <= _MAX_DIMENSION):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{label} 必須介於 1 ~ {_MAX_DIMENSION}, 收到 {v}",
            )


async def _render_html_job(
    store: JobStore,
    job_id: str,
    *,
    source: str,
    mp4_path: Path,
    duration: float,
    fps: int,
    width: int,
    height: int,
    mock: bool,
) -> None:
    """背景 task: HTML → MP4, 寫進 artifacts/ 後 refresh + 標 DONE。

    任何例外都標 FAILED 寫進 state (不能讓 task crash 後 server 不知道), 對齊
    youtube._do_publish 的寬 catch 慣例。
    """
    store.update(job_id, state=JobState.RENDERING)
    try:
        from core.html_video import render_html_to_mp4

        await asyncio.to_thread(
            render_html_to_mp4,
            source, mp4_path,
            duration=duration, fps=fps, width=width, height=height, mock=mock,
        )
    except Exception as e:  # noqa: BLE001 — 一律落 FAILED, 細節進 error 欄
        logger.exception("html_animation render 失敗 (job=%s)", job_id)
        store.update(job_id, state=JobState.FAILED, error=f"HTML 轉影片失敗: {e}")
        return

    store.refresh_artifacts(job_id)
    store.update(job_id, state=JobState.DONE)
    logger.info("html_animation render 完成 (job=%s) → %s", job_id, mp4_path.name)


@router.post(
    "/html",
    response_model=CreateJobResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit)],
)
async def upload_html_animation(
    request: Request,
    file: UploadFile | None = File(None, description="自含的 .html 動畫檔 (與 url 二擇一)"),
    url: str = Form("", description="http(s):// 動畫網址 (與 file 二擇一)"),
    title: str = Form("", description="影片標題 / 輸出檔名 (預設用來源檔名或 'animation')"),
    duration: float = Form(..., description="要錄製的長度 (秒); HTML 動畫無自然結尾, 須指定"),
    fps: int = Form(30, description="影格率 (1~60, 預設 30)"),
    width: int = Form(1920, description="影片寬 (預設 1920)"),
    height: int = Form(1080, description="影片高 (預設 1080)"),
    options_json: str = Form("{}", description="JobOptions JSON (目前只用到 mock)"),
    project_id: str = Form("", description="可選: 歸屬的 Project; 空＝建全域 job"),
    store: JobStore = Depends(get_default_store),
) -> CreateJobResponse:
    """收一支 HTML 動畫 (檔案或 URL), 背景渲成 MP4, 接上既有上傳機制。

    回應與 /upload、/jobs POST 一致 (CreateJobResponse); 前端輪詢 status_url 即可
    看到 state 由 rendering → done, 完成後該 job 的 mp4 會出現在 /library。
    """
    has_file = file is not None and bool(file.filename)
    has_url = bool(url.strip())
    if has_file == has_url:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "file 與 url 必須二擇一 (剛好提供一個)",
        )

    _validate_dimensions(duration, fps, width, height)

    # options (目前只取 mock)
    try:
        opts_dict = json.loads(options_json) if options_json else {}
        if not isinstance(opts_dict, dict):
            raise ValueError("options_json 不是 JSON 物件")
    except Exception as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"options_json 解析失敗: {e}")
    # html_animation 一律不 require_review (無 AI 產出的考題數字)
    opts_dict.setdefault("require_review", False)
    options = JobOptions(**opts_dict)

    if has_url:
        scheme = urlparse(url.strip()).scheme
        if scheme not in ("http", "https"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "url 必須是 http:// 或 https://")
        source_value = url.strip()
        job_source = JobSource(url=source_value)
        default_stem = "animation"
    else:
        ext = Path(file.filename).suffix.lower()
        if ext not in _HTML_EXTS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"只接受 .html / .htm, 收到 {ext or '(無副檔名)'}",
            )
        # 先檢 Content-Length, 再 read 後複檢 (對齊 uploads.py 的雙重防呆)
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"檔案過大, 超過上限 {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
            )
        contents = await file.read()
        if not contents:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "上傳的 HTML 是空的")
        if len(contents) > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"檔案過大, 超過上限 {MAX_UPLOAD_SIZE // (1024 * 1024)} MB",
            )
        source_value = None  # 建 job 後才知道落地路徑
        job_source = JobSource()
        default_stem = Path(_sanitize_filename(file.filename)).stem or "animation"

    # 輸出檔名 stem: title 優先, 否則用來源
    stem = _sanitize_filename(title).strip() if title.strip() else default_stem
    stem = Path(stem).stem or "animation"

    # 建 job (不經 schedule_job; 自有背景 render task)
    rec = store.create(CreateJobRequest(
        source_type=SourceType.HTML_ANIMATION,
        source=job_source,
        options=options,
    ))

    # 檔案來源: 把 HTML 落地到 jobs/<id>/source/ 再回填 source.path
    if has_file:
        source_dir = store.job_dir(rec.id) / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_target_path(source_dir, _sanitize_filename(file.filename))
        target.write_bytes(contents)
        source_value = str(target.resolve())
        rec = store.update(rec.id, source=JobSource(path=source_value))

    # 歸屬 Project
    if project_id:
        from core.project import ProjectNotFoundError
        from .projects import get_default_project_store
        try:
            get_default_project_store().add_job(project_id, rec.id)
        except ProjectNotFoundError as e:
            store.delete(rec.id)
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"project 不存在: {project_id}") from e

    mp4_path = store.artifacts_dir(rec.id) / f"{stem}.mp4"
    asyncio.create_task(_render_html_job(
        store, rec.id,
        source=source_value, mp4_path=mp4_path,
        duration=duration, fps=fps, width=width, height=height,
        mock=bool(options.mock),
    ))

    return CreateJobResponse(job_id=rec.id, state=rec.state, status_url=f"/jobs/{rec.id}")
