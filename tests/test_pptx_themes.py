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

    def test_has_jliu_extra_three_themes(self):
        """iter 28: 從 pptx-jliu-style 移植 Frieren / Naruto / Journal."""
        assert "frieren" in THEMES
        assert "naruto" in THEMES
        assert "journal" in THEMES

    def test_has_doflab_v1_themes(self):
        """iter 44: v1 沉穩家族 5 套 (editorial / podium / notebook / shinobi / elven)."""
        for name in (
            "dof-editorial", "dof-podium", "dof-notebook",
            "dof-shinobi", "dof-elven",
        ):
            assert name in THEMES, f"v1 主題 {name} 缺"

    def test_has_doflab_v2_themes(self):
        """iter 44: v2 衝擊家族 5 套 (zine / arcade / risograph / supergraphic / brutalist)."""
        for name in (
            "dof-zine", "dof-arcade", "dof-risograph",
            "dof-supergraphic", "dof-brutalist",
        ):
            assert name in THEMES, f"v2 主題 {name} 缺"

    def test_total_theme_count(self):
        """iter 44: 5 既有 + 10 dof-* = 15 套."""
        assert len(THEMES) == 15

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
    def test_primary_contrasts_with_bg(self, theme: str):
        """主色跟背景至少有顯著亮度差 — 雙向 (深底亮字 / 淺底深字 都接受).

        Journal 主題 (iter 28) 是淺底深字, 需用絕對亮度差。
        """
        p = THEMES[theme]
        assert abs(self._luma(p["primary"]) - self._luma(p["bg"])) > 100, (
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
