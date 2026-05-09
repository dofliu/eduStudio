"""/slide_images/{stem}/{filename} — 給 React UI 抓投影片 PNG 縮圖 (PR-3h)。

slide_ingest.py 把 PDF 渲染到 PROJECT_ROOT/slides/<stem>/p001.png 之後,
deck.json 的 slide.bg_image 會記成 "slides/<stem>/p001.png" (相對 PROJECT_ROOT)。

React 的 SlideEditor 把這個路徑拆成 stem + filename, 透過此端點抓圖。

安全性:
- stem / filename 都不允許 /, \\, .. (防 path traversal)
- 只服務 SLIDES_DIR 下的檔案, 解析後檢查 relative_to
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from core.config import SLIDES_DIR


router = APIRouter(prefix="/slide_images", tags=["slides"])


def _safe_part(part: str) -> bool:
    """禁止 path traversal / 絕對路徑碎片。"""
    return not (
        "/" in part or "\\" in part or ".." in part or part.startswith(".")
    )


@router.get("/{stem}/{filename}")
async def slide_image(stem: str, filename: str) -> FileResponse:
    if not _safe_part(stem) or not _safe_part(filename):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法 stem / filename")

    target = (SLIDES_DIR / stem / filename).resolve()
    # 二次防護: resolve 後仍要在 SLIDES_DIR 之下
    try:
        target.relative_to(SLIDES_DIR.resolve())
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "非法路徑")

    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"找不到圖片: {stem}/{filename}")

    return FileResponse(target, media_type="image/png")
