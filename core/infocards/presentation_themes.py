"""簡報視覺主題（從 infoCard data/presentationThemes.ts 收編，Phase C presentation）。

只取後端 generatePresentation 用到的欄位（id/accent/accentSecondary/bgBase/description）；
PPTX 專用的 fontScale/spacingScale/gradient 等待 PPTX 匯出 PR 再補。get_theme_by_style 對齊
原版：找不到退 professional。
"""
from __future__ import annotations

# id → 主題色彩（accent 主色 / accentSecondary 次強調 / bgBase 背景 / description 風格描述）。
PRESENTATION_THEMES: dict[str, dict] = {
    "professional": {"id": "professional", "accent": "#1e40af", "accentSecondary": "#d4a853", "bgBase": "#ffffff", "description": "沉穩深藍配金色強調，適合正式報告與提案"},
    "minimalist": {"id": "minimalist", "accent": "#18181b", "accentSecondary": "#f97316", "bgBase": "#fafafa", "description": "大量留白、黑白為主，一抹亮色點綴"},
    "digital": {"id": "digital", "accent": "#06b6d4", "accentSecondary": "#a855f7", "bgBase": "#0f172a", "description": "暗色主題搭配霓虹藍綠，適合科技與數據主題"},
    "vibrant": {"id": "vibrant", "accent": "#7c3aed", "accentSecondary": "#f59e0b", "bgBase": "#ffffff", "description": "大膽撞色搭配動態幾何，適合創意與行銷"},
    "nature": {"id": "nature", "accent": "#059669", "accentSecondary": "#d97706", "bgBase": "#f0fdf4", "description": "綠色系配大地色，適合教育與環境主題"},
    "academic": {"id": "academic", "accent": "#991b1b", "accentSecondary": "#b8860b", "bgBase": "#fffbeb", "description": "深紅配金色邊框，適合學術發表與講座"},
    "pastel": {"id": "pastel", "accent": "#ec4899", "accentSecondary": "#8b5cf6", "bgBase": "#fdf2f8", "description": "粉嫩色調搭配圓潤排版，適合教學與生活主題"},
    "ocean": {"id": "ocean", "accent": "#0369a1", "accentSecondary": "#f97316", "bgBase": "#f0f9ff", "description": "深海藍搭配珊瑚色，清爽專業又不失活力"},
    "sunset": {"id": "sunset", "accent": "#ea580c", "accentSecondary": "#dc2626", "bgBase": "#fff7ed", "description": "橘紅漸層搭配深棕，溫暖有感染力"},
    "lavender": {"id": "lavender", "accent": "#7c3aed", "accentSecondary": "#06b6d4", "bgBase": "#faf5ff", "description": "紫色系搭配銀灰，優雅沉靜適合藝術與人文"},
    "cyberpunk": {"id": "cyberpunk", "accent": "#e11d48", "accentSecondary": "#22d3ee", "bgBase": "#000000", "description": "純黑底搭配霓虹粉綠，適合遊戲與科幻主題"},
    "forest": {"id": "forest", "accent": "#166534", "accentSecondary": "#ca8a04", "bgBase": "#f0fdf4", "description": "沉穩深綠配暖金，適合課堂教學與學術講座"},
    "navy": {"id": "navy", "accent": "#1e3a5f", "accentSecondary": "#38bdf8", "bgBase": "#f8fafc", "description": "海軍藍搭配天藍亮色，適合科技與工程簡報"},
    "frieren": {"id": "frieren", "accent": "#7c3aed", "accentSecondary": "#34d399", "bgBase": "#faf5ff", "description": "魔法紫配精靈綠，奇幻優雅適合創意與人文主題"},
    "naruto": {"id": "naruto", "accent": "#ea580c", "accentSecondary": "#dc2626", "bgBase": "#fff7ed", "description": "火焰橘配赤紅，熱血有衝勁適合激勵與活動"},
    "earth": {"id": "earth", "accent": "#78350f", "accentSecondary": "#4d7c0f", "bgBase": "#fefce8", "description": "棕色與橄欖綠，沉穩自然適合戶外與永續主題"},
}

_DEFAULT = "professional"


def get_theme_by_style(style: str) -> dict:
    """對齊 infoCard getThemeByStyle：找不到（含 custom）退 professional。"""
    return PRESENTATION_THEMES.get(style, PRESENTATION_THEMES[_DEFAULT])
