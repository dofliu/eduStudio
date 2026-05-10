"""pptx 風格 Pillow renderer — 把 deck slide 畫成 1920x1080 PNG。

設計目標:
- 視覺風格沿用既有黑板系 (深底 + 高對比文字), 跟 BlackboardRenderer 一致
- Layout 模仿一般教學投影片: 章節 banner / slide title / bullets / code block
- 不依賴外部工具 (LibreOffice / Node) — 純 Pillow

主題 (PR-5a 引入):
- forest (預設): 深綠底 + 黃強調, 教學類用
- navy: 深海軍藍 + 青藍強調, 科技 / 程式碼類用
- 從 v0 單題 dict 的 data["theme"] 字串選色 (runner 端從 JobOptions.theme 帶過來)

Layout (1920x1080):
  y=0..70    章節 banner
  y=70..200  slide title 區 (大字 + 強調色底線)
  y=200..900 內容區 (bullets + 可選 code block)
  y=900..1080 字幕黑帶 (跟 BlackboardRenderer / SlideRenderer 同位置)

Step schema (由 deck_to_exam_schema_pptx 產生, 見 core.deck):
  {
    "bg_type": "pptx_slide",
    "section_title": "...",
    "title": "...",
    "bullets": ["..."],
    "code_snippet": null | "...",
    "code_lang": null | "python",
    "file_path": null | "core/foo.py",
    "narration": "...",
    "display": "..."  // legacy fallback, renderer 不用
  }
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TypedDict

from PIL import Image, ImageDraw, ImageFont

from core.config import (
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    get_fallback_font_path,
    get_font_path,
    get_mono_font_path,
)


# ---------- Theme (PR-5a) ----------
# 兩套色票都對齊「深底 + 高對比文字 + 強調色底線/marker」的視覺結構,
# 切主題只是換 hue, layout / 字級 / 邊距完全不變。

class Palette(TypedDict):
    bg: tuple[int, int, int]            # 主背景 (大面積)
    banner: tuple[int, int, int]        # 頂部章節 banner 背景 (略深)
    code_bg: tuple[int, int, int]       # 程式碼區塊背景
    code_border: tuple[int, int, int]   # 程式碼區塊邊框
    primary: tuple[int, int, int]       # 標題 / bullets 主色 (大字白系)
    highlight: tuple[int, int, int]     # 強調色 (黃 / 青) — 底線 + bullet marker
    secondary: tuple[int, int, int]     # banner 文字 / 次要色
    file_header: tuple[int, int, int]   # 程式碼區塊上方檔名 # filename


THEMES: dict[str, Palette] = {
    "forest": {
        # 沿用 PR-2b-ii 既有 Forest 色票, 跟黑板版同色保持風格延續
        "bg": (30, 58, 46),
        "banner": (20, 45, 35),
        "code_bg": (16, 36, 28),
        "code_border": (60, 90, 75),
        "primary": (232, 230, 216),
        "highlight": (255, 217, 107),       # 暖黃: 教學 / 重點
        "secondary": (180, 220, 200),
        "file_header": (255, 200, 140),     # 暖橘
    },
    "navy": {
        # 深海軍藍 + 青藍, 科技 / 程式碼專案用
        "bg": (24, 42, 80),
        "banner": (16, 28, 56),
        "code_bg": (14, 24, 50),
        "code_border": (60, 80, 130),
        "primary": (220, 232, 248),
        "highlight": (102, 200, 255),       # 青藍: 程式碼 / 工程
        "secondary": (170, 200, 240),
        "file_header": (255, 180, 120),     # 跟主色拉開的暖橘 (對比)
    },
}

DEFAULT_THEME = "forest"

# 底部字幕黑帶 (跟既有 renderer 一致, 不依主題)
SUBTITLE_STRIP = (0, 0, 0)


def get_palette(name: str | None) -> Palette:
    """容錯查 theme: 不認識的 name 退到 forest 並 print 警告。"""
    if not name or name not in THEMES:
        return THEMES[DEFAULT_THEME]
    return THEMES[name]


# ---------- 字級 ----------

BANNER_FONT_SIZE = 26     # 章節 banner
TITLE_FONT_SIZE = 64      # slide 主標題
BULLET_FONT_SIZE = 38     # bullets
CODE_FONT_SIZE = 26       # 程式碼字
FILE_HEADER_FONT_SIZE = 22 # 程式碼區塊上方 # filename


# ---------- 版面常數 ----------

BANNER_HEIGHT = 70
SUBTITLE_STRIP_HEIGHT = 180   # 底部字幕區 (跟既有 renderer 一致)
CONTENT_TOP = 90
CONTENT_BOTTOM = VIDEO_HEIGHT - SUBTITLE_STRIP_HEIGHT  # 900
SIDE_MARGIN = 100             # 左右留白


# ---------- 字型 cache ----------

@lru_cache(maxsize=None)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


@lru_cache(maxsize=None)
def _font_codepoints(path: str) -> frozenset[int]:
    """字型支援的 Unicode codepoint 集合, 用於 fallback 判斷。"""
    try:
        from fontTools.ttLib import TTCollection, TTFont
        if path.lower().endswith(".ttc"):
            return frozenset().union(
                *(f.getBestCmap().keys() for f in TTCollection(path).fonts)
            )
        return frozenset(TTFont(path).getBestCmap().keys())
    except Exception:
        return frozenset()


# ---------- 文字繪製 helper (主字型缺字自動 fallback) ----------

def _draw_text_mixed(draw, xy, text, main_font, fill, fb_font=None):
    """主字型缺字 (Σ ∮ ≤ 等) 用 fallback 補。回傳結束 x 座標。"""
    main_path = main_font.path if hasattr(main_font, "path") else get_font_path()
    fb_path = fb_font.path if (fb_font and hasattr(fb_font, "path")) else get_fallback_font_path()
    m_cps = _font_codepoints(main_path)
    f_cps = _font_codepoints(fb_path)
    if fb_font is None:
        fb_font = _font(get_fallback_font_path(), main_font.size)

    x, y = xy
    for ch in text:
        font = fb_font if (ord(ch) in f_cps and ord(ch) not in m_cps) else main_font
        draw.text((x, y), ch, font=font, fill=fill)
        x += int(font.getlength(ch))
    return x


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """簡單貪婪換行,中文 / 英文都能處理 (按字元逐個累積)。"""
    lines: list[str] = []
    for raw in text.split("\n"):
        buf = ""
        for ch in raw:
            if font.getlength(buf + ch) > max_w and buf:
                lines.append(buf)
                buf = ch
            else:
                buf += ch
        if buf:
            lines.append(buf)
    return lines


def _draw_text_wrapped(draw, xy, text, font, fill, max_w, line_h, fb_font=None) -> int:
    """wrap + 多行繪製, 回傳結束 y 座標。"""
    x, y = xy
    for ln in _wrap_text(text, font, max_w):
        _draw_text_mixed(draw, (x, y), ln, font, fill, fb_font=fb_font)
        y += line_h
    return y


# ---------- 元件繪製 (palette 是函式參數, 切主題只是換 palette) ----------

def _draw_banner(draw: ImageDraw.ImageDraw, section_title: str, palette: Palette) -> None:
    """頂部章節 banner: 略深背景 + 章節標題 + 底線。"""
    draw.rectangle([0, 0, VIDEO_WIDTH, BANNER_HEIGHT], fill=palette["banner"])
    draw.line(
        [(0, BANNER_HEIGHT), (VIDEO_WIDTH, BANNER_HEIGHT)],
        fill=palette["secondary"], width=2,
    )
    if section_title:
        font = _font(get_font_path(), BANNER_FONT_SIZE)
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, palette["secondary"],
        )


def _draw_title(draw: ImageDraw.ImageDraw, title: str, palette: Palette) -> int:
    """slide 主標題, 回傳結束 y 座標 (含底線)。"""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(get_font_path(), TITLE_FONT_SIZE)
    title_y = CONTENT_TOP + 30
    end_y = _draw_text_wrapped(
        draw, (SIDE_MARGIN, title_y), title, font, palette["primary"],
        max_w=VIDEO_WIDTH - SIDE_MARGIN * 2, line_h=TITLE_FONT_SIZE + 14,
    )
    underline_w = max(200, int(font.getlength(title.split("\n")[0])))
    underline_w = min(underline_w, VIDEO_WIDTH - SIDE_MARGIN * 2)
    underline_y = end_y + 8
    draw.line(
        [(SIDE_MARGIN, underline_y), (SIDE_MARGIN + underline_w, underline_y)],
        fill=palette["highlight"], width=5,
    )
    return underline_y + 30


def _draw_bullets(draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
                  y_max: int, palette: Palette) -> int:
    """畫 bullets 列表, 強調色 ▸ marker + 主色文字, 回傳結束 y。"""
    if not bullets:
        return y_start
    font = _font(get_font_path(), BULLET_FONT_SIZE)
    line_h = BULLET_FONT_SIZE + 16
    indent = 60
    text_max_w = VIDEO_WIDTH - SIDE_MARGIN * 2 - indent
    marker_font = _font(get_font_path(), BULLET_FONT_SIZE + 6)

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        _draw_text_mixed(
            draw, (SIDE_MARGIN + 18, y - 8), "•", marker_font, palette["highlight"],
        )
        end_y = _draw_text_wrapped(
            draw, (SIDE_MARGIN + indent, y), bullet, font, palette["primary"],
            max_w=text_max_w, line_h=line_h,
        )
        y = end_y + 12
        if y > y_max:
            if i < len(bullets) - 1:
                draw.text(
                    (SIDE_MARGIN + indent, y - 8), "...", font=font, fill=palette["primary"],
                )
            break
    return y


def _draw_code_block(draw: ImageDraw.ImageDraw, img: Image.Image,
                     code: str, file_path: str | None,
                     y_start: int, y_max: int, palette: Palette) -> int:
    """畫程式碼區塊: 上邊欄檔名 + bordered 等寬字內容。回傳結束 y。"""
    code = code.strip()
    if not code:
        return y_start

    file_font = _font(get_font_path(), FILE_HEADER_FONT_SIZE)
    code_font = _font(get_mono_font_path(), CODE_FONT_SIZE)
    line_h = CODE_FONT_SIZE + 8
    inner_pad = 16
    block_w = VIDEO_WIDTH - SIDE_MARGIN * 2

    code_lines = code.splitlines()
    header_h = (FILE_HEADER_FONT_SIZE + 16) if file_path else 0
    available_h = y_max - y_start - header_h - inner_pad * 2 - 16
    max_lines = max(1, available_h // line_h)
    if len(code_lines) > max_lines:
        code_lines = code_lines[:max_lines - 1] + ["    ..."]

    block_h = header_h + inner_pad * 2 + line_h * len(code_lines)
    block_top = y_start
    block_bottom = block_top + block_h

    draw.rectangle(
        [SIDE_MARGIN, block_top, SIDE_MARGIN + block_w, block_bottom],
        fill=palette["code_bg"], outline=palette["code_border"], width=2,
    )

    cur_y = block_top + 8
    if file_path:
        _draw_text_mixed(
            draw, (SIDE_MARGIN + inner_pad, cur_y),
            f"# {file_path}", file_font, palette["file_header"],
        )
        cur_y += FILE_HEADER_FONT_SIZE + 16
        draw.line(
            [(SIDE_MARGIN + inner_pad, cur_y - 6),
             (SIDE_MARGIN + block_w - inner_pad, cur_y - 6)],
            fill=palette["code_border"], width=1,
        )

    cur_y += inner_pad - 4
    for ln in code_lines:
        ln_text = ln
        max_w = block_w - inner_pad * 2
        while code_font.getlength(ln_text) > max_w and len(ln_text) > 4:
            ln_text = ln_text[:-2] + "…"
        draw.text(
            (SIDE_MARGIN + inner_pad, cur_y),
            ln_text, font=code_font, fill=palette["primary"],
        )
        cur_y += line_h

    return block_bottom + 16


def _draw_subtitle_strip(draw: ImageDraw.ImageDraw) -> None:
    """底部 180px 黑帶, 給 SRT 字幕用 (與既有 renderer 一致, 不隨主題變)。"""
    draw.rectangle(
        [0, VIDEO_HEIGHT - SUBTITLE_STRIP_HEIGHT, VIDEO_WIDTH, VIDEO_HEIGHT],
        fill=SUBTITLE_STRIP,
    )


# ---------- 公開 Renderer 類別 ----------

class PptxStyleRenderer:
    """deck slide → 1920x1080 PNG。

    從 v0 dict 的 data["theme"] 字串選色 (PR-5a). runner.py 會根據 JobOptions.theme
    把 theme 寫進 v0 dict, 預設 forest.
    """

    def render(self, data: dict, step_idx: int, out_p: Path, q_work: Path) -> None:
        # 防越界: 損毀 deck (step_idx 0 / 超過 steps 長度) 直接 raise 帶清楚訊息,
        # 不讓 IndexError 透到 server runner 變成模糊的 500
        steps = data.get("steps") or []
        if not steps:
            raise ValueError("deck data 沒有 steps, 無法 render")
        if step_idx < 1 or step_idx > len(steps):
            raise ValueError(
                f"step_idx={step_idx} 越界 (有效範圍 1..{len(steps)}), "
                f"deck 可能損毀或 caller 傳錯"
            )
        step = steps[step_idx - 1]
        palette = get_palette(data.get("theme"))

        img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), palette["bg"])
        draw = ImageDraw.Draw(img)

        section_title = step.get("section_title") or data.get("title", "")
        _draw_banner(draw, section_title, palette)

        title = step.get("title", "")
        title_end_y = _draw_title(draw, title, palette)

        content_y = title_end_y
        bullets = step.get("bullets") or []
        code = step.get("code_snippet") or ""
        file_path = step.get("file_path")

        content_y_max = CONTENT_BOTTOM - 24

        if code:
            estimated_code_h = min(
                360,
                max(120, len(code.splitlines()) * (CODE_FONT_SIZE + 8) + 80),
            )
            bullets_y_max = content_y_max - estimated_code_h - 20
            content_y = _draw_bullets(draw, bullets, content_y, bullets_y_max, palette)
            content_y = max(content_y, content_y_max - estimated_code_h)
            _draw_code_block(draw, img, code, file_path, content_y, content_y_max, palette)
        else:
            _draw_bullets(draw, bullets, content_y, content_y_max, palette)

        _draw_subtitle_strip(draw)
        try:
            from pipeline import _overlay_teacher_photo
            _overlay_teacher_photo(img)
        except Exception:
            pass

        img.save(out_p, "PNG")
