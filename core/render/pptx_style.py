"""Forest 主題 Pillow renderer — 把 deck slide 畫成 1920x1080 PNG。

設計目標:
- 視覺風格沿用既有黑板系 (深綠底 + 粉筆色階), 跟 BlackboardRenderer 一致
- Layout 模仿一般教學投影片: 章節 banner / slide title / bullets / code block
- 不依賴外部工具 (LibreOffice / Node) — 純 Pillow

Layout (1920x1080):
  y=0..70    章節 banner (深綠略深, 章節標題 + 分隔線)
  y=70..200  slide title 區 (粉筆白大字 + 黃色底線)
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

from PIL import Image, ImageDraw, ImageFont

from core.config import (
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    get_fallback_font_path,
    get_font_path,
    get_mono_font_path,
)


# ---------- Forest 色票 ----------

BG_DEEP_GREEN = (30, 58, 46)      # 主背景, 跟黑板版同色保持風格延續
BG_BANNER = (20, 45, 35)          # 章節 banner 略深
CODE_BG = (16, 36, 28)            # 程式碼區塊背景
CODE_BORDER = (60, 90, 75)
CHALK_WHITE = (232, 230, 216)     # 標題 / bullets 主色
CHALK_HIGHLIGHT = (255, 217, 107) # 黃色: 標題下底線 / bullet marker
CHALK_TITLE = (180, 220, 200)     # banner 文字
CHALK_FILE_HEADER = (255, 200, 140) # 程式碼區塊上方檔名 header
SUBTITLE_STRIP = (0, 0, 0)        # 底部字幕區黑帶 (跟 BlackboardRenderer 一致)


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
# 為什麼自己 lru_cache 而不是 import pipeline._get_font:
# - 避免循環 import (pipeline.py 註冊 renderer 時會 import 這個模組)
# - 字型 cache 是純函式無狀態, 各模組各自 cache 沒成本

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


# ---------- 元件繪製 ----------

def _draw_banner(draw: ImageDraw.ImageDraw, section_title: str) -> None:
    """頂部章節 banner: 略深背景 + 章節標題 + 底線。"""
    draw.rectangle([0, 0, VIDEO_WIDTH, BANNER_HEIGHT], fill=BG_BANNER)
    draw.line(
        [(0, BANNER_HEIGHT), (VIDEO_WIDTH, BANNER_HEIGHT)],
        fill=CHALK_TITLE, width=2,
    )
    if section_title:
        font = _font(get_font_path(), BANNER_FONT_SIZE)
        # 垂直居中: banner 高 70, 字 26, 大約 y=22
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, CHALK_TITLE,
        )


def _draw_title(draw: ImageDraw.ImageDraw, title: str) -> int:
    """slide 主標題, 回傳結束 y 座標 (含底線)。"""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(get_font_path(), TITLE_FONT_SIZE)
    title_y = CONTENT_TOP + 30
    end_y = _draw_text_wrapped(
        draw, (SIDE_MARGIN, title_y), title, font, CHALK_WHITE,
        max_w=VIDEO_WIDTH - SIDE_MARGIN * 2, line_h=TITLE_FONT_SIZE + 14,
    )
    # 黃色底線寬度配合標題實際長度 (但限制最少 200px)
    underline_w = max(200, int(font.getlength(title.split("\n")[0])))
    underline_w = min(underline_w, VIDEO_WIDTH - SIDE_MARGIN * 2)
    underline_y = end_y + 8
    draw.line(
        [(SIDE_MARGIN, underline_y), (SIDE_MARGIN + underline_w, underline_y)],
        fill=CHALK_HIGHLIGHT, width=5,
    )
    return underline_y + 30


def _draw_bullets(draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
                  y_max: int) -> int:
    """畫 bullets 列表, 黃色 ▸ marker + 白色文字, 回傳結束 y。

    超過 y_max 時自動截斷 (留省略號) — 避免畫出去頂到字幕區。
    """
    if not bullets:
        return y_start
    font = _font(get_font_path(), BULLET_FONT_SIZE)
    line_h = BULLET_FONT_SIZE + 16
    indent = 60
    text_max_w = VIDEO_WIDTH - SIDE_MARGIN * 2 - indent

    # marker 用較大字級的「•」(U+2022), 微軟正黑體有這個 glyph;
    # 走 _draw_text_mixed 是為了真的缺字時也能 fallback (例如未來換主字型)
    marker_font = _font(get_font_path(), BULLET_FONT_SIZE + 6)

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        _draw_text_mixed(
            draw, (SIDE_MARGIN + 18, y - 8), "•", marker_font, CHALK_HIGHLIGHT,
        )
        end_y = _draw_text_wrapped(
            draw, (SIDE_MARGIN + indent, y), bullet, font, CHALK_WHITE,
            max_w=text_max_w, line_h=line_h,
        )
        y = end_y + 12
        if y > y_max:
            if i < len(bullets) - 1:
                draw.text(
                    (SIDE_MARGIN + indent, y - 8), "...", font=font, fill=CHALK_WHITE,
                )
            break
    return y


def _draw_code_block(draw: ImageDraw.ImageDraw, img: Image.Image,
                     code: str, file_path: str | None,
                     y_start: int, y_max: int) -> int:
    """畫程式碼區塊: 上邊欄檔名 + bordered 等寬字內容。回傳結束 y。"""
    code = code.strip()
    if not code:
        return y_start

    file_font = _font(get_font_path(), FILE_HEADER_FONT_SIZE)
    code_font = _font(get_mono_font_path(), CODE_FONT_SIZE)
    line_h = CODE_FONT_SIZE + 8
    inner_pad = 16
    block_w = VIDEO_WIDTH - SIDE_MARGIN * 2

    # 計算實際要顯示的行數: 限制在 y_max 內
    code_lines = code.splitlines()
    header_h = (FILE_HEADER_FONT_SIZE + 16) if file_path else 0
    available_h = y_max - y_start - header_h - inner_pad * 2 - 16
    max_lines = max(1, available_h // line_h)
    if len(code_lines) > max_lines:
        code_lines = code_lines[:max_lines - 1] + ["    ..."]

    block_h = header_h + inner_pad * 2 + line_h * len(code_lines)
    block_top = y_start
    block_bottom = block_top + block_h

    # 背景 + 邊框
    draw.rectangle(
        [SIDE_MARGIN, block_top, SIDE_MARGIN + block_w, block_bottom],
        fill=CODE_BG, outline=CODE_BORDER, width=2,
    )

    # 檔名 header
    cur_y = block_top + 8
    if file_path:
        _draw_text_mixed(
            draw, (SIDE_MARGIN + inner_pad, cur_y),
            f"# {file_path}", file_font, CHALK_FILE_HEADER,
        )
        cur_y += FILE_HEADER_FONT_SIZE + 16
        # 檔名底下分隔線
        draw.line(
            [(SIDE_MARGIN + inner_pad, cur_y - 6),
             (SIDE_MARGIN + block_w - inner_pad, cur_y - 6)],
            fill=CODE_BORDER, width=1,
        )

    cur_y += inner_pad - 4
    # 程式碼本體 (等寬字, 不 wrap, 過長就截斷單行)
    for ln in code_lines:
        # 防止單行超出 — 若超出 block_w 就 truncate
        ln_text = ln
        max_w = block_w - inner_pad * 2
        while code_font.getlength(ln_text) > max_w and len(ln_text) > 4:
            ln_text = ln_text[:-2] + "…"
        draw.text(
            (SIDE_MARGIN + inner_pad, cur_y),
            ln_text, font=code_font, fill=CHALK_WHITE,
        )
        cur_y += line_h

    return block_bottom + 16


def _draw_subtitle_strip(draw: ImageDraw.ImageDraw) -> None:
    """底部 180px 黑帶, 給 SRT 字幕用 (與既有 renderer 一致)。"""
    draw.rectangle(
        [0, VIDEO_HEIGHT - SUBTITLE_STRIP_HEIGHT, VIDEO_WIDTH, VIDEO_HEIGHT],
        fill=SUBTITLE_STRIP,
    )


# ---------- 公開 Renderer 類別 ----------

class PptxStyleRenderer:
    """deck slide → 1920x1080 PNG (Forest 主題)。

    實作 pipeline.Renderer 的 render(data, step_idx, out_p, q_work) 介面,
    所以可以直接註冊到 pipeline._RENDERERS["pptx_slide"]。
    """

    def render(self, data: dict, step_idx: int, out_p: Path, q_work: Path) -> None:
        step = data["steps"][step_idx - 1]

        img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_DEEP_GREEN)
        draw = ImageDraw.Draw(img)

        # 章節 banner (取 step.section_title, 或 fallback 到 data.title)
        section_title = step.get("section_title") or data.get("title", "")
        _draw_banner(draw, section_title)

        # slide 主標題
        title = step.get("title", "")
        title_end_y = _draw_title(draw, title)

        # 內容區: bullets 與 code 共享垂直空間
        content_y = title_end_y
        bullets = step.get("bullets") or []
        code = step.get("code_snippet") or ""
        file_path = step.get("file_path")

        # 預留底部黑帶上方 24px buffer
        content_y_max = CONTENT_BOTTOM - 24

        # bullets 先畫上半, code 在下半 (若有 code 限制 bullets 高度)
        if code:
            # 簡單分配: code 區塊估計需要 (lines * 34 + 80)px, 但封頂在 360px
            estimated_code_h = min(
                360,
                max(120, len(code.splitlines()) * (CODE_FONT_SIZE + 8) + 80),
            )
            bullets_y_max = content_y_max - estimated_code_h - 20
            content_y = _draw_bullets(draw, bullets, content_y, bullets_y_max)
            content_y = max(content_y, content_y_max - estimated_code_h)
            _draw_code_block(draw, img, code, file_path, content_y, content_y_max)
        else:
            # 沒 code: bullets 吃滿
            _draw_bullets(draw, bullets, content_y, content_y_max)

        # 底部字幕黑帶 + teacher photo overlay
        _draw_subtitle_strip(draw)
        try:
            from pipeline import _overlay_teacher_photo
            _overlay_teacher_photo(img)
        except Exception:
            # PR-2b-ii 引入時 pipeline.py 還沒載入也不應掛掉
            pass

        img.save(out_p, "PNG")
