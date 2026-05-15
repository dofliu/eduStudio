"""core/render/pptx_style.py — iter 53 split-image-right layout.

只測 render() 不炸 + 圖被讀到 (產出 PNG 含圖案). 排版細節 (邊距 / 縮放) 留實機看.
- 真畫 PIL Image 不開 ffmpeg
- 用 tmp PNG 當 figure 來源
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from core.render.pptx_style import (
    PptxStyleRenderer,
    _draw_image_panel,
    get_palette,
)


@pytest.fixture
def fake_figure(tmp_path):
    """產一張 400x300 紅色測試 PNG."""
    def _make(name: str = "fig_test.png", w: int = 400, h: int = 300,
              color: tuple[int, int, int] = (220, 60, 60)) -> Path:
        p = tmp_path / name
        Image.new("RGB", (w, h), color=color).save(p, "PNG")
        return p
    return _make


# ---------- _draw_image_panel 純函式 ----------


class TestDrawImagePanel:
    def test_missing_file_returns_none(self, tmp_path):
        canvas = Image.new("RGB", (1920, 1080), (30, 30, 30))
        palette = get_palette("forest")
        panel_x, panel_w = _draw_image_panel(
            canvas, str(tmp_path / "nope.png"), 200, 900, palette,
        )
        assert panel_x is None
        assert panel_w == 0

    def test_valid_image_returns_panel_x(self, fake_figure):
        canvas = Image.new("RGB", (1920, 1080), (30, 30, 30))
        palette = get_palette("forest")
        path = fake_figure()
        panel_x, panel_w = _draw_image_panel(
            canvas, str(path), 200, 900, palette,
        )
        # 應該得到 panel 座標
        assert panel_x is not None
        # panel 在右側, x 應該超過畫面一半
        assert panel_x > 960
        assert panel_w > 0

    def test_too_narrow_region_returns_none(self, fake_figure):
        """y 區間太窄 (高度 < 100) 該 fallback 不畫."""
        canvas = Image.new("RGB", (1920, 1080), (30, 30, 30))
        palette = get_palette("forest")
        path = fake_figure()
        panel_x, panel_w = _draw_image_panel(
            canvas, str(path), 500, 550, palette,
        )
        assert panel_x is None

    def test_image_pasted_on_canvas(self, fake_figure):
        """畫完後該位置的 pixel 不應該是純背景色."""
        bg = (30, 30, 30)
        canvas = Image.new("RGB", (1920, 1080), bg)
        palette = get_palette("forest")
        path = fake_figure(color=(220, 60, 60))   # 紅
        _draw_image_panel(canvas, str(path), 200, 900, palette)
        # 在 panel 中央找紅色 pixel
        sample_x = 1920 - 200 - 100   # 約 panel 中央
        sample_y = 550
        pixel = canvas.getpixel((sample_x, sample_y))
        # 應該是紅色 (容忍 LANCZOS resize 抗鋸齒微小偏差)
        r, g, b = pixel
        assert r > 150, f"expected red dominant, got {pixel}"
        assert r > g and r > b


# ---------- render() 整合 ----------


class TestRendererImageIntegration:
    """render() 三條 layout 分流 (text / image / code), 不炸 + PNG 產出."""

    def _make_data(self, **step_overrides) -> dict:
        step = {
            "title": "測試標題",
            "section_title": "測試章節",
            "bullets": ["第一點", "第二點"],
            "code_snippet": None,
            "file_path": None,
            "image_path": None,
            "narration": "測試旁白",
            "bg_type": "pptx_slide",
        }
        step.update(step_overrides)
        return {"title": "測試 deck", "theme": "forest", "steps": [step]}

    def test_text_only_layout_renders(self, tmp_path):
        renderer = PptxStyleRenderer()
        out = tmp_path / "out.png"
        renderer.render(self._make_data(), 1, out, tmp_path)
        assert out.exists()
        # 該是 1920x1080 PNG
        with Image.open(out) as img:
            assert img.size == (1920, 1080)

    def test_image_layout_renders_with_figure(self, fake_figure, tmp_path):
        """有 image_path → split-image-right layout, 不炸 + PNG 產出."""
        renderer = PptxStyleRenderer()
        fig_path = fake_figure(color=(220, 60, 60))
        out = tmp_path / "out_img.png"
        renderer.render(
            self._make_data(image_path=str(fig_path)),
            1, out, tmp_path,
        )
        assert out.exists()
        # 該畫面右側中央區域該有圖 (紅色 pixel dominant)
        with Image.open(out) as img:
            # 右側 38% 區內取樣
            sample_x = 1920 - 250
            sample_y = 540
            pixel = img.getpixel((sample_x, sample_y))
            r, g, b = pixel
            assert r > 150 and r > g and r > b, (
                f"expected red figure in panel area, got {pixel}"
            )

    def test_image_path_missing_file_fallback_to_text(self, tmp_path):
        """image_path 設了但檔案不存在 → 退回純文字, 不炸."""
        renderer = PptxStyleRenderer()
        out = tmp_path / "out_missing.png"
        renderer.render(
            self._make_data(image_path=str(tmp_path / "does_not_exist.png")),
            1, out, tmp_path,
        )
        assert out.exists()

    def test_code_overrides_image(self, fake_figure, tmp_path):
        """code_snippet + image_path 同時存在 → code 優先 (iter 53 設計)."""
        renderer = PptxStyleRenderer()
        fig_path = fake_figure(color=(220, 60, 60))
        out = tmp_path / "out_both.png"
        renderer.render(
            self._make_data(
                code_snippet="def foo():\n    pass",
                code_lang="python",
                image_path=str(fig_path),
            ),
            1, out, tmp_path,
        )
        assert out.exists()
        # code 走原 layout, image 不該出現. 但很難穩定 assert 圖沒被畫,
        # 至少確認 PNG 產得出來, 跟 code-only 一致.
