"""core/formula_render.py — LaTeX mathtext → 透明 PNG 渲染測試.

設計文件: docs/latex-formula-rendering-proposal.md。matplotlib 已於
2026-06-04 升為核心依賴 (requirements + CI), 故這些測試在 CI 直接跑
(非 skip)。若部署環境真的缺 matplotlib, render_latex_to_png 仍 graceful
回 False — 但測試環境保證有, 所以這裡驗「成功路徑」與「壞輸入回 False」。
"""
from __future__ import annotations

import pytest

from core.formula_render import (
    DEFAULT_COLOR,
    DEFAULT_DPI,
    render_latex_to_png,
)

# matplotlib 是核心依賴, 但保險起見缺了就 skip 整檔 (不讓 import error 拖垮 collection)
pytest.importorskip("matplotlib")

from PIL import Image  # noqa: E402  (在 importorskip 後)


def _png_size(path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size


class TestRenderSuccess:
    def test_valid_formula_writes_nonempty_png(self, tmp_path):
        out = tmp_path / "f.png"
        ok = render_latex_to_png(r"\sigma = \frac{F}{A}", out)
        assert ok is True
        assert out.exists()
        assert out.stat().st_size > 0

    def test_output_is_rgba_with_transparency(self, tmp_path):
        """透明背景 — 疊深色 slide 不帶白底方塊。至少有一個全透明像素。"""
        out = tmp_path / "f.png"
        assert render_latex_to_png(r"M = \frac{wL^2}{8}", out) is True
        with Image.open(out) as im:
            rgba = im.convert("RGBA")
            alphas = rgba.getchannel("A").getdata()
        assert min(alphas) == 0  # 角落該全透明

    def test_already_wrapped_dollar_not_double_wrapped(self, tmp_path):
        """已自帶 $...$ 不重複包 (雙包會變字面 $ 顯示而非數學模式)。"""
        out = tmp_path / "f.png"
        assert render_latex_to_png(r"$x^2 + y^2$", out) is True
        assert out.stat().st_size > 0

    def test_greek_and_subscript(self, tmp_path):
        """希臘字母 + 上下標 — 材力常用 (δ_max, ε)。"""
        out = tmp_path / "f.png"
        assert render_latex_to_png(r"\delta_{max} = \frac{5wL^4}{384EI}", out) is True
        assert out.stat().st_size > 0


class TestRenderFailureGraceful:
    def test_empty_string_returns_false(self, tmp_path):
        out = tmp_path / "f.png"
        assert render_latex_to_png("", out) is False
        assert not out.exists()

    def test_whitespace_only_returns_false(self, tmp_path):
        out = tmp_path / "f.png"
        assert render_latex_to_png("   \n  ", out) is False
        assert not out.exists()

    def test_none_returns_false(self, tmp_path):
        out = tmp_path / "f.png"
        assert render_latex_to_png(None, out) is False  # type: ignore[arg-type]

    def test_broken_latex_returns_false_no_raise(self, tmp_path):
        """壞 mathtext (`\\frac{` 不完整) 不該炸 — 回 False, 該 slide 退無公式。"""
        out = tmp_path / "f.png"
        # 不可 raise
        result = render_latex_to_png(r"\frac{", out)
        assert result is False


class TestRenderParams:
    def test_parent_dir_created(self, tmp_path):
        """out_path parent 不存在時自動建。"""
        out = tmp_path / "nested" / "deep" / "f.png"
        assert render_latex_to_png(r"a + b", out) is True
        assert out.exists()

    def test_higher_dpi_yields_larger_image(self, tmp_path):
        """dpi 透傳生效 — 高 dpi 同公式像素更大。"""
        lo = tmp_path / "lo.png"
        hi = tmp_path / "hi.png"
        assert render_latex_to_png(r"E = mc^2", lo, dpi=100) is True
        assert render_latex_to_png(r"E = mc^2", hi, dpi=300) is True
        lw, lh = _png_size(lo)
        hw, hh = _png_size(hi)
        assert hw > lw and hh > lh

    def test_color_param_changes_pixels(self, tmp_path):
        """color 透傳 — 紅字與白字產出的 PNG bytes 不同。"""
        white = tmp_path / "w.png"
        red = tmp_path / "r.png"
        assert render_latex_to_png(r"x", white, color=DEFAULT_COLOR) is True
        assert render_latex_to_png(r"x", red, color="red") is True
        assert white.read_bytes() != red.read_bytes()

    def test_defaults_exposed(self):
        assert DEFAULT_DPI == 200
        assert DEFAULT_COLOR == "white"
