"""LaTeX 公式疊放 — 三大 renderer 整合測試 (2026-06-04).

接 core/formula_render.py compose_formula (單元測試在 test_formula_render.py)。
這裡走完整 render path, 驗 4 個 seam 真的接上 compose_formula:
- BlackboardRenderer (pipeline.py)
- SlideRenderer full layout (pipeline.py)
- PptxStyleRenderer normal layout (core/render/pptx_style.py, 集中 4 路 layout)

策略: 同一 renderer 渲「有 formula」與「無 formula」兩版, 比 formula 落點區域
是否不同 (robust — 不假設主題背景顏色)。再驗無 formula 欄位向後相容。
"""
from __future__ import annotations

import pytest

pytest.importorskip("matplotlib")  # 公式渲染需要 matplotlib (已升核心依賴)

from PIL import Image  # noqa: E402

# 公式放 top-right, size_ratio 0.2 → 落在右上角這塊區域 (主題內容通常不佔)
_FORMULA = {
    "latex": r"\sigma = \frac{F}{A}",
    "position": "top-right",
    "size_ratio": 0.2,
    "color": "white",
}
_TOP_RIGHT_BOX = (1450, 30, 1900, 300)


def _region_pixels(path, box):
    with Image.open(path) as im:
        return list(im.convert("RGB").crop(box).getdata())


def _region_has_bright(path, box, thresh=150):
    with Image.open(path) as im:
        return im.convert("L").crop(box).getextrema()[1] > thresh


class TestBlackboardFormula:
    def _data(self, with_formula: bool) -> dict:
        step: dict = {"display": "step 顯示", "narration": "n"}
        if with_formula:
            step["formula"] = dict(_FORMULA)
        return {
            "title": "T", "subtitle": "S", "problem": "問題",
            "image": None, "steps": [step],
        }

    def test_formula_changes_top_right_region(self, tmp_path):
        pipeline = pytest.importorskip("pipeline")
        renderer = pipeline.BlackboardRenderer()
        with_f = tmp_path / "bb_f.png"
        without_f = tmp_path / "bb_plain.png"
        renderer.render(self._data(True), 1, with_f, tmp_path)
        renderer.render(self._data(False), 1, without_f, tmp_path)
        assert with_f.exists() and without_f.exists()
        # 有公式版該在右上多出白色公式像素
        assert _region_has_bright(with_f, _TOP_RIGHT_BOX)
        assert _region_pixels(with_f, _TOP_RIGHT_BOX) != _region_pixels(
            without_f, _TOP_RIGHT_BOX
        )

    def test_no_formula_key_still_renders(self, tmp_path):
        pipeline = pytest.importorskip("pipeline")
        renderer = pipeline.BlackboardRenderer()
        out = tmp_path / "bb_nokey.png"
        renderer.render(self._data(False), 1, out, tmp_path)
        assert out.exists()


class TestSlideRendererFormula:
    def _data(self, with_formula: bool) -> dict:
        step: dict = {
            "display": "投影片標題", "narration": "旁白",
            "layout": "full", "bullets": ["重點一"],
        }
        if with_formula:
            step["formula"] = dict(_FORMULA)
        return {"steps": [step], "meta": {}}

    def test_formula_paints_on_black_canvas(self, tmp_path):
        """SlideRenderer 無 bg → 黑底, 白公式該在右上留下明亮像素."""
        import pipeline
        renderer = pipeline.SlideRenderer()
        out = tmp_path / "slide_f.png"
        renderer.render(self._data(True), step_idx=1, out_p=str(out), q_work=None)
        assert out.exists()
        assert _region_has_bright(out, _TOP_RIGHT_BOX)

    def test_no_formula_top_right_stays_black(self, tmp_path):
        """無 formula → 右上仍純黑 (compose_formula NoOp, 不誤畫)."""
        import pipeline
        renderer = pipeline.SlideRenderer()
        out = tmp_path / "slide_plain.png"
        renderer.render(self._data(False), step_idx=1, out_p=str(out), q_work=None)
        assert out.exists()
        assert not _region_has_bright(out, _TOP_RIGHT_BOX)


class TestPptxStyleFormula:
    def _data(self, with_formula: bool) -> dict:
        step: dict = {
            "title": "T", "section_title": "S", "bullets": ["b1"],
            "narration": "n", "bg_type": "pptx_slide", "image_path": None,
            "code_snippet": None, "file_path": None,
        }
        if with_formula:
            step["formula"] = dict(_FORMULA)
        return {"title": "deck", "theme": "forest", "steps": [step]}

    def test_formula_changes_top_right_region(self, tmp_path):
        from core.render.pptx_style import PptxStyleRenderer
        renderer = PptxStyleRenderer()
        with_f = tmp_path / "pptx_f.png"
        without_f = tmp_path / "pptx_plain.png"
        renderer.render(self._data(True), 1, with_f, tmp_path)
        renderer.render(self._data(False), 1, without_f, tmp_path)
        assert with_f.exists() and without_f.exists()
        assert _region_pixels(with_f, _TOP_RIGHT_BOX) != _region_pixels(
            without_f, _TOP_RIGHT_BOX
        )

    def test_no_formula_key_still_renders(self, tmp_path):
        from core.render.pptx_style import PptxStyleRenderer
        renderer = PptxStyleRenderer()
        out = tmp_path / "pptx_nokey.png"
        renderer.render(self._data(False), 1, out, tmp_path)
        assert out.exists()
