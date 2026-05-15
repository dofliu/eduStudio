"""PR-5a Forest / Navy 主題色票測試 — 只測 THEMES dict 跟 get_palette,
不實際畫圖 (要實機 + 字型才能跑, 留 integration test)."""
from __future__ import annotations

import pytest

from core.render.pptx_style import (
    DEFAULT_THEME,
    SERIF_FONT_CANDIDATES,
    THEME_BANNER_STYLES,
    THEME_FONT_ROLES,
    THEME_TITLE_DECORS,
    THEMES,
    _resolve_serif_font,
    get_banner_style,
    get_font_path_for_theme,
    get_palette,
    get_title_decor,
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


# ---------- iter 59: title_decor ----------


class TestTitleDecor:
    VALID_DECORS = {"underline", "block", "hairline", "reverse"}

    def test_default_is_underline(self):
        assert get_title_decor(None) == "underline"
        assert get_title_decor("") == "underline"

    def test_unknown_theme_fallback(self):
        assert get_title_decor("not_a_theme") == "underline"

    @pytest.mark.parametrize("theme", list(THEMES.keys()))
    def test_every_theme_has_valid_decor(self, theme: str):
        decor = get_title_decor(theme)
        assert decor in self.VALID_DECORS, (
            f"{theme} title_decor={decor!r} 不在 {self.VALID_DECORS}"
        )

    def test_decor_diversity(self):
        """15 主題不該全 underline. 至少 3 種在用."""
        decors_in_use = {get_title_decor(t) for t in THEMES.keys()}
        assert len(decors_in_use) >= 3, f"title_decor 多樣性不足: {decors_in_use}"

    def test_brutalist_uses_reverse(self):
        """野獸派該用 reverse (反白色塊招牌)."""
        assert get_title_decor("dof-brutalist") == "reverse"

    def test_legacy_themes_still_underline(self):
        """forest / navy / frieren / naruto 維持 underline (backwards compat)."""
        for legacy in ("forest", "navy", "frieren", "naruto"):
            assert get_title_decor(legacy) == "underline", (
                f"{legacy} 應保留原 underline decor"
            )

    def test_journal_uses_hairline(self):
        """期刊風該用 hairline 學術細線."""
        assert get_title_decor("journal") == "hairline"

    def test_editorial_uses_block(self):
        """雜誌風該用 block (§ 符號感)."""
        assert get_title_decor("dof-editorial") == "block"


# ---------- iter 60: font_role per theme ----------


class TestFontRole:
    """serif 主題用 serif font, 其他維持 default sans."""

    def test_default_theme_uses_sans(self):
        """forest (default) 該用 default sans path."""
        from core.config import get_font_path
        assert get_font_path_for_theme("forest") == get_font_path()

    def test_unknown_theme_uses_sans(self):
        from core.config import get_font_path
        assert get_font_path_for_theme("not_a_theme") == get_font_path()
        assert get_font_path_for_theme(None) == get_font_path()

    def test_serif_themes_listed(self):
        """5 個 serif 主題該都在 THEME_FONT_ROLES 內標 'serif'."""
        for theme in ("journal", "dof-editorial", "dof-podium",
                      "dof-notebook", "dof-elven"):
            assert THEME_FONT_ROLES.get(theme) == "serif", (
                f"{theme} 該標 serif"
            )

    def test_serif_themes_get_serif_path(self):
        """serif 主題 get_font_path_for_theme 該回非 default sans 路徑
        (如果系統有 serif font; 沒就回 default fallback)."""
        from core.config import get_font_path
        default = get_font_path()
        serif_path = get_font_path_for_theme("journal")
        # 系統有 Noto Serif TC 或 mingliu 時, 該回非 default 路徑
        import os
        if any(os.path.exists(p) for p in SERIF_FONT_CANDIDATES):
            assert serif_path != default, (
                "系統有 serif font 但 get_font_path_for_theme 卻回 default"
            )
        else:
            # 沒 serif font 時 fallback 到 default 也算正常
            assert serif_path == default

    def test_resolve_serif_font_returns_existing_path(self):
        """_resolve_serif_font 該回實際存在的路徑 (有 serif 時) 或 default fallback."""
        import os
        path = _resolve_serif_font()
        assert os.path.exists(path), f"serif font path {path} 不存在"

    def test_non_serif_legacy_themes_default(self):
        """forest / navy / frieren / naruto / shinobi 這些非 serif 主題該 default."""
        for theme in ("forest", "navy", "frieren", "naruto", "dof-shinobi",
                      "dof-zine", "dof-arcade", "dof-risograph",
                      "dof-supergraphic", "dof-brutalist"):
            # 不在 THEME_FONT_ROLES 內或標 "sans"
            role = THEME_FONT_ROLES.get(theme, "sans")
            assert role == "sans", f"{theme} 該是 sans, 卻是 {role!r}"
