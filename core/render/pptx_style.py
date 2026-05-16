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


# iter 60: theme font role — "serif" 走襯線, 其他 (sans / 未列) 走現行 default sans
# 為什麼不做 mono body: CJK mono 字型罕見 (consolas 不含 CJK), code block 才用 mono
FontRole = str  # Literal["serif", "sans"]

THEME_FONT_ROLES: dict[str, str] = {
    # 學者氣質 + 學術 + 雜誌風 走襯線
    "journal": "serif",
    "dof-editorial": "serif",
    "dof-podium": "serif",
    "dof-notebook": "serif",
    "dof-elven": "serif",
    # 其他主題 default "sans" (forest / navy / frieren / naruto / shinobi /
    # zine / arcade / risograph / supergraphic / brutalist) — 不必列在這
}

# 系統 serif CJK 字型候選 (按優先順序 — 越漂亮越優先)
# Windows 內建大多有 mingliu, 沒 Noto 也撐得住. Linux 部署到 Docker 時要另外
# 在 Dockerfile 裝 Noto Serif CJK (現行 Dockerfile 已裝 Noto Sans CJK).
SERIF_FONT_CANDIDATES = [
    "C:/Windows/Fonts/NotoSerifTC-VF.ttf",        # Noto Serif TC (modern, 最漂亮)
    "C:/Windows/Fonts/NotoSerifCJKtc-Regular.otf",
    "C:/Windows/Fonts/mingliu.ttc",                # 細明體 (內建)
    "C:/Windows/Fonts/simsun.ttc",                 # SimSun (簡體但能顯繁體)
    # Linux Docker fallback
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
]


@lru_cache(maxsize=1)
def _resolve_serif_font() -> str:
    """探系統有的 serif CJK 字型, 沒找到回 default sans 路徑 (graceful degrade).

    @lru_cache(1): 跨 render 共享結果, 第一次 probe 後不必重 stat.
    """
    import os
    for path in SERIF_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    # 都沒找到 — fall back 到 default sans 確保畫得出字
    print(f"[pptx_style] WARN: 找不到 serif CJK 字型, serif 主題退到 default sans")
    return get_font_path()


def get_font_path_for_theme(theme_name: str | None) -> str:
    """主題對應的 body 字型路徑 — serif 主題回 serif font, 其他回 default sans.

    渲染 title / banner / bullets 用. code block 仍用 mono (不影響).
    """
    role = THEME_FONT_ROLES.get(theme_name or "", "sans")
    if role == "serif":
        return _resolve_serif_font()
    return get_font_path()


# iter 61: 各主題獨特的簽名裝飾元素 (top-right corner). 不適用所有主題,
# 只給 5 個視覺最具識別性的主題加 — 其他維持 banner + title 已有的差異化即可.
#
# signature decor 種類:
#   "shinobi_stamp":  朱印章 (紅圓圈 + 内文)
#   "elven_diamond":  燙金菱形 ✦
#   "arcade_pixels":  8-bit pixel dots (3x3 小方塊)
#   "brutalist_warn": 警示斜紋 (對角線 stripes)
#   "editorial_sec":  雜誌 § 章節符號 + 羅馬數字
# iter 68b: 主題內容區 (bullets) layout 變體 — 觀眾停留最久區域, 改這裡才能
# 拉出真正的視覺差異 (claude design 建議 01). 目前提供 3 個變體:
#   - classic: • + 左對齊單欄 (預設, 教學經典)
#   - numbered: 01 / 02 / 03 編號 + 左對齊單欄 (學術 / 編輯感)
#   - centered: 居中對稱 + 大留白, 一張 slide 一個重點 (key-message style)
# 之後可擴 offset / arcade_hud / notebook_lined / shinobi_vertical 等變體.
THEME_CONTENT_LAYOUTS: dict[str, str] = {
    "forest": "classic",
    "navy": "classic",
    "frieren": "classic",
    "naruto": "classic",
    "journal": "numbered",                  # 學術期刊風 — 編號條列
    # v1 沉穩家族
    "dof-editorial": "numbered",            # 雜誌編輯風 — 編號
    "dof-podium": "centered",               # TED 講壇 — 居中大留白
    "dof-notebook": "notebook_lined",       # iter 71: 札記筆記風 (— + 行底線)
    "dof-shinobi": "shinobi_vertical",      # iter 71: 卷軸縱線 + 漢字編號
    "dof-elven": "centered",                # 月光對稱 — 居中
    # v2 衝擊家族
    "dof-zine": "offset",                   # iter 71: 海報錯位
    "dof-arcade": "arcade_hud",             # iter 71: HUD [ITEM_NN]
    "dof-risograph": "risograph_offset",    # iter 71: 兩色疊印
    "dof-supergraphic": "offset",           # iter 71: 大色塊錯位
    "dof-brutalist": "offset",              # iter 71: 野獸派錯位
}


def get_content_layout(theme_name: str | None) -> str:
    """主題對應的 content layout (classic / numbered / centered).
    沒列回 classic (預設)."""
    if not theme_name:
        return "classic"
    return THEME_CONTENT_LAYOUTS.get(theme_name, "classic")


# iter 74 (A1, claude design 04 + 05): per-theme 字級 / 行距 / margin metrics.
# 不破壞 iter 71 各 layout 內部精心調過的 multiplier — 這層只調「基線」,
# layout 函式 (offset 用 1.6× hero, centered +4 等) 仍依基線相對縮放.
#
# Keys:
#   title_size           主標題字級 (slide top), 預設 TITLE_FONT_SIZE=64
#   bullet_size          bullet 字級, 預設 BULLET_FONT_SIZE=38
#   line_height_extra    bullet 行間距 (font_size + extra), 預設 16
#   side_margin          左右留白 px, 預設 100
#   content_width_ratio  內容區寬度 (1.0=滿版, 0.7=居中縮窄), 預設 1.0
#
# None / 缺欄位 → fallback 到全域常數.
THEME_METRICS: dict[str, dict] = {
    # 衝擊家族 — 超大字
    "dof-brutalist":    {"title_size": 88, "bullet_size": 44, "side_margin": 40},
    "dof-supergraphic": {"title_size": 96, "bullet_size": 46, "side_margin": 40},
    "dof-zine":         {"title_size": 76, "bullet_size": 42, "side_margin": 60},
    # 學術 / 編輯家族 — 大行距 (airy 感)
    "journal":          {"line_height_extra": 24, "bullet_size": 40},
    "dof-editorial":    {"line_height_extra": 24, "bullet_size": 40},
    # 講壇 / 月光 — 居中縮窄 + 少字大字
    "dof-podium":       {"title_size": 72, "bullet_size": 44,
                         "content_width_ratio": 0.70, "line_height_extra": 28},
    "dof-elven":        {"title_size": 70, "bullet_size": 44,
                         "content_width_ratio": 0.72, "line_height_extra": 26},
    # 札記 — 行距更大 (筆記本格感)
    "dof-notebook":     {"line_height_extra": 28, "bullet_size": 36},
    # 其他保持預設 (forest / navy / frieren / naruto / dof-shinobi / dof-arcade /
    # dof-risograph) — 既有觀感不動
}


def get_theme_metric(theme_name: str | None, key: str, default):
    """取主題的特定 metric, 沒設用 default. iter 74."""
    if not theme_name:
        return default
    metrics = THEME_METRICS.get(theme_name, {})
    return metrics.get(key, default)


THEME_SIGNATURE_DECORS: dict[str, str] = {
    # 原 5 個 (iter 61)
    "dof-shinobi": "shinobi_stamp",
    "dof-elven": "elven_diamond",
    "dof-arcade": "arcade_pixels",
    "dof-brutalist": "brutalist_warn",
    "dof-editorial": "editorial_sec",
    # iter 69: 補另外 10 個 (claude design 建議 03)
    "forest": "chalk_strokes",          # 黑板粉筆筆觸
    "navy": "circuit_trace",            # PCB 線路
    "frieren": "magic_hex",             # 六角魔法陣
    "naruto": "spiral_seal",            # 卷軸螺旋封印
    "journal": "page_marker",           # — 1 — 頁碼章節
    "dof-podium": "minimal_diamond",    # ◆ + 細直線
    "dof-notebook": "sticky_corner",    # 便條紙折角
    "dof-zine": "sticker_bang",         # 撞色 sticker
    "dof-risograph": "riso_dots",       # 兩色錯位圓點
    "dof-supergraphic": "big_number",   # 巨大數字
}


