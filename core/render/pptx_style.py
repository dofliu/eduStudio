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
from core.visuals import (
    CONTENT_BOTTOM,
    SUBTITLE_BAND_HEIGHT,
    SUBTITLE_STRIP_COLOR,
)


# ---------- Theme (PR-5a / iter 58) ----------
# 色票 + iter 58 加入的 banner_style 開始有 layout 差異.

# iter 58 banner 樣式 (四種):
#   "rectangle" (default): 填滿矩形 + 底線 + 文字 — 多數深底主題
#   "hairline":            無填色, 上下兩條細線, 文字躺在 bg 上 — 淺底極簡 (editorial / journal / notebook / elven)
#   "reverse":             深色填滿 + 強對比文字 — 衝擊家族 (brutalist / supergraphic / zine)
#   "neon":                填滿 + 內側螢光細邊 — 霓虹主題 (arcade)
BannerStyle = str  # Literal["rectangle", "hairline", "reverse", "neon"]


class Palette(TypedDict):
    bg: tuple[int, int, int]            # 主背景 (大面積)
    banner: tuple[int, int, int]        # 頂部章節 banner 背景 (略深)
    code_bg: tuple[int, int, int]       # 程式碼區塊背景
    code_border: tuple[int, int, int]   # 程式碼區塊邊框
    primary: tuple[int, int, int]       # 標題 / bullets 主色 (大字白系)
    highlight: tuple[int, int, int]     # 強調色 (黃 / 青) — 底線 + bullet marker
    secondary: tuple[int, int, int]     # banner 文字 / 次要色
    file_header: tuple[int, int, int]   # 程式碼區塊上方檔名 # filename


# iter 58: theme → banner style 對應, 沒列在裡面的 fallback 到 "rectangle"
# 沒寫在 Palette TypedDict 內 (TypedDict 用 NotRequired 可選欄位 + Python 3.11+
# 才有, 為了相容性放外面 mapping)
THEME_BANNER_STYLES: dict[str, str] = {
    "forest": "rectangle",        # 深綠教學, 經典
    "navy": "rectangle",          # 深藍科技, 經典
    "frieren": "rectangle",       # 藏青漫畫
    "naruto": "rectangle",        # 焦糖漫畫
    "journal": "hairline",        # 期刊細線
    # v1 沉穩家族 - 多數走 hairline (極簡 / 學者氣質)
    "dof-editorial": "hairline",  # 雜誌編輯 - 髮絲線分隔
    "dof-podium": "hairline",     # 講壇 TED - 極簡
    "dof-notebook": "hairline",   # 札記 - 紙感
    "dof-shinobi": "rectangle",   # 忍者深底 - 需 solid 填色
    "dof-elven": "hairline",      # 魔法幻境 - 細緻
    # v2 衝擊家族
    "dof-zine": "reverse",        # 海報撞色
    "dof-arcade": "neon",         # 霓虹發光
    "dof-risograph": "rectangle", # 油墨疊印
    "dof-supergraphic": "reverse",# Pentagram 大色塊
    "dof-brutalist": "reverse",   # 野獸派反白
}


def get_banner_style(theme_name: str | None) -> str:
    """容錯查 banner style, 沒列就回 'rectangle' (現行預設行為)."""
    if not theme_name:
        return "rectangle"
    return THEME_BANNER_STYLES.get(theme_name, "rectangle")


# iter 59 title 樣式 (四種):
#   "underline" (default): 標題下方 highlight 色橫線, 寬 5 (現行)
#   "block":               標題前面一個 highlight 色方塊 prefix (像章節符號)
#   "hairline":            標題上方一條 hairline (1px), 比 underline 細, 學術感
#   "reverse":             標題包進 highlight 色塊內 + bg 色文字 (海報式標籤)
TitleDecor = str  # Literal["underline", "block", "hairline", "reverse"]

