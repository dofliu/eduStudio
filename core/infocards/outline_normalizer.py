"""簡報大綱 AI 輸出校正（從 infoCard services/outlineNormalizer.ts 收編）。

純函式、零 API：Stage 1 大綱的 suggestedTheme/suggestedTypography/estimatedImageCount 是
外部邊界輸入，LLM 可能回不存在主題/無效字型/亂填圖片數。本層決定性校正成合法值，
並把三方案的 suggestedTheme 統一為使用者選定主題（可控版型系統）。
"""
from __future__ import annotations

from core.infocards.presentation_themes import PRESENTATION_THEMES

VALID_TYPOGRAPHY = ("modern", "classic", "mono", "handwriting")
_DEFAULT_THEME = "professional"
_DEFAULT_TYPOGRAPHY = "modern"
_CUSTOM_STYLE = "custom"


def _is_valid_theme(theme) -> bool:
    return isinstance(theme, str) and theme in PRESENTATION_THEMES


def normalize_theme(theme, fallback: str = _DEFAULT_THEME) -> str:
    if _is_valid_theme(theme):
        return theme
    if _is_valid_theme(fallback):
        return fallback
    return _DEFAULT_THEME


def normalize_typography(typo) -> str:
    return typo if typo in VALID_TYPOGRAPHY else _DEFAULT_TYPOGRAPHY


def normalize_estimated_image_count(count, slide_count: int) -> int:
    """非負整數，夾在 [0, slideCount]。AI 偶回浮點/負數/超量會誤導費用估算。"""
    upper = max(0, int(slide_count))
    n = int(count) if isinstance(count, (int, float)) and count == count else 0  # NaN→0
    return min(max(0, n), upper)


def resolve_selected_theme(selected_style) -> str:
    """custom（自由文字風格）原樣保留（下游用 customStylePrompt）；否則校正成合法主題。"""
    return _CUSTOM_STYLE if selected_style == _CUSTOM_STYLE else normalize_theme(selected_style)


def apply_selected_theme(outlines: list[dict], selected_style: str = _DEFAULT_THEME) -> list[dict]:
    """三方案統一沿用使用者選定主題（差異只留 layout/敘事，非配色）。"""
    theme = resolve_selected_theme(selected_style)
    for o in outlines:
        o["suggestedTheme"] = theme
    return outlines


def normalize_outlines(outlines: list[dict], selected_style: str = _DEFAULT_THEME) -> list[dict]:
    """整批大綱決定性校正：typography/estimatedImageCount 合法化 + 主題統一。"""
    for o in outlines:
        o["suggestedTypography"] = normalize_typography(o.get("suggestedTypography"))
        o["estimatedImageCount"] = normalize_estimated_image_count(
            o.get("estimatedImageCount"), len(o.get("slides") or []))
    return apply_selected_theme(outlines, selected_style)
