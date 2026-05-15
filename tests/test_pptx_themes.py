"""PR-5a Forest / Navy 主題色票測試 — 只測 THEMES dict 跟 get_palette,
不實際畫圖 (要實機 + 字型才能跑, 留 integration test)."""
from __future__ import annotations

import pytest

from core.render.pptx_style import (
    DEFAULT_THEME,
    THEME_BANNER_STYLES,
    THEMES,
    get_banner_style,
    get_palette,
)


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


# ---------- iter 58: banner_style ----------


class TestBannerStyle:
    """每主題該有對應 banner style, 不認識的 theme fallback 到 rectangle."""

    VALID_STYLES = {"rectangle", "hairline", "reverse", "neon"}

    def test_default_is_rectangle(self):
        assert get_banner_style(None) == "rectangle"
        assert get_banner_style("") == "rectangle"

    def test_unknown_theme_fallback(self):
        assert get_banner_style("not_a_theme") == "rectangle"

    @pytest.mark.parametrize("theme", list(THEMES.keys()))
    def test_every_theme_has_valid_style(self, theme: str):
        """每張現存主題該對到 4 種有效 style 之一."""
        style = get_banner_style(theme)
        assert style in self.VALID_STYLES, (
            f"{theme} banner_style={style!r} 不在 {self.VALID_STYLES}"
        )

    def test_styles_have_meaningful_distribution(self):
        """15 主題不該全 rectangle (那就沒個性化效果). 至少 3 種 style 在用."""
        styles_in_use = {
            get_banner_style(t) for t in THEMES.keys()
        }
        assert len(styles_in_use) >= 3, (
            f"banner_style 多樣性不夠: {styles_in_use}"
        )

    def test_brutalist_uses_reverse(self):
        """野獸派該用 reverse — 反白色塊是其招牌."""
        assert get_banner_style("dof-brutalist") == "reverse"

    def test_arcade_uses_neon(self):
        """街機霓虹該用 neon — 發光感是其招牌."""
        assert get_banner_style("dof-arcade") == "neon"

    def test_journal_uses_hairline(self):
        """期刊風該用 hairline — 學術極簡."""
        assert get_banner_style("journal") == "hairline"

    def test_legacy_themes_still_rectangle(self):
        """forest / navy / frieren / naruto 維持 rectangle 不變 (backwards compat)."""
        for legacy in ("forest", "navy", "frieren", "naruto"):
            assert get_banner_style(legacy) == "rectangle", (
                f"{legacy} 應保留原 rectangle style 不該被誤改"
            )