THEME_TITLE_DECORS: dict[str, str] = {
    # 經典 — underline
    "forest": "underline",
    "navy": "underline",
    "frieren": "underline",
    "naruto": "underline",
    "journal": "hairline",         # 學術細線
    # v1 沉穩家族
    "dof-editorial": "block",      # 雜誌風: § 符號感
    "dof-podium": "hairline",      # 講壇 TED 極簡
    "dof-notebook": "hairline",    # 札記細線
    "dof-shinobi": "block",        # 朱印章式色塊
    "dof-elven": "hairline",       # 月光細緻
    # v2 衝擊家族
    "dof-zine": "reverse",         # 海報標籤
    "dof-arcade": "underline",     # banner 已用 neon, title 維持經典
    "dof-risograph": "block",      # 油墨塊感
    "dof-supergraphic": "reverse", # 大色塊
    "dof-brutalist": "reverse",    # 反白色塊
}


def get_title_decor(theme_name: str | None) -> str:
    """容錯查 title decor style, 沒列就回 'underline' (現行預設行為)."""
    if not theme_name:
        return "underline"
    return THEME_TITLE_DECORS.get(theme_name, "underline")


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
    "frieren": {
        # 葬送的芙莉蓮 — 藏青夜空 + 銀白頭髮 + 淡紫魔法粒子. 冷色靜謐, 適合
        # 理論探索 / 學術研究 / 文學性主題 (iter 28 從 pptx-jliu-style 移植).
        "bg": (26, 31, 58),                 # 藏青夜空
        "banner": (14, 18, 38),             # 更深的夜
        "code_bg": (20, 24, 44),
        "code_border": (74, 68, 128),       # 紫粉氛圍
        "primary": (232, 234, 240),         # 銀白
        "highlight": (184, 160, 224),       # 淡紫魔法
        "secondary": (139, 154, 200),       # 月光藍
        "file_header": (212, 184, 106),     # 淡金
    },
    "naruto": {
        # 火影忍者 — 焦糖 + 火影橘 + 紅雲. 熱血暖色, 適合實作專題 / 競賽 /
        # 團隊合作主題 (iter 28 從 pptx-jliu-style 移植).
        "bg": (46, 26, 15),                 # 深焦糖
        "banner": (26, 15, 8),              # 黑邊
        "code_bg": (32, 20, 10),
        "code_border": (139, 58, 46),       # 紅雲
        "primary": (245, 237, 216),         # 暖白 (老紙感)
        "highlight": (255, 140, 66),        # 火影橘
        "secondary": (212, 184, 106),       # 卷軸色
        "file_header": (230, 74, 60),       # 紅雲
    },
    "journal": {
        # 米白墨綠期刊風 / 學術襯線書冊風 — ⚠ 唯一「淺底」主題, 適合學術課程
        # 研究所 / 正式出版風 (iter 28 從 pptx-jliu-style 移植).
        # 若深淺主題切換時視覺差異太大可考慮另開「淺底」family。
        "bg": (245, 241, 230),              # 米白紙感
        "banner": (232, 226, 210),          # 略深米色
        "code_bg": (236, 230, 214),         # 老紙
        "code_border": (46, 74, 53),        # 墨綠
        "primary": (42, 31, 24),            # 黑棕墨 (印刷感)
        "highlight": (139, 58, 46),         # 暗紅 (重點 / 標籤色)
        "secondary": (46, 74, 53),          # 墨綠
        "file_header": (139, 58, 46),       # 暗紅
    },

    # ---------- iter 44: dof-* 系列 (10 套, 從 docs/pptx-jliu-style 移植) ----------
    # 完整 design spec 在 docs/pptx-jliu-style/dof-*.md (有頁型 / 字體 / 母片).
    # 這裡只取色票 (本 renderer 用 Palette 8 token), pptx-jliu-style skill
    # 才會用到完整 layout spec.

    # === v1 沉穩家族 (全襯線 / 極簡 / 學者氣質) ===

    "dof-editorial": {
        # 雜誌編輯風 · 暖色全襯線 · 業界演講 / Demo Day / 對外分享
        "bg": (244, 238, 227),              # 紙底 F4EEE3
        "banner": (232, 225, 210),          # 略深紙
        "code_bg": (236, 230, 214),         # 老紙
        "code_border": (201, 188, 163),     # 髮絲線 C9BCA3
        "primary": (30, 26, 20),            # 墨 1E1A14
        "highlight": (178, 85, 48),         # 赭橘 B25530
        "secondary": (138, 124, 101),       # 灰調 8A7C65
        "file_header": (201, 163, 91),      # 米金 C9A35B
    },
    "dof-podium": {
        # 講壇風 / TED 感 · 冷灰 · Conference / Keynote / 研究發表
        "bg": (238, 237, 233),              # 紙底 EEEDE9
        "banner": (220, 219, 213),          # 略深紙
        "code_bg": (216, 215, 208),
        "code_border": (207, 207, 201),     # 髮絲線 CFCFC9
        "primary": (24, 25, 28),            # 墨 18191C
        "highlight": (90, 107, 122),        # 霧藍石板 5A6B7A
        "secondary": (139, 143, 149),       # 次文灰 8B8F95
        "file_header": (184, 176, 164),     # 麻灰 B8B0A4
    },
    "dof-notebook": {
        # 札記風 / 讀書會 · 霧暖 · Journal Club / 思考筆記
        "bg": (241, 236, 227),              # 米黃紙底 F1ECE3
        "banner": (224, 218, 205),
        "code_bg": (220, 213, 199),
        "code_border": (214, 207, 193),     # 髮絲 D6CFC1
        "primary": (42, 37, 32),            # 墨 2A2520
        "highlight": (110, 126, 98),        # 苔綠 6E7E62 (眉批色)
        "secondary": (156, 148, 138),       # 次文灰褐 9C948A
        "file_header": (184, 154, 146),     # 粉藕 B89A92
    },
    "dof-shinobi": {
        # 忍者熱血 · 深夜墨 + 朱印紅 · 黑客松 / 動員會
        "bg": (22, 17, 10),                 # 墨夜 16110A (深底淺字, 跟其他 v1 反相)
        "banner": (10, 7, 4),               # 更深夜
        "code_bg": (16, 12, 8),
        "code_border": (58, 48, 36),        # 髮絲 3A3024
        "primary": (242, 229, 200),         # 紙黃前景 F2E5C8
        "highlight": (199, 58, 29),         # 朱印紅 C73A1D
        "secondary": (138, 125, 94),        # 暗黃褐 8A7D5E
        "file_header": (232, 144, 48),      # 焰橘 E89030
    },
    "dof-elven": {
        # 魔法幻境 · 月光紫 + 燙金 · 哲學 / 認知科學 / 文學主題
        "bg": (242, 238, 245),              # 月光紙底 F2EEF5 (極淡紫, 不純白)
        "banner": (226, 222, 230),
        "code_bg": (222, 217, 226),
        "code_border": (216, 210, 222),     # 髮絲 D8D2DE
        "primary": (31, 27, 46),            # 墨紫 1F1B2E
        "highlight": (124, 111, 160),       # 月光紫 7C6FA0
        "secondary": (144, 137, 164),       # 淡紫灰 9089A4
        "file_header": (184, 154, 92),      # 燙金 B89A5C
    },

    # === v2 衝擊家族 (粗 sans / 撞色 / 玩心或立場) ===

    "dof-zine": {
        # 獨立雜誌海報 · 螢光黃 + 撞色紅 · 年度回顧 / 宣言式 talk
        "bg": (250, 250, 245),              # 紙白 FAFAF5
        "banner": (240, 240, 232),
        "code_bg": (235, 235, 225),
        "code_border": (218, 218, 210),
        "primary": (10, 10, 10),            # 黑墨 0A0A0A
        "highlight": (230, 57, 70),         # 撞色紅 E63946
        "secondary": (119, 112, 103),       # 灰調 777067
        "file_header": (29, 78, 216),       # 撞色藍 1D4ED8 (跟紅互補)
    },
    "dof-arcade": {
        # 街機霓虹 8-bit · 深夜底 + 霓虹 · 黑客松開幕 / Tech demo
        "bg": (10, 14, 39),                 # 深夜底 0A0E27
        "banner": (22, 27, 64),             # 深夜底-2 161B40
        "code_bg": (8, 12, 32),
        "code_border": (0, 240, 255),       # 霓虹青 00F0FF (做亮邊框)
        "primary": (245, 245, 240),         # 紙白前景 F5F5F0
        "highlight": (0, 240, 255),         # 霓虹青 (主標題 / 玩家友善)
        "secondary": (255, 184, 0),         # 警報橘黃 FFB800 (HUD / 數值)
        "file_header": (255, 0, 110),       # 霓虹洋紅 FF006E (系統訊息)
    },
    "dof-risograph": {
        # Riso 兩色疊印 · 油墨藍 + 螢光粉 · 工作坊 / 跨界活動
        "bg": (247, 242, 229),              # 米紙 F7F2E5
        "banner": (236, 231, 218),
        "code_bg": (230, 225, 212),
        "code_border": (14, 91, 168),       # Federal Blue 0E5BA8
        "primary": (26, 24, 18),            # 油墨黑 1A1812
        "highlight": (255, 72, 176),        # 螢光粉 FF48B0
        "secondary": (131, 120, 101),       # 灰調 837865
        "file_header": (14, 91, 168),       # Federal Blue
    },
    "dof-supergraphic": {
        # Pentagram 大色塊瑞士幾何 · 三原色 + 黑白 · 品牌簡介 / 企業合作
        "bg": (255, 255, 255),              # 純白
        "banner": (230, 57, 70),            # 撞色紅當大色塊 banner
        "code_bg": (10, 10, 10),            # 純黑 code 區塊 (反白文字)
        "code_border": (0, 0, 0),           # 純黑 4pt 分隔線
        "primary": (0, 0, 0),               # 純黑大字
        "highlight": (230, 57, 70),         # 撞色紅 E63946 (單一強調)
        "secondary": (255, 255, 255),       # 白 (banner 上的標題文字)
        "file_header": (255, 214, 10),      # 撞色黃 FFD60A
    },
    "dof-brutalist": {
        # 野獸派宣言 · 黑白 + 警示橘紅 · 觀點 talk / 批判演講
        "bg": (244, 244, 240),              # 紙白 F4F4F0
        "banner": (10, 10, 10),             # 純黑 banner (極端對比)
        "code_bg": (10, 10, 10),            # 純黑 code 區
        "code_border": (255, 61, 0),        # 警示橘紅 FF3D00
        "primary": (10, 10, 10),            # 純黑大字
        "highlight": (255, 61, 0),          # 警示橘紅 (call to action)
        "secondary": (196, 255, 0),         # 螢光綠 C4FF00 (banner 上的章節名)
        "file_header": (196, 255, 0),       # 螢光綠
    },
}

