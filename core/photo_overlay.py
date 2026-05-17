"""老師頭像 overlay — 從 pipeline.py 抽出 (iter 35 技術債清理)。

純 Pillow 邏輯, 不依賴 pipeline.py 全局狀態。caller 傳 config dict +
畫面尺寸 + 邊框配色, 函式 in-place 修改 img。

設計筆記:
- caller 可預先讀 pipeline_config.json 自己快取, 或讓本 module 自己 lazy load
- dynamic_avatar (動態頭像) 跟靜態 teacher_photo 互斥, dynamic 啟用時這
  函式 noop
- 任何 PIL exception 都靜默 swallow (圖貼不上不該擋影片渲染整批)

iter 92 talking_head_override:
- runner 可用 context manager 暫時 force-skip 頭像 (短影片 / 用戶 off)
- 跟 video_dimensions_override 同 pattern, scope 結束自動 restore
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Literal

from PIL import Image, ImageDraw

from core.config import PIPELINE_CONFIG_PATH


_PIPELINE_CONFIG_CACHE: dict | None = None

# iter 92: runtime 強制覆寫 — runner 用 context manager 進來改, 出去復原
# None = 走 pipeline_config.json 預設, "off"/"always"/"long_form_only" = 覆寫
_RUNTIME_TALKING_HEAD_MODE: str | None = None
_RUNTIME_IS_SHORT_FORM: bool = False


@contextmanager
def talking_head_override(
    mode: Literal["always", "long_form_only", "off"] | None,
    *,
    is_short_form: bool = False,
) -> Iterator[None]:
    """iter 92: 暫時覆寫頭像顯示策略.

    mode:
      - "off": 不畫頭像
      - "always": 永遠畫 (即使短影片)
      - "long_form_only": 預設, 短影片 (is_short_form=True) 不畫, 其他都畫
      - None: 不覆寫, 走 pipeline_config.json 既有行為

    is_short_form: 短影片標記 (ultra_quick / aspect_ratio="9:16" /
                   short_video_layout 任一觸發). 只在 mode="long_form_only"
                   時才看. caller (runner) 自己判斷, 不在這推導.

    scope 結束自動 restore. 跟 video_dimensions_override 一致 pattern.
    """
    global _RUNTIME_TALKING_HEAD_MODE, _RUNTIME_IS_SHORT_FORM
    prev_mode = _RUNTIME_TALKING_HEAD_MODE
    prev_short = _RUNTIME_IS_SHORT_FORM
    _RUNTIME_TALKING_HEAD_MODE = mode
    _RUNTIME_IS_SHORT_FORM = bool(is_short_form)
    try:
        yield
    finally:
        _RUNTIME_TALKING_HEAD_MODE = prev_mode
        _RUNTIME_IS_SHORT_FORM = prev_short


def _should_skip_by_runtime_override() -> bool:
    """iter 92: 檢查 runtime override 是否要 skip 整個 overlay."""
    mode = _RUNTIME_TALKING_HEAD_MODE
    if mode is None:
        return False  # 沒覆寫, caller 繼續看 pipeline_config
    if mode == "off":
        return True
    if mode == "always":
        return False
    # "long_form_only": 短影片 skip, 長片 show
    return _RUNTIME_IS_SHORT_FORM


def load_pipeline_config() -> dict:
    """Lazy load pipeline_config.json, module-level cache (一次性).

    給 caller 不必每次自己讀檔. 若 caller 想主動傳 config dict 進來,
    overlay_teacher_photo 也支援。
    """
    global _PIPELINE_CONFIG_CACHE
    if _PIPELINE_CONFIG_CACHE is None:
        if PIPELINE_CONFIG_PATH.exists():
            _PIPELINE_CONFIG_CACHE = json.loads(
                PIPELINE_CONFIG_PATH.read_text(encoding="utf-8")
            )
        else:
            _PIPELINE_CONFIG_CACHE = {}
    return _PIPELINE_CONFIG_CACHE


def overlay_teacher_photo(
    img: Image.Image,
    *,
    config: dict | None = None,
    canvas_width: int = 1920,
    canvas_height: int = 1080,
    border_color: tuple[int, int, int] = (232, 230, 216),
) -> None:
    """把 teacher_photo 疊在 img 右下角 (in-place 修改 img).

    參數:
        img: PIL.Image (RGB / RGBA), 會被 in-place 改
        config: pipeline_config dict (None → 自己 lazy load PIPELINE_CONFIG_PATH)
        canvas_width: 影格寬 (預設 1920)
        canvas_height: 影格高 (預設 1080)
        border_color: 邊框配色 (預設 CHALK_WHITE = (232, 230, 216))

    行為:
        - iter 92: runtime override (talking_head_override) 命中 skip → return
        - config.dynamic_avatar.enabled=True → 直接 return (動態 avatar 流程
          會另外處理頭像, 兩模式互斥)
        - config.teacher_photo.enabled=False / 缺檔 / 路徑壞 → 直接 return
        - 任何 PIL exception → 靜默 swallow (圖貼不上不該擋整批渲染)
    """
    # iter 92: 先檢查 runtime override (runner 給的 user 偏好)
    if _should_skip_by_runtime_override():
        return
    cfg = config if config is not None else load_pipeline_config()
    if cfg.get("dynamic_avatar", {}).get("enabled"):
        return
    tp = cfg.get("teacher_photo", {})
    if not tp.get("enabled"):
        return
    path = Path(tp.get("path", ""))
    if not path.exists():
        return
    try:
        size = int(tp.get("size", 220))
        margin = int(tp.get("margin", 40))
        shape = tp.get("shape", "circle")
        bw = int(tp.get("border_width", 3))
        photo = Image.open(path).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        if shape == "circle":
            md.ellipse([0, 0, size, size], fill=255)
        else:
            md.rectangle([0, 0, size, size], fill=255)
        px = canvas_width - size - margin
        py = canvas_height - size - margin
        img.paste(photo, (px, py), mask=mask)
        if bw > 0:
            bd = ImageDraw.Draw(img)
            box = [px - bw, py - bw, px + size + bw, py + size + bw]
            if shape == "circle":
                bd.ellipse(box, outline=border_color, width=bw)
            else:
                bd.rectangle(box, outline=border_color, width=bw)
    except Exception:
        pass
