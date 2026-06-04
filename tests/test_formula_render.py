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
    compose_formula,
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


def _black_canvas(w=1920, h=1080):
    return Image.new("RGB", (w, h), (0, 0, 0))


def _has_non_black(im, box=None):
    region = im.crop(box) if box else im
    return region.convert("L").getextrema()[1] > 0


class TestComposeFormula:
    def test_valid_formula_paints_pixels(self):
        img = _black_canvas()
        compose_formula(img, {"latex": r"\sigma = \frac{F}{A}"},
                        canvas_w=1920, canvas_h=900)
        assert _has_non_black(img)  # 公式被疊上 → 出現非黑像素

    def test_none_is_noop(self):
        img = _black_canvas()
        compose_formula(img, None, canvas_w=1920, canvas_h=900)
        assert not _has_non_black(img)  # 畫布維持全黑

    def test_non_dict_is_noop(self):
        img = _black_canvas()
        compose_formula(img, "x^2", canvas_w=1920, canvas_h=900)  # type: ignore[arg-type]
        assert not _has_non_black(img)

    def test_missing_latex_is_noop(self):
        img = _black_canvas()
        compose_formula(img, {"position": "center"}, canvas_w=1920, canvas_h=900)
        assert not _has_non_black(img)

    def test_empty_latex_is_noop(self):
        img = _black_canvas()
        compose_formula(img, {"latex": "   "}, canvas_w=1920, canvas_h=900)
        assert not _has_non_black(img)

    def test_broken_latex_is_noop_no_raise(self):
        """壞 LaTeX → render 回 False → compose 不疊任何東西, 不炸."""
        img = _black_canvas()
        compose_formula(img, {"latex": r"\frac{"}, canvas_w=1920, canvas_h=900)
        assert not _has_non_black(img)

    def test_position_top_left_vs_bottom_right(self):
        """position 透傳 compose_icons — top-left 公式落左上, bottom-right 落右下."""
        tl = _black_canvas()
        compose_formula(tl, {"latex": r"x", "position": "top-left",
                             "size_ratio": 0.1}, canvas_w=1920, canvas_h=900)
        br = _black_canvas()
        compose_formula(br, {"latex": r"x", "position": "bottom-right",
                             "size_ratio": 0.1}, canvas_w=1920, canvas_h=900)
        # top-left 區 (左上 1/4) 有像素, 右下角無; bottom-right 反之
        assert _has_non_black(tl, box=(0, 0, 480, 225))
        assert not _has_non_black(tl, box=(1440, 675, 1920, 900))
        assert _has_non_black(br, box=(1440, 675, 1920, 900))
        assert not _has_non_black(br, box=(0, 0, 480, 225))

    def test_formula_stays_above_subtitle_band(self):
        """canvas_h=900 (字幕帶上緣) → bottom 公式停在 y<900, 不掉進字幕黑帶."""
        img = _black_canvas()
        compose_formula(img, {"latex": r"\sigma", "position": "bottom-left",
                              "size_ratio": 0.1}, canvas_w=1920, canvas_h=900)
        # 字幕帶 (y>=900) 該維持全黑
        assert not _has_non_black(img, box=(0, 900, 1920, 1080))

    def test_color_changes_pixels(self):
        """color 透傳 render_latex_to_png — 白字與紅字疊出的畫布不同."""
        white = _black_canvas()
        compose_formula(white, {"latex": r"E=mc^2", "color": "white"},
                        canvas_w=1920, canvas_h=900)
        red = _black_canvas()
        compose_formula(red, {"latex": r"E=mc^2", "color": "red"},
                        canvas_w=1920, canvas_h=900)
        assert list(white.getdata()) != list(red.getdata())