DEFAULT_THEME = "forest"

# 底部字幕黑帶 — 跨 renderer 共用, 從 core.visuals 集中載入 (Round 2 lessons-learned #3)
SUBTITLE_STRIP = SUBTITLE_STRIP_COLOR


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
SUBTITLE_STRIP_HEIGHT = SUBTITLE_BAND_HEIGHT   # 別名, 對齊 core.visuals 集中版
CONTENT_TOP = 90
# CONTENT_BOTTOM 由 core.visuals 提供, 值 = VIDEO_HEIGHT - SUBTITLE_BAND_HEIGHT (900)
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

def _draw_banner(
    draw: ImageDraw.ImageDraw, section_title: str, palette: Palette,
    style: str = "rectangle",
) -> None:
    """頂部章節 banner — iter 58 加 4 種 style dispatch.

    style:
      "rectangle" (default): 填滿矩形 + 底線 + secondary 色文字 (現行預設)
      "hairline":            雙細線夾住 banner 區, 不填色, 文字躺 bg 上
      "reverse":             primary 色填滿 + bg 色文字 (反白衝擊)
      "neon":                填滿 + 內 highlight 細邊 (霓虹發光感)
    """
    if style == "hairline":
        _draw_banner_hairline(draw, section_title, palette)
    elif style == "reverse":
        _draw_banner_reverse(draw, section_title, palette)
    elif style == "neon":
        _draw_banner_neon(draw, section_title, palette)
    else:  # rectangle (default fallback)
        _draw_banner_rectangle(draw, section_title, palette)