def get_signature_decor(theme_name: str | None) -> str | None:
    """主題對應的 signature decor 名稱, 沒列回 None (不畫)."""
    if not theme_name:
        return None
    return THEME_SIGNATURE_DECORS.get(theme_name)


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
    style: str = "rectangle", font_path: str | None = None,
) -> None:
    """頂部章節 banner — iter 58 加 4 種 style dispatch. iter 60 加 font_path.

    style:
      "rectangle" (default): 填滿矩形 + 底線 + secondary 色文字 (現行預設)
      "hairline":            雙細線夾住 banner 區, 不填色, 文字躺 bg 上
      "reverse":             primary 色填滿 + bg 色文字 (反白衝擊)
      "neon":                填滿 + 內 highlight 細邊 (霓虹發光感)
    font_path: iter 60 — None 則用 default sans. serif 主題 caller 帶進來.
    """
    if style == "hairline":
        _draw_banner_hairline(draw, section_title, palette, font_path)
    elif style == "reverse":
        _draw_banner_reverse(draw, section_title, palette, font_path)
    elif style == "neon":
        _draw_banner_neon(draw, section_title, palette, font_path)
    else:  # rectangle (default fallback)
        _draw_banner_rectangle(draw, section_title, palette, font_path)


def _draw_banner_rectangle(
    draw: ImageDraw.ImageDraw, section_title: str, palette: Palette,
    font_path: str | None = None,
) -> None:
    """現行 default 樣式: 填滿矩形 + 底線 + secondary 色文字."""
    draw.rectangle([0, 0, VIDEO_WIDTH, BANNER_HEIGHT], fill=palette["banner"])
    draw.line(
        [(0, BANNER_HEIGHT), (VIDEO_WIDTH, BANNER_HEIGHT)],
        fill=palette["secondary"], width=2,
    )
    if section_title:
        font = _font(font_path or get_font_path(), BANNER_FONT_SIZE)
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, palette["secondary"],
        )


def _draw_banner_hairline(
    draw: ImageDraw.ImageDraw, section_title: str, palette: Palette,
    font_path: str | None = None,
) -> None:
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
        font = _font(font_path or get_font_path(), BANNER_FONT_SIZE - 2)   # 略小, 配薄線
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, palette["primary"],
        )


def _draw_banner_reverse(
    draw: ImageDraw.ImageDraw, section_title: str, palette: Palette,
    font_path: str | None = None,
) -> None:
    """反白衝擊: primary 色填滿 + bg 色文字 (對比強烈).
    給 zine / supergraphic / brutalist 用."""
    draw.rectangle([0, 0, VIDEO_WIDTH, BANNER_HEIGHT], fill=palette["primary"])
    # 底部用 highlight 色標一條粗線 (野獸派風格)
    draw.rectangle(
        [0, BANNER_HEIGHT - 4, VIDEO_WIDTH, BANNER_HEIGHT],
        fill=palette["highlight"],
    )
    if section_title:
        font = _font(font_path or get_font_path(), BANNER_FONT_SIZE + 2)   # 略大, 配粗 banner
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, palette["bg"],
        )


def _draw_banner_neon(
    draw: ImageDraw.ImageDraw, section_title: str, palette: Palette,
    font_path: str | None = None,
) -> None:
    """霓虹: 填滿 + 內 highlight 細邊 + 高對比文字.
    給 arcade 用."""
    draw.rectangle([0, 0, VIDEO_WIDTH, BANNER_HEIGHT], fill=palette["banner"])
    # 內側 4px highlight 色亮邊 (模擬霓虹發光)
    draw.rectangle(
        [4, 4, VIDEO_WIDTH - 5, BANNER_HEIGHT - 5],
        outline=palette["highlight"], width=2,
    )
    if section_title:
        font = _font(font_path or get_font_path(), BANNER_FONT_SIZE)
        text_y = (BANNER_HEIGHT - BANNER_FONT_SIZE) // 2 - 4
        _draw_text_mixed(
            draw, (SIDE_MARGIN, text_y), section_title, font, palette["highlight"],
        )


def _draw_title(
    draw: ImageDraw.ImageDraw, title: str, palette: Palette,
    decor: str = "underline", font_path: str | None = None,
    title_size: int | None = None,
    side_margin: int | None = None,
) -> int:
    """slide 主標題 dispatch — iter 59 加 4 種 decor. iter 60 加 font_path.
    iter 74 (A1): title_size 由 caller 從 THEME_METRICS 取, None → 全域 default.
    iter 75 (A2): side_margin 同上 (brutalist=40 等貼邊緣).

    decor:
      "underline" (default): 標題下方 highlight 色橫線 (現行行為)
      "block":               標題前 highlight 色方塊 prefix (像章節符號)
      "hairline":            標題上方 1px 細線 (學術 / 細緻)
      "reverse":             標題 wrapped 在 highlight 色塊 + bg 色反白文字
    """
    size = title_size if title_size is not None else TITLE_FONT_SIZE
    margin = side_margin if side_margin is not None else SIDE_MARGIN
    if decor == "block":
        return _draw_title_block(draw, title, palette, font_path, size, margin)
    if decor == "hairline":
        return _draw_title_hairline(draw, title, palette, font_path, size, margin)
    if decor == "reverse":
        return _draw_title_reverse(draw, title, palette, font_path, size, margin)
    return _draw_title_underline(draw, title, palette, font_path, size, margin)


def _draw_title_underline(
    draw: ImageDraw.ImageDraw, title: str, palette: Palette,
    font_path: str | None = None,
    title_size: int = TITLE_FONT_SIZE,
    side_margin: int = SIDE_MARGIN,
) -> int:
    """現行 default: 標題下方 highlight 橫線, 寬 5.
    iter 74/75: title_size + side_margin 接 caller (從 THEME_METRICS)."""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(font_path or get_font_path(), title_size)
    title_y = CONTENT_TOP + 30
    end_y = _draw_text_wrapped(
        draw, (side_margin, title_y), title, font, palette["primary"],
        max_w=VIDEO_WIDTH - side_margin * 2, line_h=title_size + 14,
    )
    underline_w = max(200, int(font.getlength(title.split("\n")[0])))
    underline_w = min(underline_w, VIDEO_WIDTH - side_margin * 2)
    underline_y = end_y + 8
    draw.line(
        [(side_margin, underline_y), (side_margin + underline_w, underline_y)],
        fill=palette["highlight"], width=5,
    )
    return underline_y + 30


def _draw_title_block(
    draw: ImageDraw.ImageDraw, title: str, palette: Palette,
    font_path: str | None = None,
    title_size: int = TITLE_FONT_SIZE,
    side_margin: int = SIDE_MARGIN,
) -> int:
    """標題前 highlight 色塊 prefix — 像 § / 章節符號感."""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(font_path or get_font_path(), title_size)
    title_y = CONTENT_TOP + 30
    block_w = 16
    block_h = int(title_size * 0.7)
    block_x = side_margin
    block_y = title_y + int(title_size * 0.18)
    draw.rectangle(
        [block_x, block_y, block_x + block_w, block_y + block_h],
        fill=palette["highlight"],
    )
    text_x = side_margin + block_w + 18
    end_y = _draw_text_wrapped(
        draw, (text_x, title_y), title, font, palette["primary"],
        max_w=VIDEO_WIDTH - text_x - side_margin, line_h=title_size + 14,
    )
    return end_y + 30


