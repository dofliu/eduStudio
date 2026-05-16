"""iter 74 (A1, claude design 04): per-theme 字級 / 行距 metrics dispatch."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

import pipeline
from core.render.pptx_style import (
    THEME_METRICS,
    TITLE_FONT_SIZE,
    BULLET_FONT_SIZE,
    get_theme_metric,
)


class TestThemeMetricsDispatch:
    """get_theme_metric 對 mapping 該對, 沒設用 default."""

    def test_unknown_theme_returns_default(self):
        assert get_theme_metric(None, "title_size", TITLE_FONT_SIZE) == TITLE_FONT_SIZE
        assert get_theme_metric("nonexistent", "title_size", 999) == 999

    def test_brutalist_has_bigger_title(self):
        """brutalist 該超大字 (>= 80)."""
        size = get_theme_metric("dof-brutalist", "title_size", TITLE_FONT_SIZE)
        assert size > TITLE_FONT_SIZE
        assert size >= 80

    def test_supergraphic_has_biggest_title(self):
        """supergraphic 大色塊風 該最大字 (>= 90)."""
        size = get_theme_metric("dof-supergraphic", "title_size", TITLE_FONT_SIZE)
        assert size >= 90

    def test_journal_has_extra_line_height(self):
        """journal 學術風 該大行距 (>= 20)."""
        extra = get_theme_metric("journal", "line_height_extra", 16)
        assert extra > 16

    def test_podium_has_narrow_content(self):
        """podium 講壇風 該內容寬度縮窄 (<= 0.8)."""
        ratio = get_theme_metric("dof-podium", "content_width_ratio", 1.0)
        assert ratio < 1.0
        assert ratio <= 0.80

    def test_forest_keeps_defaults(self):
        """forest / navy 等教學主題該不在 METRICS 表 (用全域 default)."""
        assert "forest" not in THEME_METRICS
        assert "navy" not in THEME_METRICS

    def test_metrics_have_known_keys_only(self):
        """所有 METRICS 設定該只用已知 keys, 防 typo."""
        known_keys = {
            "title_size", "bullet_size", "line_height_extra",
            "side_margin", "content_width_ratio",
        }
        for theme, metrics in THEME_METRICS.items():
            for key in metrics.keys():
                assert key in known_keys, (
                    f"{theme} 用了未知 metric key {key!r}"
                )


def _render(theme: str, tmp_path: Path) -> Image.Image:
    """渲一張帶 title + bullets 的 slide."""
    out = tmp_path / f"{theme}.png"
    data = {
        "theme": theme,
        "steps": [{
            "bg_type": "pptx_slide",
            "title": "字級測試 ABC",
            "section_title": "Section",
            "bullets": ["AAA", "BBB", "CCC"],
            "code_snippet": None, "code_lang": None,
            "file_path": None, "image_path": None,
            "narration": "n",
        }],
    }
    pipeline.render_frame(data, 1, out, tmp_path)
    return Image.open(out).convert("RGB")


class TestRendersWithMetrics:
    """套用 METRICS 後 15 主題都該正常 render 不 raise."""

    THEMES_WITH_METRICS = list(THEME_METRICS.keys())

    @pytest.mark.parametrize("theme", THEMES_WITH_METRICS)
    def test_metric_theme_renders(self, theme):
        with TemporaryDirectory() as td:
            img = _render(theme, Path(td))
            assert img.size == (1920, 1080)

    def test_supergraphic_title_uses_bigger_font(self):
        """supergraphic title 字級 96 該佔比 forest (64) 更高範圍.

        brutalist 用 reverse title decor (反白文字), 採點不適合. supergraphic
        也是 reverse 但用 title=96 + 大色塊填滿, 該佔 row 範圍很廣.
        驗法: title region (y 100-280) 非 bg 色像素數量 supergraphic > forest.
        """
        with TemporaryDirectory() as td:
            from core.render.pptx_style import get_palette
            forest_img = _render("forest", Path(td))
            sg_img = _render("dof-supergraphic", Path(td))
            f_bg = get_palette("forest")["bg"]
            s_bg = get_palette("dof-supergraphic")["bg"]
            f_non_bg = 0
            s_non_bg = 0
            for y in range(100, 280, 5):
                for x in range(80, 1200, 5):
                    fp = forest_img.getpixel((x, y))
                    if any(abs(fp[i] - f_bg[i]) > 30 for i in range(3)):
                        f_non_bg += 1
                    sp = sg_img.getpixel((x, y))
                    if any(abs(sp[i] - s_bg[i]) > 30 for i in range(3)):
                        s_non_bg += 1
            # supergraphic 大字 + 反白色塊填 → 非 bg 像素該明顯多於 forest
            assert s_non_bg > f_non_bg * 1.3, (
                f"supergraphic 大字大色塊該佔更多非-bg 區塊, "
                f"forest={f_non_bg} supergraphic={s_non_bg}"
            )