def _draw_banner_rectangle(draw: ImageDraw.ImageDraw, section_title: str, palette: Palette) -> None:
    """現行 default 樣式: 填滿矩形 + 底線 + secondary 色文字."""
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


def _draw_banner_hairline(draw: ImageDraw.ImageDraw, section_title: str, palette: Palette) -> None:
    """極簡髮絲線: 不填色, 上下細線 + primary 色文字躺 bg 上.
    給 editorial / journal / notebook / podium / elven 用."""
    # 不畫填色矩形 (banner 區用 bg 色)
    # 上下兩條細線, 用 secondary 色
    top_y = BANNER_HEIGHT - 10
    draw.line(
        [(SIDE_MARGIN, 14), (VIDEO_WIDTH - SIDE_MARGIN, 14)],
        fill=palette["secondary"], width=1,
    )
    draw.line(
        [(SIDE_MARGIN, top_y), (VIDEO_WIDTH - SIDE_MARGIN, top_y)],
        fill=palette["secondary"], width=1,
    )
    if section_title:
        font = _font(get_font_path(), BANNER_FONT_SIZE - 2)   # 略小, 配薄線
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, palette["primary"],
        )


def _draw_banner_reverse(draw: ImageDraw.ImageDraw, section_title: str, palette: Palette) -> None:
    """反白衝擊: primary 色填滿 + bg 色文字 (對比強烈).
    給 zine / supergraphic / brutalist 用."""
    draw.rectangle([0, 0, VIDEO_WIDTH, BANNER_HEIGHT], fill=palette["primary"])
    # 底部用 highlight 色標一條粗線 (野獸派風格)
    draw.rectangle(
        [0, BANNER_HEIGHT - 4, VIDEO_WIDTH, BANNER_HEIGHT],
        fill=palette["highlight"],
    )
    if section_title:
        font = _font(get_font_path(), BANNER_FONT_SIZE + 2)   # 略大, 配粗 banner
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, palette["bg"],
        )