def _draw_title_hairline(
    draw: ImageDraw.ImageDraw, title: str, palette: Palette,
    font_path: str | None = None,
    title_size: int = TITLE_FONT_SIZE,
    side_margin: int = SIDE_MARGIN,
) -> int:
    """標題上方 1px 細線 — 學術 / 月光感."""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(font_path or get_font_path(), title_size)
    title_y = CONTENT_TOP + 30
    hairline_y = title_y - 14
    hairline_w = max(300, int(font.getlength(title.split("\n")[0])) + 100)
    hairline_w = min(hairline_w, VIDEO_WIDTH - side_margin * 2)
    draw.line(
        [(side_margin, hairline_y), (side_margin + hairline_w, hairline_y)],
        fill=palette["highlight"], width=1,
    )
    end_y = _draw_text_wrapped(
        draw, (side_margin, title_y), title, font, palette["primary"],
        max_w=VIDEO_WIDTH - side_margin * 2, line_h=title_size + 14,
    )
    return end_y + 30


def _draw_title_reverse(
    draw: ImageDraw.ImageDraw, title: str, palette: Palette,
    font_path: str | None = None,
    title_size: int = TITLE_FONT_SIZE,
    side_margin: int = SIDE_MARGIN,
) -> int:
    """標題包進 highlight 色塊 + bg 色反白文字 — 海報 / 反白標籤式."""
    title = (title or "").strip()
    if not title:
        return CONTENT_TOP
    font = _font(font_path or get_font_path(), title_size)
    title_y = CONTENT_TOP + 30
    first_line = title.split("\n")[0]
    text_w = int(font.getlength(first_line))
    block_w = min(text_w + 60, VIDEO_WIDTH - side_margin * 2)
    block_h = title_size + 28
    draw.rectangle(
        [side_margin, title_y - 12,
         side_margin + block_w, title_y + block_h - 12],
        fill=palette["highlight"],
    )
    end_y = _draw_text_wrapped(
        draw, (side_margin + 18, title_y), title, font, palette["bg"],
        max_w=VIDEO_WIDTH - side_margin * 2 - 36, line_h=title_size + 14,
    )
    return end_y + 36


def _draw_bullets_classic(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    bullet_size: int | None = None,
    line_height_extra: int | None = None,
    side_margin: int | None = None,
) -> int:
    """經典版: highlight 色 • marker + 左對齊單欄. 教學主題 (forest / navy 等)."""
    if not bullets:
        return y_start
    fpath = font_path or get_font_path()
    fsize = bullet_size if bullet_size is not None else BULLET_FONT_SIZE
    extra = line_height_extra if line_height_extra is not None else 16
    sm = side_margin if side_margin is not None else SIDE_MARGIN
    font = _font(fpath, fsize)
    line_h = fsize + extra
    indent = 60
    text_max_w = max_text_width if max_text_width is not None else (
        VIDEO_WIDTH - sm * 2 - indent
    )
    marker_font = _font(fpath, fsize + 6)

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        _draw_text_mixed(
            draw, (sm + 18, y - 8), "•", marker_font, palette["highlight"],
        )
        end_y = _draw_text_wrapped(
            draw, (sm + indent, y), bullet, font, palette["primary"],
            max_w=text_max_w, line_h=line_h,
        )
        y = end_y + 12
        if y > y_max:
            if i < len(bullets) - 1:
                draw.text(
                    (sm + indent, y - 8), "...", font=font, fill=palette["primary"],
                )
            break
    return y


def _draw_bullets_numbered(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    bullet_size: int | None = None,
    line_height_extra: int | None = None,
    side_margin: int | None = None,
) -> int:
    """編號版: 01 / 02 / 03 兩位數編號 + 左對齊單欄."""
    if not bullets:
        return y_start
    fpath = font_path or get_font_path()
    fsize = bullet_size if bullet_size is not None else BULLET_FONT_SIZE
    extra = line_height_extra if line_height_extra is not None else 18
    sm = side_margin if side_margin is not None else SIDE_MARGIN
    font = _font(fpath, fsize)
    line_h = fsize + extra
    num_font = _font(fpath, fsize + 8)
    indent = 110
    text_max_w = max_text_width if max_text_width is not None else (
        VIDEO_WIDTH - sm * 2 - indent
    )

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        label = f"{i + 1:02d}"
        _draw_text_mixed(
            draw, (sm + 14, y - 4), label, num_font, palette["secondary"],
        )
        end_y = _draw_text_wrapped(
            draw, (sm + indent, y), bullet, font, palette["primary"],
            max_w=text_max_w, line_h=line_h,
        )
        y = end_y + 14
        if y > y_max:
            if i < len(bullets) - 1:
                draw.text(
                    (sm + indent, y - 8), "...",
                    font=font, fill=palette["primary"],
                )
            break
    return y


