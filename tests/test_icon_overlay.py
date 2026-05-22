"""E2-5 icon_overlay tests — slide 渲染時 PIL 疊 icon.

不依賴外部 assets (assets/icon_library/ 內容尚未產 SVG 全部, E2-2 待做);
全部用 tmp_path 產 fixture PNG 自給自足, 跑得快也跟 manifest 解耦.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PIL", reason="需要 Pillow")

from PIL import Image

from core.icon_overlay import compose_icons


@pytest.fixture
def blank_canvas():
    """1920×1080 純白底, 模擬 SlideRenderer 產出的 frame."""
    return Image.new("RGB", (1920, 1080), (255, 255, 255))


@pytest.fixture
def real_icon(tmp_path):
    """256×256 純紅 RGBA PNG icon — 給 composite 後 pixel 驗證用."""
    p = tmp_path / "icon.png"
    Image.new("RGBA", (256, 256), (255, 0, 0, 255)).save(p)
    return p


class TestNoOpInputs:
    """None / [] / 非 list / 缺欄位 — 都不該炸, 也不該改 canvas."""

    def test_none_noop(self, blank_canvas):
        compose_icons(blank_canvas, None)
        assert blank_canvas.getpixel((100, 100)) == (255, 255, 255)

    def test_empty_list_noop(self, blank_canvas):
        compose_icons(blank_canvas, [])
        assert blank_canvas.getpixel((100, 100)) == (255, 255, 255)

    def test_non_list_input_noop(self, blank_canvas):
        compose_icons(blank_canvas, "not-a-list")  # type: ignore[arg-type]
        assert blank_canvas.getpixel((100, 100)) == (255, 255, 255)

    def test_non_dict_entry_skipped(self, blank_canvas):
        compose_icons(blank_canvas, ["x", None, 42])  # type: ignore[list-item]
        assert blank_canvas.getpixel((100, 100)) == (255, 255, 255)

    def test_missing_path_swallowed(self, blank_canvas):
        compose_icons(
            blank_canvas,
            [{"path": "/does/not/exist.png", "position": "top-right", "size_ratio": 0.1}],
        )
        # top-right 區域 (icon 寬約 192) 應仍白
        assert blank_canvas.getpixel((1800, 50)) == (255, 255, 255)

    def test_path_none_skipped(self, blank_canvas):
        compose_icons(
            blank_canvas,
            [{"path": None, "position": "top-right", "size_ratio": 0.1}],
        )
        assert blank_canvas.getpixel((1800, 50)) == (255, 255, 255)


class TestSVGFallback:
    """E2 候選 A — repo 暫無 cairosvg dep, .svg path 必須 graceful skip 或
    fallback 到同名 .png."""

    def test_svg_path_no_png_skipped(self, blank_canvas, tmp_path):
        svg = tmp_path / "icon.svg"
        svg.write_text("<svg/>", encoding="utf-8")
        compose_icons(
            blank_canvas,
            [{"path": str(svg), "position": "top-right", "size_ratio": 0.1}],
        )
        # 沒有 PNG fallback, top-right 區域該仍白
        assert blank_canvas.getpixel((1800, 50)) == (255, 255, 255)

    def test_svg_falls_back_to_sibling_png(self, blank_canvas, tmp_path):
        """E2-2 之後若 Gemini 順手 render PNG, 兩種檔案同存. 該優先用 PNG."""
        Image.new("RGBA", (256, 256), (255, 0, 0, 255)).save(tmp_path / "icon.png")
        svg = tmp_path / "icon.svg"
        svg.write_text("<svg/>", encoding="utf-8")
        compose_icons(
            blank_canvas,
            [{"path": str(svg), "position": "top-right", "size_ratio": 0.1}],
        )
        # 應有紅色 icon: 寬=192, 邊距 40, x=1688..1880
        assert blank_canvas.getpixel((1750, 80))[0] > 200

    def test_svg_path_no_file_but_png_alt_exists(self, blank_canvas, tmp_path):
        """SVG 檔不存在但同名 PNG 存在 — 仍該用 PNG (E2-2 路徑換命名也常見)."""
        Image.new("RGBA", (256, 256), (255, 0, 0, 255)).save(tmp_path / "icon.png")
        # 不建 svg 檔
        svg_path = tmp_path / "icon.svg"
        compose_icons(
            blank_canvas,
            [{"path": str(svg_path), "position": "top-left", "size_ratio": 0.1}],
        )
        assert blank_canvas.getpixel((100, 100))[0] > 200


class TestPositionResolver:
    """五個位置都該 work; 未知位置該 fallback (不 raise)."""

    def test_top_left(self, blank_canvas, real_icon):
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "top-left", "size_ratio": 0.1}],
        )
        # icon 寬 192, 邊距 40, x: 40..232. top-left
        assert blank_canvas.getpixel((100, 100))[0] > 200
        # 右上角該仍白
        assert blank_canvas.getpixel((1800, 100)) == (255, 255, 255)

    def test_top_right(self, blank_canvas, real_icon):
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "top-right", "size_ratio": 0.1}],
        )
        assert blank_canvas.getpixel((1750, 100))[0] > 200
        assert blank_canvas.getpixel((100, 100)) == (255, 255, 255)

    def test_bottom_right(self, blank_canvas, real_icon):
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "bottom-right", "size_ratio": 0.1}],
        )
        # canvas_h=1080 預設, icon 寬高 192, y: 1080-192-40=848..1040
        assert blank_canvas.getpixel((1750, 950))[0] > 200

    def test_bottom_left(self, blank_canvas, real_icon):
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "bottom-left", "size_ratio": 0.1}],
        )
        assert blank_canvas.getpixel((100, 950))[0] > 200

    def test_center(self, blank_canvas, real_icon):
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "center", "size_ratio": 0.1}],
        )
        # icon 寬 192, center: x=(1920-192)/2=864, y=(1080-192)/2=444
        assert blank_canvas.getpixel((960, 540))[0] > 200

    def test_unknown_position_falls_back_top_right(self, blank_canvas, real_icon):
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "no-such-pos", "size_ratio": 0.1}],
        )
        # 退到 top-right
        assert blank_canvas.getpixel((1750, 100))[0] > 200


class TestSizeAndMultiple:
    def test_size_ratio_applied(self, blank_canvas, real_icon):
        # size_ratio=0.2 → 寬 384, top-left → x 40..424
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "top-left", "size_ratio": 0.2}],
        )
        assert blank_canvas.getpixel((400, 100))[0] > 200

    def test_size_ratio_clamped_zero(self, blank_canvas, real_icon):
        # size_ratio=0 該 clamp 到 0.02 (不該 raise / 不該消失)
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "top-right", "size_ratio": 0.0}],
        )
        # 寬 1920*0.02=38, x=1920-38-40=1842..1880; 抓 (1850, 50)
        assert blank_canvas.getpixel((1850, 50))[0] > 200

    def test_multiple_icons_no_collision(self, blank_canvas, real_icon):
        compose_icons(
            blank_canvas,
            [
                {"path": str(real_icon), "position": "top-left", "size_ratio": 0.08},
                {"path": str(real_icon), "position": "top-right", "size_ratio": 0.08},
            ],
        )
        # 兩邊都該有紅
        assert blank_canvas.getpixel((80, 80))[0] > 200
        assert blank_canvas.getpixel((1800, 80))[0] > 200

    def test_canvas_h_respects_subtitle_band(self, real_icon):
        """caller (SlideRenderer) 該傳 canvas_h=900 扣字幕帶; icon bottom-right
        該在 visible 區內, 不該掉到字幕帶 (y>900)."""
        canvas = Image.new("RGB", (1920, 1080), (255, 255, 255))
        compose_icons(
            canvas,
            [{"path": str(real_icon), "position": "bottom-right", "size_ratio": 0.1}],
            canvas_h=900,
        )
        # icon 高 192, canvas_h=900, margin 40 → y: 900-192-40=668..860
        # 字幕帶 (y>=900) 該仍白
        assert canvas.getpixel((1750, 950)) == (255, 255, 255)
        # icon 範圍內 (y~750) 該紅
        assert canvas.getpixel((1750, 750))[0] > 200