def _draw_banner_neon(draw: ImageDraw.ImageDraw, section_title: str, palette: Palette) -> None:
    """霓虹: 填滿 + 內 highlight 細邊 + 高對比文字.
    給 arcade 用."""
    draw.rectangle([0, 0, VIDEO_WIDTH, BANNER_HEIGHT], fill=palette["banner"])
    # 內側 4px highlight 色亮邊 (模擬霓虹發光)
    draw.rectangle(
        [4, 4, VIDEO_WIDTH - 5, BANNER_HEIGHT - 5],
        outline=palette["highlight"], width=2,
    )
    if section_title:
        font = _font(get_font_path(), BANNER_FONT_SIZE)
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, palette["highlight"],
        )


def _draw_title(
    draw: ImageDraw.ImageDraw, title: str, palette: Palette,
    decor: str = "underline",
) -> int:
    """slide 主標題 dispatch — iter 59 加 4 種 decor.

    decor:
      "underline" (default): 標題下方 highlight 色橫線 (現行行為)
      "block":               標題前 highlight 色方塊 prefix (像章節符號)
      "hairline":            標題上方 1px 細線 (學術 / 細緻)
      "reverse":             標題 wrapped 在 highlight 色塊 + bg 色反白文字
    """
    if decor == "block":
        return _draw_title_block(draw, title, palette)
    if decor == "hairline":
        return _draw_title_hairline(draw, title, palette)
    if decor == "reverse":
        return _draw_title_reverse(draw, title, palette)
    return _draw_title_underline(draw, title, palette)


def _draw_title_underline(draw: ImageDraw.ImageDraw, title: str, palette: Palette) -> int:
    """現行 default: 標題下方 highlight 橫線, 寬 5."""
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


def _draw_title_block(draw: ImageDraw.ImageDraw, title: str, palette: Palette) -> int:
    """標題前 highlight 色塊 prefix — 像 § / 章節符號感.
    給 editorial / shinobi / risograph 用 (雜誌 / 印章 / 油墨)."""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(get_font_path(), TITLE_FONT_SIZE)
    title_y = CONTENT_TOP + 30
    # 標題前方塊 (寬 16px, 高 = 字級 70%)
    block_w = 16
    block_h = int(TITLE_FONT_SIZE * 0.7)
    block_x = SIDE_MARGIN
    block_y = title_y + int(TITLE_FONT_SIZE * 0.18)
    draw.rectangle(
        [block_x, block_y, block_x + block_w, block_y + block_h],
        fill=palette["highlight"],
    )
    # 文字往右挪一個 gap (block + 18px 間距)
    text_x = SIDE_MARGIN + block_w + 18
    end_y = _draw_text_wrapped(
        draw, (text_x, title_y), title, font, palette["primary"],
        max_w=VIDEO_WIDTH - text_x - SIDE_MARGIN, line_h=TITLE_FONT_SIZE + 14,
    )
    return end_y + 30