def _draw_bullets_centered(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    bullet_size: int | None = None,
    line_height_extra: int | None = None,
    side_margin: int | None = None,
) -> int:
    """居中版: 每條 bullet 居中, 大留白, 字級略大. 主題 podium / elven —
    key-message 演講風. 不畫 marker (極簡, bullet 自身就是主角)."""
    if not bullets:
        return y_start
    fpath = font_path or get_font_path()
    fsize = bullet_size if bullet_size is not None else (BULLET_FONT_SIZE + 4)
    extra = line_height_extra if line_height_extra is not None else 32
    sm = side_margin if side_margin is not None else SIDE_MARGIN
    font = _font(fpath, fsize)
    line_h = fsize + extra
    text_max_w = max_text_width if max_text_width is not None else int(VIDEO_WIDTH * 0.70)

    y = y_start
    item_gap = 32
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        line_w = int(font.getlength(bullet))
        line_w = min(line_w, text_max_w)
        line_x = max(sm, (VIDEO_WIDTH - line_w) // 2)
        end_y = _draw_text_wrapped(
            draw, (line_x, y), bullet, font, palette["primary"],
            max_w=text_max_w, line_h=line_h,
        )
        y = end_y + item_gap
        if y > y_max:
            if i < len(bullets) - 1:
                ellipsis_x = (VIDEO_WIDTH - int(font.getlength("..."))) // 2
                draw.text(
                    (ellipsis_x, y - 8), "...",
                    font=font, fill=palette["primary"],
                )
            break
    return y


def _draw_bullets_offset(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    bullet_size: int | None = None,
    line_height_extra: int | None = None,  # noqa: 不直接用, hero/small 自有 gap
    side_margin: int | None = None,
) -> int:
    """iter 71: 錯位 + 強反差 — 第一條超大字 + 其他擠小 + x 軸錯位."""
    if not bullets:
        return y_start
    fpath = font_path or get_font_path()
    base = bullet_size if bullet_size is not None else BULLET_FONT_SIZE
    sm = side_margin if side_margin is not None else SIDE_MARGIN
    hero_font = _font(fpath, int(base * 1.6))
    small_font = _font(fpath, int(base * 0.85))
    hero_line_h = int(base * 1.6) + 14
    small_line_h = int(base * 0.85) + 12

    text_max_w = max_text_width if max_text_width is not None else (
        VIDEO_WIDTH - sm * 2 - 80
    )

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        if i == 0:
            end_y = _draw_text_wrapped(
                draw, (sm, y), bullet, hero_font, palette["highlight"],
                max_w=text_max_w, line_h=hero_line_h,
            )
            y = end_y + 26
        else:
            indent = 60 if i % 2 == 1 else 140
            end_y = _draw_text_wrapped(
                draw, (sm + indent, y), bullet, small_font,
                palette["primary"],
                max_w=text_max_w - indent, line_h=small_line_h,
            )
            y = end_y + 14
        if y > y_max:
            break
    return y


def _draw_bullets_arcade_hud(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    bullet_size: int | None = None,
    line_height_extra: int | None = None,
    side_margin: int | None = None,
) -> int:
    """iter 71: 8-bit HUD 風 — 每條 bullet 前 [ITEM_NN] 方括號 + 點數標籤."""
    if not bullets:
        return y_start
    fpath = font_path or get_font_path()
    mono_path = get_mono_font_path()
    fsize = bullet_size if bullet_size is not None else BULLET_FONT_SIZE
    extra = line_height_extra if line_height_extra is not None else 18
    sm = side_margin if side_margin is not None else SIDE_MARGIN
    font = _font(fpath, fsize)
    tag_font = _font(mono_path, int(fsize * 0.85))
    line_h = fsize + extra
    indent = 220

    text_max_w = max_text_width if max_text_width is not None else (
        VIDEO_WIDTH - sm * 2 - indent
    )

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        tag = f"[ITEM_{i + 1:02d}]"
        _draw_text_mixed(
            draw, (sm + 10, y + 4), tag, tag_font, palette["highlight"],
        )
        end_y = _draw_text_wrapped(
            draw, (sm + indent, y), bullet, font, palette["primary"],
            max_w=text_max_w, line_h=line_h,
        )
        y = end_y + 14
        if y > y_max:
            break
    return y


def _draw_bullets_notebook_lined(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    bullet_size: int | None = None,
    line_height_extra: int | None = None,
    side_margin: int | None = None,
) -> int:
    """iter 71: 札記筆記風 — 行距大 + 每條前破折號 (—) + 細水平底線."""
    if not bullets:
        return y_start
    fpath = font_path or get_font_path()
    fsize = bullet_size if bullet_size is not None else BULLET_FONT_SIZE
    extra = line_height_extra if line_height_extra is not None else 32
    sm = side_margin if side_margin is not None else SIDE_MARGIN
    font = _font(fpath, fsize)
    line_h = fsize + extra
    indent = 80

    text_max_w = max_text_width if max_text_width is not None else (
        VIDEO_WIDTH - sm * 2 - indent
    )

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        _draw_text_mixed(
            draw, (sm + 14, y), "—", font, palette["secondary"],
        )
        end_y = _draw_text_wrapped(
            draw, (sm + indent, y), bullet, font, palette["primary"],
            max_w=text_max_w, line_h=line_h,
        )
        underline_y = end_y + 10
        draw.line(
            [(sm + 14, underline_y),
             (VIDEO_WIDTH - sm - 20, underline_y)],
            fill=palette["secondary"], width=1,
        )
        y = end_y + 26
        if y > y_max:
            break
    return y


def _draw_bullets_shinobi_vertical(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    bullet_size: int | None = None,
    line_height_extra: int | None = None,
    side_margin: int | None = None,
) -> int:
    """iter 71: 忍者卷軸式 — 縱線分組 ┃ + 漢字編號 (一 / 二 / 三)."""
    if not bullets:
        return y_start
    fpath = font_path or get_font_path()
    fsize = bullet_size if bullet_size is not None else BULLET_FONT_SIZE
    extra = line_height_extra if line_height_extra is not None else 20
    sm = side_margin if side_margin is not None else SIDE_MARGIN
    font = _font(fpath, fsize)
    label_font = _font(fpath, int(fsize * 1.1))
    line_h = fsize + extra
    indent = 160

    cn_digits = ("零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十")
    text_max_w = max_text_width if max_text_width is not None else (
        VIDEO_WIDTH - sm * 2 - indent
    )

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        line_top = y + 2
        line_bot = y + fsize + 12
        draw.rectangle(
            [sm + 18, line_top, sm + 22, line_bot],
            fill=palette["highlight"],
        )
        num_str = cn_digits[i + 1] if 1 <= (i + 1) <= 10 else str(i + 1)
        _draw_text_mixed(
            draw, (sm + 50, y), num_str, label_font, palette["highlight"],
        )
        end_y = _draw_text_wrapped(
            draw, (sm + indent, y), bullet, font, palette["primary"],
            max_w=text_max_w, line_h=line_h,
        )
        y = end_y + 18
        if y > y_max:
            break
    return y


def _draw_bullets_risograph_offset(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    bullet_size: int | None = None,
    line_height_extra: int | None = None,
    side_margin: int | None = None,
) -> int:
    """iter 71: risograph 兩色錯位疊印 — 文字畫兩次, secondary 色微錯位
    在 primary 色下方, 模擬油墨疊印效果."""
    if not bullets:
        return y_start
    fpath = font_path or get_font_path()
    fsize = bullet_size if bullet_size is not None else BULLET_FONT_SIZE
    extra = line_height_extra if line_height_extra is not None else 18
    sm = side_margin if side_margin is not None else SIDE_MARGIN
    font = _font(fpath, fsize)
    marker_font = _font(fpath, fsize + 6)
    line_h = fsize + extra
    indent = 70

    text_max_w = max_text_width if max_text_width is not None else (
        VIDEO_WIDTH - sm * 2 - indent
    )

    y = y_start
    for i, bullet in enumerate(bullets):
        bullet = (bullet or "").strip()
        if not bullet:
            continue
        _draw_text_mixed(
            draw, (sm + 18 + 3, y - 8 + 2), "●", marker_font,
            palette["secondary"],
        )
        _draw_text_mixed(
            draw, (sm + 18, y - 8), "●", marker_font,
            palette["highlight"],
        )
        _draw_text_wrapped(
            draw, (sm + indent + 2, y + 2), bullet, font,
            palette["secondary"],
            max_w=text_max_w, line_h=line_h,
        )
        end_y = _draw_text_wrapped(
            draw, (sm + indent, y), bullet, font, palette["primary"],
            max_w=text_max_w, line_h=line_h,
        )
        y = end_y + 14
        if y > y_max:
            break
    return y


def _draw_bullets(
    draw: ImageDraw.ImageDraw, bullets: list[str], y_start: int,
    y_max: int, palette: Palette,
    max_text_width: int | None = None,
    font_path: str | None = None,
    layout: str = "classic",
    bullet_size: int | None = None,
    line_height_extra: int | None = None,
    side_margin: int | None = None,
) -> int:
    """畫 bullets, dispatch 到對應 layout 變體, 回傳結束 y.

    iter 68b: layout 由 caller 從 get_content_layout(theme_name) 取得.
    iter 71: 補 5 個變體 (offset / arcade_hud / notebook_lined /
    shinobi_vertical / risograph_offset). 未知 layout fallback 到 classic.
    iter 74 (A1): bullet_size + line_height_extra 由 caller 從 THEME_METRICS
    取. None → 用全域 BULLET_FONT_SIZE / 16. layout 內部仍可相對縮放 (offset
    用 hero 1.6× 等), 這層只調 base.

    iter 53: max_text_width 由 caller 指定窄寬 (例: split-image layout 時
    bullets 佔左側 55% 寬).
    iter 60: font_path 由 caller 帶 (serif 主題用 serif font).
    """
    if not bullets:
        return y_start
    fn = {
        "classic": _draw_bullets_classic,
        "numbered": _draw_bullets_numbered,
        "centered": _draw_bullets_centered,
        "offset": _draw_bullets_offset,
        "arcade_hud": _draw_bullets_arcade_hud,
        "notebook_lined": _draw_bullets_notebook_lined,
        "shinobi_vertical": _draw_bullets_shinobi_vertical,
        "risograph_offset": _draw_bullets_risograph_offset,
    }.get(layout, _draw_bullets_classic)
    return fn(draw, bullets, y_start, y_max, palette,
              max_text_width=max_text_width, font_path=font_path,
              bullet_size=bullet_size, line_height_extra=line_height_extra,
              side_margin=side_margin)


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


def _luma(rgb: tuple[int, int, int]) -> float:
    """Rec. 601 luma — 用來判斷顏色亮度. 0 (黑) ~ 255 (白)."""
    return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]


def _pick_meta_color(palette: Palette, threshold: float = 80.0) -> tuple[int, int, int]:
    """iter 62a: 封面 meta 文字選色 — secondary 對比夠就用, 不夠 fallback 到 primary.

    背景: 部分主題的 secondary 是 muted gray / lavender / neon 對淺底對比不
    足 (例: brutalist secondary=螢光綠 配米白幾乎看不見). 這函式做防呆.

    threshold=80: Rec. 601 luma 差值門檻, 經驗值. < 80 視為對比不足.
    """
    if abs(_luma(palette["secondary"]) - _luma(palette["bg"])) >= threshold:
        return palette["secondary"]
    return palette["primary"]


