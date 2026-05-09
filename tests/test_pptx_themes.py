"""PR-5a Forest / Navy 主題色票測試 — 只測 THEMES dict 跟 get_palette,
不實際畫圖 (要實機 + 字型才能跑, 留 integration test)."""
from __future__ import annotations

import pytest

from core.render.pptx_style import DEFAULT_THEME, THEMES, get_palette


REQUIRED_KEYS = {
    "bg", "banner", "code_bg", "code_border",
    "primary", "highlight", "secondary", "file_header",
}


class TestThemes:
    def test_default_is_forest(self):
        assert DEFAULT_THEME == "forest"

    def test_has_forest_and_navy(self):
        assert "forest" in THEMES
        assert "navy" in THEMES

    def test_each_theme_has_required_keys(self):
        for name, palette in THEMES.items():
            missing = REQUIRED_KEYS - set(palette.keys())
            assert not missing, f"theme {name} 缺欄位: {missing}"

    def test_each_color_is_rgb_tuple(self):
        for name, palette in THEMES.items():
            for key, value in palette.items():
                assert isinstance(value, tuple) and len(value) == 3, (
                    f"theme {name} 的 {key} 不是 RGB tuple: {value}"
                )
                for ch in value:
                    assert 0 <= ch <= 255, f"theme {name}.{key} 顏色超出範圍"


class TestGetPalette:
    def test_returns_forest_when_none(self):
        assert get_palette(None) is THEMES["forest"]

    def test_returns_forest_when_empty(self):
        assert get_palette("") is THEMES["forest"]

    def test_returns_forest_for_unknown(self):
        # 未知 theme 名退到預設, 不丟例外 (容錯)
        assert get_palette("midnight") is THEMES["forest"]

    def test_returns_navy_when_navy(self):
        assert get_palette("navy") is THEMES["navy"]

    def test_returns_forest_when_forest_explicit(self):
        assert get_palette("forest") is THEMES["forest"]


class TestPaletteContrast:
    """sanity check: 主背景跟主色至少有顯著亮度差, 不會看不見."""

    def _luma(self, rgb: tuple[int, int, int]) -> float:
        # Rec. 601 luma
        return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]

    @pytest.mark.parametrize("theme", list(THEMES.keys()))
    def test_primary_is_lighter_than_bg(self, theme: str):
        p = THEMES[theme]
        assert self._luma(p["primary"]) > self._luma(p["bg"]) + 100, (
            f"{theme} primary 跟 bg 對比不足"
        )

    @pytest.mark.parametrize("theme", list(THEMES.keys()))
    def test_highlight_distinct_from_primary(self, theme: str):
        p = THEMES[theme]
        # highlight 跟 primary 顏色明顯不同 (R/G/B 至少一通道差 > 30)
        diff = max(
            abs(p["highlight"][i] - p["primary"][i]) for i in range(3)
        )
        assert diff > 30, f"{theme} highlight 跟 primary 太接近"