def _draw_title_hairline(draw: ImageDraw.ImageDraw, title: str, palette: Palette) -> int:
    """標題上方 1px 細線 — 學術 / 月光感.
    給 journal / podium / notebook / elven 用."""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(get_font_path(), TITLE_FONT_SIZE)
    title_y = CONTENT_TOP + 30
    # 上方一條 hairline (寬至文字段+200px, 限制在版面內)
    hairline_y = title_y - 14
    hairline_w = max(300, int(font.getlength(title.split("\n")[0])) + 100)
    hairline_w = min(hairline_w, VIDEO_WIDTH - SIDE_MARGIN * 2)
    draw.line(
        [(SIDE_MARGIN, hairline_y), (SIDE_MARGIN + hairline_w, hairline_y)],
        fill=palette["highlight"], width=1,
    )
    end_y = _draw_text_wrapped(
        draw, (SIDE_MARGIN, title_y), title, font, palette["primary"],
        max_w=VIDEO_WIDTH - SIDE_MARGIN * 2, line_h=TITLE_FONT_SIZE + 14,
    )
    return end_y + 30


def _draw_title_reverse(draw: ImageDraw.ImageDraw, title: str, palette: Palette) -> int:
    """標題包進 highlight 色塊 + bg 色反白文字 — 海報 / 反白標籤式.
    給 zine / brutalist / supergraphic 用."""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(get_font_path(), TITLE_FONT_SIZE)
    title_y = CONTENT_TOP + 30
    # 量第一行寬度當色塊寬 (多行的話色塊只包第一行)
    first_line = title.split("\n")[0]
    text_w = int(font.getlength(first_line))
    block_w = min(text_w + 60, VIDEO_WIDTH - SIDE_MARGIN * 2)
    block_h = TITLE_FONT_SIZE + 28
    draw.rectangle(
        [SIDE_MARGIN, title_y - 12,
         SIDE_MARGIN + block_w, title_y + block_h - 12],
        fill=palette["highlight"],
    )
    end_y = _draw_text_wrapped(
        draw, (SIDE_MARGIN + 18, title_y), title, font, palette["bg"],
        max_w=VIDEO_WIDTH - SIDE_MARGIN * 2 - 36, line_h=TITLE_FONT_SIZE + 14,
    )
    return end_y + 36


def _draw_bullets(draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
                  y_max: int, palette: Palette,
                  max_text_width: int | None = None) -> int:
    """畫 bullets 列表, 強調色 ▸ marker + 主色文字, 回傳結束 y。

    iter 53: max_text_width 由 caller 指定窄寬 (例: split-image layout 時
    bullets 佔左側 55% 寬). None 走原本全寬 (預設).
    """
    if not bullets:
        return y_start
    font = _font(get_font_path(), BULLET_FONT_SIZE)
    line_h = BULLET_FONT_SIZE + 16
    indent = 60
    text_max_w = max_text_width if max_text_width is not None else (
        VIDEO_WIDTH - SIDE_MARGIN * 2 - indent
    )
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