def _draw_brutalist_frame(
    draw: ImageDraw.ImageDraw, palette: Palette,
    inset: int = 80, thickness: int = 12,
) -> None:
    """iter 64: 為 banner_style=reverse 的主題 (brutalist / supergraphic /
    zine) 在封面/結尾頁外圍畫粗框, 加強野獸派 / 海報式視覺衝擊感.

    inset: 框離邊緣的內縮量
    thickness: 框線粗細

    Letterbox-friendly: 上邊框不蓋到 teacher photo overlay, 下邊框不蓋到字幕帶.
    """
    left = inset
    right = VIDEO_WIDTH - inset
    top = inset
    bottom = VIDEO_HEIGHT - SUBTITLE_STRIP_HEIGHT - inset // 2
    # 四條邊: 上 / 下 / 左 / 右
    draw.rectangle([left, top, right, top + thickness], fill=palette["primary"])
    draw.rectangle([left, bottom - thickness, right, bottom], fill=palette["primary"])
    draw.rectangle([left, top, left + thickness, bottom], fill=palette["primary"])
    draw.rectangle([right - thickness, top, right, bottom], fill=palette["primary"])


def _draw_cover_slide(
    draw: ImageDraw.ImageDraw, step: dict, palette: Palette,
    body_font_path: str | None = None,
    *,
    signature_decor: str | None = None,
    banner_style: str = "rectangle",
) -> None:
    """iter 62 + 64: 封面頁專屬 layout.

    版面 (預設):
    - 上 1/3 空白 (留 breathing room)
    - 中央: 大標題 (deck title), 字級 = TITLE_FONT_SIZE * 1.4
    - 標題下方 highlight 色橫線 (居中)
    - 標題下: 講者 / 日期 / 單位 三行 meta (iter 62a: contrast-aware 選色,
      secondary 對比不夠時 fallback 到 primary)

    iter 64 主題差異化:
    - banner_style="reverse" 主題 (brutalist / supergraphic / zine): 外圍粗框
    - signature_decor 非 None: 對應主題 (shinobi / elven / arcade / brutalist
      / editorial) 在右上角畫識別徽章
    """
    fpath = body_font_path or get_font_path()
    # 大標題字級
    cover_title_size = int(TITLE_FONT_SIZE * 1.4)
    meta_size = 32
    deck_title = (step.get("title") or "今天的主題").strip()
    speaker = (step.get("cover_speaker") or "").strip()
    date = (step.get("cover_date") or "").strip()
    org = (step.get("cover_org") or "").strip()

    title_font = _font(fpath, cover_title_size)
    meta_font = _font(fpath, meta_size)
    # iter 62a: meta 文字色 — 對比優先, 不依賴 secondary
    meta_color = _pick_meta_color(palette)

    # iter 64: reverse 主題畫粗框 (在最底層, 後續元素疊在上面)
    if banner_style == "reverse":
        _draw_brutalist_frame(draw, palette)

    # 標題: 居中, 自動換行 (寬度限 80% video width)
    max_title_w = int(VIDEO_WIDTH * 0.85)
    title_y = int(VIDEO_HEIGHT * 0.32)
    # 簡單居中: 量第一行寬, 從中心對齊起始 x
    first_line = deck_title.split("\n")[0]
    title_w = int(title_font.getlength(first_line))
    title_w = min(title_w, max_title_w)
    title_x = max(SIDE_MARGIN, (VIDEO_WIDTH - title_w) // 2)
    end_y = _draw_text_wrapped(
        draw, (title_x, title_y), deck_title, title_font, palette["primary"],
        max_w=max_title_w, line_h=cover_title_size + 18,
    )

    # 標題下方 highlight 色橫線, 居中, 寬度約等於文字
    rule_w = max(180, min(title_w, max_title_w))
    rule_x = (VIDEO_WIDTH - rule_w) // 2
    rule_y = end_y + 24
    draw.rectangle(
        [rule_x, rule_y, rule_x + rule_w, rule_y + 4],
        fill=palette["highlight"],
    )

    # Meta 三行 — 居中, 用 contrast-aware color
    meta_y = rule_y + 40
    for line in (speaker, date, org):
        line = (line or "").strip()
        if not line:
            continue
        line_w = int(meta_font.getlength(line))
        line_x = max(SIDE_MARGIN, (VIDEO_WIDTH - line_w) // 2)
        _draw_text_mixed(
            draw, (line_x, meta_y), line, meta_font, meta_color,
        )
        meta_y += meta_size + 14

    # iter 64: signature decor (5 主題各自的識別徽章) 畫在右上角
    if signature_decor:
        _draw_signature_decor(draw, signature_decor, palette, step_idx=1)


def _generate_qr_png(url: str, size_px: int = 220) -> Image.Image | None:
    """iter 67: 生 QR code PIL.Image. URL 空 / qrcode 未裝 → None.

    size_px: 最終長寬 (正方形). 內部 box_size 依此算.
    """
    url = (url or "").strip()
    if not url:
        return None
    try:
        import qrcode  # 可選依賴, 沒裝就跳過
    except ImportError:
        return None
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        # 強制 RGB + resize 成目標尺寸
        img = img.convert("RGB").resize((size_px, size_px), Image.NEAREST)
        return img
    except Exception:
        return None


def _draw_outro_qr_codes(
    img: Image.Image, draw: ImageDraw.ImageDraw,
    web_url: str, youtube_url: str, palette: Palette,
    body_font_path: str | None = None,
) -> None:
    """iter 67: outro 底部畫兩個 QR code — 左下「網頁」, 右下「頻道」.

    位置: 字幕帶上方 ~40px, 兩側距 SIDE_MARGIN 加 20px. QR 下方標籤
    用 secondary 色小字.

    每個 QR 失敗 (空 URL / qrcode 沒裝) → 跳過, 不擋整個 outro 渲染.
    """
    qr_size = 200
    label_size = 24
    qr_y = VIDEO_HEIGHT - SUBTITLE_STRIP_HEIGHT - qr_size - 50  # 上面 50 留標籤
    side_inset = SIDE_MARGIN + 20
    label_font = _font(body_font_path or get_font_path(), label_size)

    # 左下: 網頁 QR
    if web_url:
        qr_left = _generate_qr_png(web_url, size_px=qr_size)
        if qr_left is not None:
            img.paste(qr_left, (side_inset, qr_y))
            label = "網頁"
            label_w = int(label_font.getlength(label))
            label_x = side_inset + (qr_size - label_w) // 2
            label_y = qr_y + qr_size + 6
            _draw_text_mixed(
                draw, (label_x, label_y), label, label_font,
                palette["secondary"],
            )

    # 右下: YouTube QR
    if youtube_url:
        qr_right = _generate_qr_png(youtube_url, size_px=qr_size)
        if qr_right is not None:
            right_x = VIDEO_WIDTH - side_inset - qr_size
            img.paste(qr_right, (right_x, qr_y))
            label = "YouTube"
            label_w = int(label_font.getlength(label))
            label_x = right_x + (qr_size - label_w) // 2
            label_y = qr_y + qr_size + 6
            _draw_text_mixed(
                draw, (label_x, label_y), label, label_font,
                palette["secondary"],
            )


def _draw_outro_slide(
    draw: ImageDraw.ImageDraw, step: dict, palette: Palette,
    body_font_path: str | None = None,
    *,
    signature_decor: str | None = None,
    banner_style: str = "rectangle",
    img: Image.Image | None = None,
) -> None:
    """iter 63 + 64: 結尾頁專屬 layout, 跟封面對稱.

    版面 (預設):
    - 上 1/3 空白
    - 中央: 大字 thanks_text (預設「謝謝聆聽」), 字級 = TITLE_FONT_SIZE * 1.6
      (比封面更大, 結尾要有 closure 感)
    - 主標下方 highlight 色橫線 (居中)
    - 主標下: 講者 / 單位 / URL 三行 meta (contrast-aware 選色, 跟封面共用)

    iter 64 主題差異化 (跟 cover 對稱):
    - banner_style="reverse": 外圍粗框
    - signature_decor 非 None: 右上角識別徽章
    """
    fpath = body_font_path or get_font_path()
    outro_title_size = int(TITLE_FONT_SIZE * 1.6)
    meta_size = 32
    thanks = (step.get("title") or "謝謝聆聽").strip()
    speaker = (step.get("outro_speaker") or "").strip()
    org = (step.get("outro_org") or "").strip()
    url = (step.get("outro_url") or "").strip()

    title_font = _font(fpath, outro_title_size)
    meta_font = _font(fpath, meta_size)
    # 共用 iter 62a 的 contrast-aware 選色
    meta_color = _pick_meta_color(palette)

    # iter 64: reverse 主題畫粗框
    if banner_style == "reverse":
        _draw_brutalist_frame(draw, palette)

    # 主標題: 居中, 跟封面同邏輯
    max_title_w = int(VIDEO_WIDTH * 0.85)
    title_y = int(VIDEO_HEIGHT * 0.30)
    first_line = thanks.split("\n")[0]
    title_w = int(title_font.getlength(first_line))
    title_w = min(title_w, max_title_w)
    title_x = max(SIDE_MARGIN, (VIDEO_WIDTH - title_w) // 2)
    end_y = _draw_text_wrapped(
        draw, (title_x, title_y), thanks, title_font, palette["primary"],
        max_w=max_title_w, line_h=outro_title_size + 18,
    )

    # 主標下方 highlight 色橫線, 居中, 寬度約等於文字
    rule_w = max(220, min(title_w, max_title_w))
    rule_x = (VIDEO_WIDTH - rule_w) // 2
    rule_y = end_y + 28
    draw.rectangle(
        [rule_x, rule_y, rule_x + rule_w, rule_y + 4],
        fill=palette["highlight"],
    )

    # Meta 三行 — 講者 / 單位 / URL
    meta_y = rule_y + 44
    for line in (speaker, org, url):
        line = (line or "").strip()
        if not line:
            continue
        line_w = int(meta_font.getlength(line))
        line_x = max(SIDE_MARGIN, (VIDEO_WIDTH - line_w) // 2)
        _draw_text_mixed(
            draw, (line_x, meta_y), line, meta_font, meta_color,
        )
        meta_y += meta_size + 14

    # iter 64: signature decor (跟 cover 對稱)
    if signature_decor:
        _draw_signature_decor(draw, signature_decor, palette, step_idx=1)

    # iter 67: 底部 QR code (網頁 + YouTube). 只在 step.outro_show_qr=True
    # 且 img (PIL Image) 傳進來時才畫 — img.paste 需要 Image 不只 draw.
    if step.get("outro_show_qr") and img is not None:
        web_url = (step.get("outro_url") or "").strip()
        yt_url = (step.get("outro_youtube_url") or "").strip()
        _draw_outro_qr_codes(
            img, draw, web_url, yt_url, palette, body_font_path,
        )


def _draw_signature_decor(
    draw: ImageDraw.ImageDraw, decor: str | None, palette: Palette,
    step_idx: int = 1,
) -> None:
    """iter 61: 主題獨特的簽名裝飾元素, 畫在 slide 右上角.

    位置: x ∈ [VIDEO_WIDTH - 220, VIDEO_WIDTH - 60], y ∈ [BANNER_HEIGHT + 30,
    BANNER_HEIGHT + 150]. 不影響 title / bullets / code 區域.

    decor=None 時 noop (大多數主題).
    """
    if not decor:
        return
    corner_x = VIDEO_WIDTH - 140    # 中心 x
    corner_y = BANNER_HEIGHT + 60   # 中心 y

    if decor == "shinobi_stamp":
        _draw_shinobi_stamp(draw, corner_x, corner_y, palette)
    elif decor == "elven_diamond":
        _draw_elven_diamond(draw, corner_x, corner_y, palette)
    elif decor == "arcade_pixels":
        _draw_arcade_pixels(draw, corner_x, corner_y, palette)
    elif decor == "brutalist_warn":
        _draw_brutalist_warn(draw, corner_x, corner_y, palette)
    elif decor == "editorial_sec":
        _draw_editorial_section_mark(draw, corner_x, corner_y, palette, step_idx)
    # iter 69: 10 個新 decor
    elif decor == "chalk_strokes":
        _draw_chalk_strokes(draw, corner_x, corner_y, palette)
    elif decor == "circuit_trace":
        _draw_circuit_trace(draw, corner_x, corner_y, palette)
    elif decor == "magic_hex":
        _draw_magic_hex(draw, corner_x, corner_y, palette)
    elif decor == "spiral_seal":
        _draw_spiral_seal(draw, corner_x, corner_y, palette)
    elif decor == "page_marker":
        _draw_page_marker(draw, corner_x, corner_y, palette, step_idx)
    elif decor == "minimal_diamond":
        _draw_minimal_diamond(draw, corner_x, corner_y, palette)
    elif decor == "sticky_corner":
        _draw_sticky_corner(draw, corner_x, corner_y, palette)
    elif decor == "sticker_bang":
        _draw_sticker_bang(draw, corner_x, corner_y, palette)
    elif decor == "riso_dots":
        _draw_riso_dots(draw, corner_x, corner_y, palette)
    elif decor == "big_number":
        _draw_big_number(draw, corner_x, corner_y, palette, step_idx)


def _draw_shinobi_stamp(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """朱印章: 紅圓 + 中央「印」字 (中文字型支援的話) 或「DOF」.

    用 highlight 色 (朱印紅 C73A1D) 畫圓 + bg 色字 (深底紙黃) 反白.
    """
    radius = 50
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=palette["highlight"], outline=palette["primary"], width=2,
    )
    # 中央 "印" 字 — 用 default fallback font (可能含中文); 失敗就用 "DOF"
    font_size = 32
    try:
        font = _font(get_font_path(), font_size)
        text = "印"
        # 量字寬, 居中
        bbox = font.getbbox(text)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (cx - tw // 2, cy - th // 2 - 4),
            text, font=font, fill=palette["bg"],
        )
    except Exception:
        # fallback ascii
        try:
            font = _font(get_font_path(), font_size)
            text = "DOF"
            bbox = font.getbbox(text)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text(
                (cx - tw // 2, cy - th // 2),
                text, font=font, fill=palette["bg"],
            )
        except Exception:
            pass


def _draw_elven_diamond(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """燙金菱形 ✦: highlight (file_header 燙金色) 菱形 + 細線陪襯."""
    size = 36
    # 主菱形 (filled)
    diamond = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    draw.polygon(diamond, fill=palette["file_header"])
    # 外圈細線菱形 (略大)
    outer = size + 22
    outer_diamond = [
        (cx, cy - outer), (cx + outer, cy), (cx, cy + outer), (cx - outer, cy),
    ]
    draw.line(outer_diamond + [outer_diamond[0]],
              fill=palette["highlight"], width=1)
    # 三條極細水平線 (月光感)
    for dy in (-58, 0, 58):
        draw.line(
            [(cx - 80, cy + dy), (cx - outer - 10, cy + dy)],
            fill=palette["secondary"], width=1,
        )


def _draw_arcade_pixels(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """8-bit pixel: 3x3 小方塊 grid + 一條霓虹底線.

    用 highlight (霓虹青) 跟 secondary (橘黃) 交替, 像素風 HUD 圖示感.
    """
    px_size = 14
    gap = 4
    # 3x3 點陣 — 中央霓虹青, 周圍交替
    colors = [
        palette["secondary"], palette["highlight"], palette["secondary"],
        palette["highlight"], palette["highlight"], palette["highlight"],
        palette["secondary"], palette["highlight"], palette["secondary"],
    ]
    start_x = cx - (px_size + gap) * 1 - px_size // 2
    start_y = cy - (px_size + gap) * 1 - px_size // 2
    for row in range(3):
        for col in range(3):
            x0 = start_x + col * (px_size + gap)
            y0 = start_y + row * (px_size + gap)
            draw.rectangle(
                [x0, y0, x0 + px_size, y0 + px_size],
                fill=colors[row * 3 + col],
            )
    # 下方一條 highlight 霓虹線 (HUD 感)
    line_y = cy + 50
    draw.line(
        [(cx - 70, line_y), (cx + 70, line_y)],
        fill=palette["highlight"], width=2,
    )


def _draw_brutalist_warn(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """警示斜紋: highlight 色 (警示橘紅) 對角線 stripe 塊, 野獸派警告風."""
    # 100x60 區塊內畫對角線 stripe
    box_w, box_h = 110, 60
    x0 = cx - box_w // 2
    y0 = cy - box_h // 2
    # 外框 (純黑)
    draw.rectangle(
        [x0, y0, x0 + box_w, y0 + box_h],
        outline=palette["primary"], width=3,
    )
    # 內部對角斜紋
    stripe_gap = 10
    for offset in range(-box_h, box_w + box_h, stripe_gap):
        # 對角線 (左上 → 右下方向)
        line_x1 = x0 + offset
        line_y1 = y0
        line_x2 = line_x1 + box_h
        line_y2 = y0 + box_h
        # clip 到 box 內
        if line_x2 < x0 or line_x1 > x0 + box_w:
            continue
        draw.line(
            [(max(line_x1, x0), line_y1 + max(0, x0 - line_x1)),
             (min(line_x2, x0 + box_w), line_y2 - max(0, line_x2 - x0 - box_w))],
            fill=palette["highlight"], width=3,
        )


def _draw_editorial_section_mark(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette, step_idx: int,
) -> None:
    """§ N 章節符號: 大 § + 羅馬數字, 用赭橘色, 雜誌封面感.

    step_idx (slide 序號) → 羅馬數字 I-V (超過用阿拉伯).
    """
    roman = ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")
    num_str = roman[step_idx] if 1 <= step_idx <= 10 else str(step_idx)
    # § 符號 (大字)
    try:
        sec_font = _font(get_font_path(), 72)
    except Exception:
        return
    draw.text(
        (cx - 50, cy - 50), "§", font=sec_font, fill=palette["highlight"],
    )
    # 羅馬數字 (略小)
    try:
        num_font = _font(get_font_path(), 36)
        draw.text(
            (cx + 15, cy - 25), num_str, font=num_font, fill=palette["secondary"],
        )
    except Exception:
        pass


# ---------- iter 69: 補 10 個主題 signature decor ----------

def _draw_chalk_strokes(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """forest 粉筆筆觸: 3 條長短不一的水平粉筆痕, highlight 色 (黃)."""
    strokes = [
        # (x_offset_from_center, y_offset, length, thickness)
        (-50, -28, 100, 4),
        (-40, -8, 80, 3),
        (-60, 18, 110, 5),
    ]
    for x_off, y_off, length, th in strokes:
        x0 = cx + x_off
        y0 = cy + y_off
        draw.rectangle(
            [x0, y0, x0 + length, y0 + th],
            fill=palette["highlight"],
        )
    # 末端兩條極細 (淡化感)
    draw.line([(cx - 30, cy + 38), (cx + 40, cy + 38)],
              fill=palette["secondary"], width=1)


def _draw_circuit_trace(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """navy PCB 線路: 90 度折線 + 端點圓點, highlight 色 (青藍)."""
    # 3 條折線, 各有端點圓
    paths = [
        [(cx - 50, cy - 30), (cx - 50, cy), (cx + 10, cy)],
        [(cx + 30, cy - 30), (cx + 30, cy + 20), (cx + 60, cy + 20)],
        [(cx - 20, cy + 35), (cx + 40, cy + 35)],
    ]
    for path in paths:
        for i in range(len(path) - 1):
            draw.line([path[i], path[i + 1]], fill=palette["highlight"], width=3)
        # 端點圓
        for pt in (path[0], path[-1]):
            r = 5
            draw.ellipse([pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r],
                         fill=palette["highlight"])


def _draw_magic_hex(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """frieren 六角魔法陣: hex + 內接圓 + 中心點, highlight 色."""
    import math
    radius = 45
    # 六角形頂點
    hex_pts = []
    for i in range(6):
        angle = math.pi / 6 + i * math.pi / 3  # 30° + 60° increments
        hex_pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    # 外六角線
    for i in range(6):
        draw.line([hex_pts[i], hex_pts[(i + 1) % 6]],
                  fill=palette["highlight"], width=2)
    # 內接圓 (稍小)
    inner_r = 28
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        outline=palette["secondary"], width=1,
    )
    # 中心點
    draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=palette["highlight"])


def _draw_spiral_seal(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """naruto 卷軸螺旋封印: 3 圈同心圓 + 旋轉螺旋線, 焦糖 + 朱紅雙色."""
    # 同心圓 3 層
    for r, color in ((46, palette["highlight"]), (32, palette["secondary"]),
                     (18, palette["highlight"])):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                     outline=color, width=2)
    # 中心實心圓 (印章感)
    draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=palette["highlight"])
    # 漩渦短線 (4 條從中心向外旋轉)
    import math
    for i in range(4):
        angle = i * math.pi / 2
        x_end = cx + 50 * math.cos(angle)
        y_end = cy + 50 * math.sin(angle)
        draw.line([(cx, cy), (x_end, y_end)], fill=palette["secondary"], width=1)


def _draw_page_marker(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette, step_idx: int,
) -> None:
    """journal 頁碼章節: 「— N —」橫線中央夾數字, 期刊風."""
    try:
        num_font = _font(get_font_path(), 40)
    except Exception:
        return
    num_str = f"{step_idx:02d}"
    # 量字寬
    bbox = num_font.getbbox(num_str)
    tw = bbox[2] - bbox[0]
    # 中央數字
    draw.text((cx - tw // 2, cy - 20), num_str,
              font=num_font, fill=palette["primary"])
    # 左右兩條短橫線
    line_y = cy + 5
    draw.line([(cx - 60, line_y), (cx - tw // 2 - 8, line_y)],
              fill=palette["secondary"], width=2)
    draw.line([(cx + tw // 2 + 8, line_y), (cx + 60, line_y)],
              fill=palette["secondary"], width=2)


def _draw_minimal_diamond(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """podium ◆ + 細直線: TED 極簡風. 一菱形 + 旁邊垂直細線, 純文字感."""
    # 實心小菱形
    size = 14
    diamond = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    draw.polygon(diamond, fill=palette["primary"])
    # 右側細垂直線
    line_x = cx + size + 18
    draw.line([(line_x, cy - 32), (line_x, cy + 32)],
              fill=palette["secondary"], width=1)


def _draw_sticky_corner(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """notebook 便條紙折角: 矩形 + 右下角小三角形折角, 淡黃."""
    # 主矩形 (highlight 色, 便條黃)
    w, h = 110, 70
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = x0 + w, y0 + h
    draw.rectangle([x0, y0, x1, y1], fill=palette["highlight"])
    # 右下角折角三角形 (略深, secondary 色)
    fold_size = 18
    fold = [
        (x1 - fold_size, y1),       # 折角起點 (底邊)
        (x1, y1),                    # 右下角
        (x1, y1 - fold_size),       # 折角終點 (右邊)
    ]
    draw.polygon(fold, fill=palette["secondary"])
    # 折角邊線
    draw.line([(x1 - fold_size, y1), (x1, y1 - fold_size)],
              fill=palette["primary"], width=1)
    # 中央橫線 (代表筆記文字)
    for i, dy in enumerate((-15, 0, 15)):
        line_w = (40, 50, 35)[i]
        draw.line([(x0 + 12, cy + dy), (x0 + 12 + line_w, cy + dy)],
                  fill=palette["primary"], width=1)


def _draw_sticker_bang(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """zine 撞色 sticker: 大圓 (highlight 色) + 中央「!」字 (bg 色反白)."""
    radius = 45
    # 主圓 (sticker 撞色)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=palette["highlight"], outline=palette["primary"], width=3,
    )
    # 中央 ! 字 (反白)
    try:
        bang_font = _font(get_font_path(), 56)
        bbox = bang_font.getbbox("!")
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(
            (cx - tw // 2, cy - th // 2 - 6),
            "!", font=bang_font, fill=palette["bg"],
        )
    except Exception:
        pass


def _draw_riso_dots(draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette) -> None:
    """risograph 兩色錯位疊印圓點: highlight 圓 + secondary 圓 錯位疊印感.

    PIL 沒 alpha blend, 用兩個錯位實心圓 + 中央深色疊印區模擬."""
    r = 32
    # highlight 色圓 (略偏左)
    draw.ellipse(
        [cx - r - 12, cy - r, cx + r - 12, cy + r],
        fill=palette["highlight"],
    )
    # secondary 色圓 (略偏右, 疊在前一個上面)
    draw.ellipse(
        [cx - r + 12, cy - r, cx + r + 12, cy + r],
        fill=palette["secondary"],
    )
    # 中央疊印區 — 用 primary 一個小圓模擬 (兩色疊出深色)
    overlap_r = 12
    draw.ellipse(
        [cx - overlap_r, cy - overlap_r, cx + overlap_r, cy + overlap_r],
        fill=palette["primary"],
    )


def _draw_big_number(
    draw: ImageDraw.ImageDraw, cx: int, cy: int, palette: Palette, step_idx: int,
) -> None:
    """supergraphic 巨大數字: 大字「01」/「02」之類, 大色塊風."""
    try:
        big_font = _font(get_font_path(), 96)
    except Exception:
        return
    num_str = f"{step_idx:02d}"
    bbox = big_font.getbbox(num_str)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    # 整個編號往左偏一點, 露出右側
    draw.text(
        (cx - tw // 2, cy - th // 2 - 10),
        num_str, font=big_font, fill=palette["highlight"],
    )


def _draw_image_panel(
    img: Image.Image, image_path: str, y_top: int, y_bottom: int,
    palette: Palette,
) -> tuple[int | None, int]:
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


def _draw_subtitle_strip(
    draw: ImageDraw.ImageDraw,
    palette: Palette | None = None,
) -> None:
    """底部 180px 字幕帶.

    iter 68a: 接 palette 後依主題切色 (palette["banner"]). 沒給 palette
    fallback 到 SUBTITLE_STRIP (黑) 保持向後相容 — blackboard / slide
    renderer 仍用全域常數.

    為什麼用 palette["banner"]:
    - 淺底主題 (journal / editorial / brutalist / elven 等) 不再用純黑
      撞色, 改用 banner 同色系 (米色 / 警示橘紅 / 淡紫等), 視覺連貫
    - 暗底主題 (forest / navy / shinobi / arcade) 的 banner 本來就是更
      深的同色, 字幕帶仍然清楚
    - 字幕文字本身是白色帶黑邊 (ffmpeg subtitles filter 設的, 見
      pipeline.py:472 PrimaryColour=&H00FFFFFF&), 任何 band 色都讀得到
    """
    color = palette["banner"] if palette else SUBTITLE_STRIP
    draw.rectangle(
        [0, VIDEO_HEIGHT - SUBTITLE_STRIP_HEIGHT, VIDEO_WIDTH, VIDEO_HEIGHT],
        fill=color,
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
        # iter 60: body 字型依主題切 — serif 主題用 serif, 其他 sans (default)
        body_font_path = get_font_path_for_theme(theme_name)
        # iter 61: 簽名裝飾 (5 個主題: shinobi/elven/arcade/brutalist/editorial)
        signature_decor = get_signature_decor(theme_name)
        # iter 68b: bullets content layout (classic / numbered / centered)
        content_layout = get_content_layout(theme_name)
        # iter 74 (A1): per-theme metrics (字級 / 行距) — 不影響 layout 內部
        # multiplier (offset hero 1.6× 等), 只調 base.
        theme_title_size = get_theme_metric(theme_name, "title_size", TITLE_FONT_SIZE)
        theme_bullet_size = get_theme_metric(theme_name, "bullet_size", BULLET_FONT_SIZE)
        theme_line_extra = get_theme_metric(theme_name, "line_height_extra", None)
        # iter 75 (A2): per-theme margin (brutalist=40 等貼邊緣)
        theme_side_margin = get_theme_metric(theme_name, "side_margin", SIDE_MARGIN)

        img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), palette["bg"])
        draw = ImageDraw.Draw(img)

        # iter 62 + 64: 封面頁專屬 layout — 居中大字 + meta + 主題差異化
        # (reverse 主題加粗框 + 5 主題簽名徽章在右上)
        if step.get("bg_type") == "cover":
            _draw_cover_slide(
                draw, step, palette, body_font_path,
                signature_decor=signature_decor, banner_style=banner_style,
            )
            _draw_subtitle_strip(draw, palette)
            try:
                from pipeline import _overlay_teacher_photo
                _overlay_teacher_photo(img)
            except Exception:
                pass
            img.save(out_p, "PNG")
            return

        # iter 63 + 64 + 67: 結尾頁專屬 layout — 跟封面對稱 + 可選 QR codes
        if step.get("bg_type") == "outro":
            _draw_outro_slide(
                draw, step, palette, body_font_path,
                signature_decor=signature_decor, banner_style=banner_style,
                img=img,
            )
            _draw_subtitle_strip(draw, palette)
            try:
                from pipeline import _overlay_teacher_photo
                _overlay_teacher_photo(img)
            except Exception:
                pass
            img.save(out_p, "PNG")
            return

        section_title = step.get("section_title") or data.get("title", "")
        _draw_banner(draw, section_title, palette, style=banner_style, font_path=body_font_path)

        title = step.get("title", "")
        title_end_y = _draw_title(
            draw, title, palette, decor=title_decor, font_path=body_font_path,
            title_size=theme_title_size,
            side_margin=theme_side_margin,
        )
        # iter 61: 在 title 完成後畫簽名 (避免被 title 文字蓋)
        _draw_signature_decor(draw, signature_decor, palette, step_idx=step_idx)

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
            content_y = _draw_bullets(
                draw, bullets, content_y, bullets_y_max, palette,
                font_path=body_font_path, layout=content_layout,
                bullet_size=theme_bullet_size,
                line_height_extra=theme_line_extra,
                side_margin=theme_side_margin,
            )
            content_y = max(content_y, content_y_max - estimated_code_h)
            _draw_code_block(draw, img, code, file_path, content_y, content_y_max, palette)
        elif image_path:
            # split-image-right: 圖貼右側 38%, bullets 縮窄到左側
            panel_x, _ = _draw_image_panel(
                img, image_path, content_y, content_y_max, palette,
            )
            if panel_x is None:
                # image panel 失敗 → fallback 純文字
                _draw_bullets(
                    draw, bullets, content_y, content_y_max, palette,
                    font_path=body_font_path, layout=content_layout,
                    bullet_size=theme_bullet_size,
                    line_height_extra=theme_line_extra,
                )
            else:
                # bullets 寬度 = 左側到 panel_x 之間 (扣 indent)
                indent = 60
                bullet_max_w = panel_x - SIDE_MARGIN - indent - 30  # 30px gap
                _draw_bullets(
                    draw, bullets, content_y, content_y_max, palette,
                    max_text_width=bullet_max_w,
                    font_path=body_font_path, layout=content_layout,
                    bullet_size=theme_bullet_size,
                    line_height_extra=theme_line_extra,
                )
        else:
            _draw_bullets(
                draw, bullets, content_y, content_y_max, palette,
                font_path=body_font_path, layout=content_layout,
                bullet_size=theme_bullet_size,
                line_height_extra=theme_line_extra,
                side_margin=theme_side_margin,
            )

        _draw_subtitle_strip(draw, palette)
        try:
            from pipeline import _overlay_teacher_photo
            _overlay_teacher_photo(img)
        except Exception:
            pass

        img.save(out_p, "PNG")
