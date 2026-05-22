"""E2-5 icon overlay — slide 渲染時 PIL 疊 icon (跟 photo_overlay.py 同 pattern).

對應 docs/dynamic-visual-assets-design.md E2 候選 A (keyword grep MVP).
schema 欄位 (E2-4 已落地): step.icon_overlay = list[dict] | None, 每筆含:
    - path: str — 絕對 / 相對 caller 已 resolve
    - position: str — top-left | top-right | bottom-left | bottom-right | center
    - size_ratio: float — icon 寬佔 canvas_w 比例 (0.08~0.20 推薦)
    - start_ms / duration_ms: 暫未處理 (留給多 frame 序列接 E1-2)

設計原則:
- 跟 core/photo_overlay.py 同 pattern: 純 Pillow, 任何 PIL exception 靜默 swallow.
  圖貼不上不該擋影片渲染整批.
- SVG 暫不支援 — repo 沒 cairosvg dep (見 docs/dynamic-visual-assets-design.md
  「不新增 pip 必要依賴」硬規則). 三種行為:
    1. path 是 .svg 但同層級有同名 .png → 用 .png (E2-2 Gemini 產 SVG 時若
       順手 render PNG 就直接吃)
    2. path 是 .svg 且無 .png fallback → graceful skip (warning 不噴, 不擋
       其他 icon)
    3. path 是 .png / .jpg / 任何 PIL 可開 → 正常 composite
- caller 該傳 canvas_h = 字幕帶之上的可視高 (不是整 1080), 避免 icon 被字幕蓋.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image


_VALID_POSITIONS = ("top-left", "top-right", "bottom-left", "bottom-right", "center")
_DEFAULT_POSITION = "top-right"


def _resolve_position(
    position: str,
    icon_w: int,
    icon_h: int,
    canvas_w: int,
    canvas_h: int,
    margin: int,
) -> tuple[int, int]:
    """根據 position 字串算 icon 左上角 (px, py).

    canvas_h 該由 caller 預先扣字幕帶 (例 _render_full 傳 visible_h=900),
    bottom-* position 才不會壓到字幕區.
    """
    if position == "top-left":
        return margin, margin
    if position == "top-right":
        return canvas_w - icon_w - margin, margin
    if position == "bottom-left":
        return margin, canvas_h - icon_h - margin
    if position == "bottom-right":
        return canvas_w - icon_w - margin, canvas_h - icon_h - margin
    if position == "center":
        return (canvas_w - icon_w) // 2, (canvas_h - icon_h) // 2
    # 不該到這 — _VALID_POSITIONS 已 caller filter 過, defensive 退到 top-right
    return canvas_w - icon_w - margin, margin


def _load_icon(path: Path) -> Image.Image | None:
    """讀 icon 檔, 回 RGBA PIL Image. 缺檔 / SVG (無 cairosvg) → None.

    SVG fallback 規則:
    - .svg 不存在 → 試同名 .png (E2-2 產時 commit 兩種格式可走) → 不存在 None
    - .svg 存在但 repo 無 cairosvg → 試同名 .png → 不存在 None
    - 未來進 cairosvg dep 後改這支函式就行, 上游 compose_icons 不用動
    """
    if not path.exists():
        if path.suffix.lower() == ".svg":
            png_alt = path.with_suffix(".png")
            if png_alt.exists():
                try:
                    return Image.open(png_alt).convert("RGBA")
                except Exception:
                    return None
        return None
    if path.suffix.lower() == ".svg":
        png_alt = path.with_suffix(".png")
        if png_alt.exists():
            try:
                return Image.open(png_alt).convert("RGBA")
            except Exception:
                return None
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception:
        return None


def compose_icons(
    img: Image.Image,
    icons: list[dict] | None,
    *,
    canvas_w: int = 1920,
    canvas_h: int = 1080,
    margin: int = 40,
) -> None:
    """把 icon list 疊到 img 上 (in-place 修改).

    Args:
        img: PIL.Image RGB / RGBA, 會被 in-place 改
        icons: schema E2-4 的 icon_overlay 欄位. None / [] / 非 list → noop
        canvas_w / canvas_h: 影格寬高 (預設 1920×1080). caller 該傳「字幕帶
            之上」可視高給 canvas_h, 不是整 1080
        margin: icon 邊距 (預設 40, 跟 teacher_photo 同)

    單筆 icon 失敗 (path 壞 / SVG 無 PNG fallback / size 計算炸) 靜默 skip,
    不擋其他 icon, 不擋影片渲染整批.
    """
    if not isinstance(icons, list) or not icons:
        return
    for entry in icons:
        if not isinstance(entry, dict):
            continue
        path_str = entry.get("path")
        if not path_str:
            continue
        try:
            icon = _load_icon(Path(path_str))
            if icon is None:
                continue
            size_ratio = float(entry.get("size_ratio", 0.10))
            # clamp: 太小看不到, 太大蓋掉內容 (icon 寬度上限 50% canvas)
            size_ratio = max(0.02, min(0.50, size_ratio))
            target_w = max(1, int(canvas_w * size_ratio))
            ratio = target_w / max(1, icon.width)
            target_h = max(1, int(icon.height * ratio))
            icon = icon.resize((target_w, target_h), Image.LANCZOS)
            position = entry.get("position") or _DEFAULT_POSITION
            if position not in _VALID_POSITIONS:
                position = _DEFAULT_POSITION
            px, py = _resolve_position(
                position, target_w, target_h, canvas_w, canvas_h, margin,
            )
            # paste with alpha mask (icon 已是 RGBA)
            img.paste(icon, (px, py), mask=icon)
        except Exception:
            continue
