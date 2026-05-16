"""GET /themes/* — 主題預覽 endpoints (iter 72).

提供 thumbnail PNG 給 ThemeGalleryModal 顯示, 讓用戶從視覺挑主題不再靠
主題名稱猜. iter 58-71 累積 4 個 dispatch table (banner / title / font /
signature) + 8 個 layout 變體 + cover/outro 主題化 — 15 主題真的長不一樣,
這個 endpoint 把成果秀給用戶看.

設計:
- GET /themes        列所有 theme 名稱 + 中文 label
- GET /themes/preview/{theme}                 main slide thumbnail (300x169 蓋 1920x1080 縮)
- GET /themes/preview/{theme}/cover           cover thumbnail
- 結果 PNG 緩存 in-memory dict (server lifecycle 內 stable, restart 重算).
  15 主題 × 2 = 30 PNG, 各 ~50 KB → ~1.5 MB 記憶體 OK.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response


router = APIRouter(prefix="/themes", tags=["themes"])
logger = logging.getLogger(__name__)


# 跟 web ProposalsList THEME_APPLICABLE / Forest UI THEMES 一致
THEME_LIST: list[tuple[str, str]] = [
    # (id, 中文 label)
    ("forest", "Forest 森林教學"),
    ("navy", "Navy 海軍科技"),
    ("frieren", "Frieren 葬送的芙莉蓮"),
    ("naruto", "Naruto 火影"),
    ("journal", "Journal 期刊"),
    ("dof-editorial", "DOF Editorial 雜誌"),
    ("dof-podium", "DOF Podium 講壇"),
    ("dof-notebook", "DOF Notebook 札記"),
    ("dof-shinobi", "DOF Shinobi 忍者"),
    ("dof-elven", "DOF Elven 魔法"),
    ("dof-zine", "DOF Zine 海報"),
    ("dof-arcade", "DOF Arcade 像素"),
    ("dof-risograph", "DOF Risograph 油墨"),
    ("dof-supergraphic", "DOF Supergraphic 大色塊"),
    ("dof-brutalist", "DOF Brutalist 野獸派"),
]


# Cache: (theme, kind) → PNG bytes. server lifecycle 內 stable.
_PREVIEW_CACHE: dict[tuple[str, str], bytes] = {}

# Example bullets/title 寫 hard-code 一份, 給所有主題用同一份內容 — 視覺比較
# 才公平 (不會因為內容多寡 / 字數差異混淆觀感).
_EXAMPLE_BULLETS = [
    "重點 A: 簡單明瞭的條列說明",
    "重點 B: 第二個關鍵概念",
    "重點 C: 第三個延伸補充",
]
_EXAMPLE_TITLE = "範例: 材料力學概念"
_EXAMPLE_SECTION = "第 1 章 概念"
_EXAMPLE_COVER_TITLE = "範例教學主題"


def _render_preview(theme: str, kind: Literal["slide", "cover"]) -> bytes:
    """渲染指定主題 + kind 的 thumbnail, 回 PNG bytes.

    kind="slide": 一般 pptx_slide layout (title + bullets + section banner)
    kind="cover": 封面 layout (大字 + meta)
    """
    cache_key = (theme, kind)
    if cache_key in _PREVIEW_CACHE:
        return _PREVIEW_CACHE[cache_key]

    # lazy import 避免 server import 時牽動 PIL / fontTools
    import pipeline

    if kind == "slide":
        step = {
            "bg_type": "pptx_slide",
            "title": _EXAMPLE_TITLE,
            "section_title": _EXAMPLE_SECTION,
            "bullets": _EXAMPLE_BULLETS,
            "code_snippet": None, "code_lang": None,
            "file_path": None, "image_path": None,
            "narration": "preview",
        }
    elif kind == "cover":
        step = {
            "bg_type": "cover",
            "title": _EXAMPLE_COVER_TITLE,
            "cover_speaker": "劉瑞弘 副教授",
            "cover_org": "NCUT IAE · DofLab",
            "cover_date": "2026-05-16",
            "bullets": [], "code_snippet": None, "code_lang": None,
            "file_path": None, "image_path": None,
            "narration": "preview",
            "section_title": "",
        }
    else:
        raise ValueError(f"unknown kind {kind!r}")

    data = {"theme": theme, "steps": [step]}
    # tempfile 不適合 (回 bytes 就好) — 用 BytesIO + PIL save 繞過 file IO
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "preview.png"
        try:
            pipeline.render_frame(data, 1, out, Path(td))
        except Exception as e:
            logger.exception("theme preview render failed for %s/%s: %s",
                             theme, kind, e)
            raise HTTPException(500, f"render failed: {e}")
        # 縮放成 thumbnail (640×360 是 16:9 約三分之一原寸, 載入快但仍看得清楚)
        from PIL import Image
        img = Image.open(out).convert("RGB")
        thumb = img.resize((640, 360), Image.LANCZOS)
        buf = io.BytesIO()
        thumb.save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()

    _PREVIEW_CACHE[cache_key] = png_bytes
    return png_bytes


@router.get("")
def list_themes() -> dict:
    """列所有可選主題 + 中文 label. 給 frontend 建 gallery 用."""
    return {
        "themes": [
            {"id": tid, "label": label}
            for tid, label in THEME_LIST
        ],
    }


@router.get("/preview/{theme}")
def get_slide_preview(theme: str) -> Response:
    """回主題的 main slide thumbnail PNG."""
    if not any(t == theme for t, _ in THEME_LIST):
        raise HTTPException(404, f"unknown theme {theme!r}")
    png = _render_preview(theme, "slide")
    return Response(
        content=png, media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/preview/{theme}/cover")
def get_cover_preview(theme: str) -> Response:
    """回主題的封面 thumbnail PNG."""
    if not any(t == theme for t, _ in THEME_LIST):
        raise HTTPException(404, f"unknown theme {theme!r}")
    png = _render_preview(theme, "cover")
    return Response(
        content=png, media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )
