"""/slide_images/{stem}/{filename} — 給 React UI 抓投影片 PNG 縮圖 (PR-3h)。

slide_ingest.py 把 PDF 渲染到 PROJECT_ROOT/slides/<stem>/p001.png 之後,
deck.json 的 slide.bg_image 會記成 "slides/<stem>/p001.png" (相對 PROJECT_ROOT)。

React 的 SlideEditor 把這個路徑拆成 stem + filename, 透過此端點抓圖。

安全性:
- stem / filename 都不允許 /, \\, .. (防 path traversal)
- 只服務 SLIDES_DIR 下的檔案, 解析後檢查 relative_to
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from core.config import SLIDES_DIR

from ..path_safety import safe_join


router = APIRouter(prefix="/slide_images", tags=["slides"])


@router.get("/{stem}/{filename}")
async def slide_image(stem: str, filename: str) -> FileResponse:
    # 字元檢查 + resolve + 限定在 SLIDES_DIR 下 (S-3 共用 safe_join)
    target = safe_join(SLIDES_DIR, stem, filename)
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"找不到圖片: {stem}/{filename}")

    return FileResponse(target, media_type="image/png")