def _draw_image_panel(
    img: Image.Image, image_path: str, y_top: int, y_bottom: int,
    palette: Palette,
) -> tuple[int, int]:
    """iter 53: split-image-right layout — 把 figure 圖貼到主圖右側區塊.

    切版策略:
    - 影像區佔內容區右側 38% 寬, 留 SIDE_MARGIN 跟左側 bullets 隔開
    - 圖按 letterbox 縮放 (保持原比例, 留白填 banner / bg 色)
    - 細灰邊框 (跟 banner secondary 同色), 讓圖跟背景界線清楚

    回傳 (panel_x_start, panel_w_used) 讓 bullets 知道避開哪段水平範圍.
    失敗 (檔不存在 / 壞圖 / PIL 不認得) 就回 (None, 0) 由 caller fallback.
    """
    try:
        from PIL import Image as _Image
        from pathlib import Path

        if not Path(image_path).exists():
            return (None, 0)

        # 影像區尺寸
        gap = 40
        # 從右邊算 38% 寬
        panel_w = int((VIDEO_WIDTH - SIDE_MARGIN * 2) * 0.38)
        panel_x = VIDEO_WIDTH - SIDE_MARGIN - panel_w
        panel_y = y_top
        panel_h = y_bottom - y_top
        if panel_h < 100 or panel_w < 100:
            return (None, 0)

        # 載圖 + letterbox
        with _Image.open(image_path) as fig:
            fig = fig.convert("RGB") if fig.mode != "RGB" else fig
            fw, fh = fig.size
            # 縮放到 panel 內 (保留比例)
            scale = min(panel_w / fw, panel_h / fh)
            new_w = max(1, int(fw * scale))
            new_h = max(1, int(fh * scale))
            fig_resized = fig.resize((new_w, new_h), _Image.LANCZOS)

        # 置中
        paste_x = panel_x + (panel_w - new_w) // 2
        paste_y = panel_y + (panel_h - new_h) // 2
        img.paste(fig_resized, (paste_x, paste_y))

        # 細邊框 (淡色, 不搶戲)
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [paste_x - 2, paste_y - 2, paste_x + new_w + 1, paste_y + new_h + 1],
            outline=palette["secondary"], width=2,
        )
        return (panel_x, panel_w + gap)
    except Exception as e:
        # 任一步失敗 (PIL 不認 / OOM / 損毀) → fallback, 不擋 render
        print(f"[pptx_style] image panel failed for {image_path}: {e}")
        return (None, 0)


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
        theme_name = data.get("theme")
        palette = get_palette(theme_name)
        # iter 58: banner style 依主題切 — rectangle (default) / hairline / reverse / neon
        banner_style = get_banner_style(theme_name)
        # iter 59: title decor 依主題切 — underline (default) / block / hairline / reverse
        title_decor = get_title_decor(theme_name)

        img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), palette["bg"])
        draw = ImageDraw.Draw(img)

        section_title = step.get("section_title") or data.get("title", "")
        _draw_banner(draw, section_title, palette, style=banner_style)

        title = step.get("title", "")
        title_end_y = _draw_title(draw, title, palette, decor=title_decor)

        content_y = title_end_y
        bullets = step.get("bullets") or []
        code = step.get("code_snippet") or ""
        file_path = step.get("file_path")
        # iter 53: image_path 已被 runner 解析成絕對路徑 (或 None)
        image_path = step.get("image_path")

        content_y_max = CONTENT_BOTTOM - 24

        # iter 53: 三種 layout 分流
        # 1. code + image 兩者: code 優先 (程式碼是主角, image 不容易並列)
        # 2. 只有 image: split-image-right (bullets 左, 圖右)
        # 3. 只有 code: 既有 code layout
        # 4. 都沒有: 既有 text-only

        if code:
            # 既有 code layout (image 即使有也忽略, 避免擠壓)
            estimated_code_h = min(
                360,
                max(120, len(code.splitlines()) * (CODE_FONT_SIZE + 8) + 80),
            )
            bullets_y_max = content_y_max - estimated_code_h - 20
            content_y = _draw_bullets(draw, bullets, content_y, bullets_y_max, palette)
            content_y = max(content_y, content_y_max - estimated_code_h)
            _draw_code_block(draw, img, code, file_path, content_y, content_y_max, palette)
        elif image_path:
            # split-image-right: 圖貼右側 38%, bullets 縮窄到左側
            panel_x, _ = _draw_image_panel(
                img, image_path, content_y, content_y_max, palette,
            )
            if panel_x is None:
                # image panel 失敗 → fallback 純文字
                _draw_bullets(draw, bullets, content_y, content_y_max, palette)
            else:
                # bullets 寬度 = 左側到 panel_x 之間 (扣 indent)
                indent = 60
                bullet_max_w = panel_x - SIDE_MARGIN - indent - 30  # 30px gap
                _draw_bullets(
                    draw, bullets, content_y, content_y_max, palette,
                    max_text_width=bullet_max_w,
                )
        else:
            _draw_bullets(draw, bullets, content_y, content_y_max, palette)

        _draw_subtitle_strip(draw)
        try:
            from pipeline import _overlay_teacher_photo
            _overlay_teacher_photo(img)
        except Exception:
            pass

        img.save(out_p, "PNG")
