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


class TestSizeRatioEdges:
    """size_ratio 的 clamp / 預設 / 非數值路徑 — 既有測試只蓋下界 (0→0.02),
    上界 (0.50) / 預設值 / 壞值 skip 從沒被驗過."""

    def test_size_ratio_clamped_upper_half(self, blank_canvas, real_icon):
        # size_ratio=0.9 該 clamp 到 0.50 → 寬 1920*0.5=960 (top-left x 40..1000),
        # 而非 0.9 的寬 1728. 抓一個落在 0.9 寬內但 0.5 寬外的 pixel 來區分.
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "top-left", "size_ratio": 0.9}],
        )
        # clamp 0.50 範圍內 (500,500) 該紅
        assert blank_canvas.getpixel((500, 500))[0] > 200
        # x=1400 落在 0.9 寬 (到 1768) 內、0.5 寬 (到 1000) 外 → clamp 後該白
        assert blank_canvas.getpixel((1400, 500)) == (255, 255, 255)

    def test_default_size_ratio_when_missing(self, blank_canvas, real_icon):
        # 沒 size_ratio key → 預設 0.10 → 寬 192, top-left x 40..232
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "top-left"}],
        )
        assert blank_canvas.getpixel((100, 100))[0] > 200
        # x=300 已超 232 → 白, 證明用預設 0.10 而非更大
        assert blank_canvas.getpixel((300, 100)) == (255, 255, 255)

    def test_non_numeric_size_ratio_skipped(self, blank_canvas, real_icon):
        # size_ratio 非數值 → float() 炸 → 單筆靜默 skip (設計: 單 icon 失敗不擋整批)
        compose_icons(
            blank_canvas,
            [{"path": str(real_icon), "position": "top-left", "size_ratio": "big"}],
        )
        # 該 skip, top-left 仍白
        assert blank_canvas.getpixel((100, 100)) == (255, 255, 255)

    def test_bad_size_ratio_does_not_block_other_icons(self, blank_canvas, real_icon):
        # 壞 size_ratio 的 icon skip, 但同 list 的好 icon 該照畫 (per-entry 隔離)
        compose_icons(
            blank_canvas,
            [
                {"path": str(real_icon), "position": "top-left", "size_ratio": "big"},
                {"path": str(real_icon), "position": "top-right", "size_ratio": 0.1},
            ],
        )
        assert blank_canvas.getpixel((100, 100)) == (255, 255, 255)  # 壞的 skip
        assert blank_canvas.getpixel((1750, 100))[0] > 200  # 好的照畫


class TestAspectRatioPreserved:
    """非正方形 icon 該按比例縮放 — 既有測試 icon 全是 256×256 正方形,
    aspect-ratio 縮放 (target_h = icon_h * target_w/icon_w) 從沒被真正驗過."""

    @pytest.fixture
    def wide_icon(self, tmp_path):
        """256×128 (2:1) 紅 RGBA — 驗高度按比例縮 (非拉成跟寬一樣)."""
        p = tmp_path / "wide.png"
        Image.new("RGBA", (256, 128), (255, 0, 0, 255)).save(p)
        return p

    @pytest.fixture
    def tall_icon(self, tmp_path):
        """128×256 (1:2) 紅 RGBA — 驗寬固定 size_ratio、高按比例放大."""
        p = tmp_path / "tall.png"
        Image.new("RGBA", (128, 256), (255, 0, 0, 255)).save(p)
        return p

    def test_wide_icon_height_scaled_proportionally(self, blank_canvas, wide_icon):
        # 256×128 (2:1), size_ratio=0.1 → 寬 192, 高按比例 = 96 (不是 192)
        compose_icons(
            blank_canvas,
            [{"path": str(wide_icon), "position": "top-left", "size_ratio": 0.1}],
        )
        # icon: x 40..232, y 40..136. (100,100) 在內該紅
        assert blank_canvas.getpixel((100, 100))[0] > 200
        # y=200 超出高 96 (40+96=136) → 白, 證明高沒被拉成 192
        assert blank_canvas.getpixel((100, 200)) == (255, 255, 255)

    def test_tall_icon_height_scaled_proportionally(self, blank_canvas, tall_icon):
        # 128×256 (1:2), size_ratio=0.1 → 寬 192, 高按比例 = 384
        compose_icons(
            blank_canvas,
            [{"path": str(tall_icon), "position": "top-left", "size_ratio": 0.1}],
        )
        # icon: x 40..232, y 40..424. (100,400) 仍在高範圍內該紅
        assert blank_canvas.getpixel((100, 400))[0] > 200
        # x=300 超出寬 192 (40+192=232) → 白, 證明寬鎖 size_ratio 沒被高度連動拉大
        assert blank_canvas.getpixel((300, 100)) == (255, 255, 255)


# ---------- iter 103: 渲染整合 (BlackboardRenderer + PptxStyleRenderer) ----------


@pytest.fixture
def real_icon_shared(tmp_path_factory):
    """跨 class 共用的紅 RGBA PNG, 給渲染整合 test 用."""
    p = tmp_path_factory.mktemp("icons") / "icon.png"
    Image.new("RGBA", (256, 256), (255, 0, 0, 255)).save(p)
    return p


class TestBlackboardRendererIntegration:
    """iter 103: BlackboardRenderer 接 compose_icons — 黑板 chalk 內容 + icon 共存.

    跟 test_pptx_image_layout.py 同 pattern: 真畫 1920x1080 PNG, 驗指定位置
    pixel 是 icon 紅. 不 mock compose_icons, 走完整 render path.
    """

    def _make_data(self, icon_path: str | None = None) -> dict:
        step: dict = {
            "display": "step 1 顯示", "narration": "n",
        }
        if icon_path:
            step["icon_overlay"] = [{
                "path": icon_path, "position": "top-right", "size_ratio": 0.1,
            }]
        return {
            "title": "T", "subtitle": "S",
            "problem": "問題", "image": None,
            "steps": [step],
        }

    def test_blackboard_renders_with_icon(self, real_icon_shared, tmp_path):
        pipeline = pytest.importorskip(
            "pipeline", reason="pipeline.py 需要 PIL / mutagen",
        )
        renderer = pipeline.BlackboardRenderer()
        out = tmp_path / "out.png"
        renderer.render(
            self._make_data(icon_path=str(real_icon_shared)),
            1, out, tmp_path,
        )
        assert out.exists()
        with Image.open(out) as png:
            # icon 寬 1920*0.1=192, 邊距 40, top-right x: 1688..1880, y: 40..232
            r, g, b = png.getpixel((1750, 100))[:3]
            assert r > 200 and g < 80 and b < 80, (
                f"top-right 該有紅 icon, 拿到 {(r, g, b)}"
            )

    def test_blackboard_no_icon_overlay_still_works(self, tmp_path):
        """沒 icon_overlay 欄位也該正常渲染 (backwards compat)."""
        pipeline = pytest.importorskip(
            "pipeline", reason="pipeline.py 需要 PIL / mutagen",
        )
        renderer = pipeline.BlackboardRenderer()
        out = tmp_path / "out.png"
        renderer.render(self._make_data(icon_path=None), 1, out, tmp_path)
        assert out.exists()

    def test_blackboard_icon_canvas_h_respects_subtitle_band(
        self, real_icon_shared, tmp_path,
    ):
        """bottom-right icon 不該掉到字幕黑帶 (y>=900)."""
        pipeline = pytest.importorskip(
            "pipeline", reason="pipeline.py 需要 PIL / mutagen",
        )
        renderer = pipeline.BlackboardRenderer()
        data = self._make_data(icon_path=str(real_icon_shared))
        data["steps"][0]["icon_overlay"][0]["position"] = "bottom-right"
        out = tmp_path / "out_br.png"
        renderer.render(data, 1, out, tmp_path)
        with Image.open(out) as png:
            # 字幕帶 (y=950) 該是字幕帶半透黑色 (alpha 180 over 黑板綠), 不該是紅
            # 給足容差: 至少不該 R 通道 dominant
            r, g, b = png.getpixel((1750, 950))[:3]
            assert r < 100, f"字幕帶 (y=950) 不該有紅 icon, 拿到 {(r, g, b)}"


class TestPptxStyleRendererIntegration:
    """iter 103: PptxStyleRenderer 接 compose_icons — 4 路 layout (normal /
    cover / outro / short_video) 都該疊 icon. 走完整 render path 驗 pixel."""

    def _make_step(self, bg_type: str, icon_path: str | None) -> dict:
        step: dict = {
            "title": "T", "section_title": "S",
            "bullets": ["b1"], "narration": "n",
            "bg_type": bg_type, "image_path": None,
            "code_snippet": None, "file_path": None,
        }
        if icon_path:
            step["icon_overlay"] = [{
                "path": icon_path, "position": "top-right", "size_ratio": 0.1,
            }]
        return step

    def _data(self, step: dict) -> dict:
        return {"title": "deck", "theme": "forest", "steps": [step]}

    def test_normal_slide_renders_with_icon(self, real_icon_shared, tmp_path):
        from core.render.pptx_style import PptxStyleRenderer
        renderer = PptxStyleRenderer()
        out = tmp_path / "out_normal.png"
        renderer.render(
            self._data(self._make_step("pptx_slide", str(real_icon_shared))),
            1, out, tmp_path,
        )
        with Image.open(out) as png:
            r, g, b = png.getpixel((1750, 100))[:3]
            assert r > 200 and g < 80 and b < 80, (
                f"normal slide top-right 該有紅 icon, 拿到 {(r, g, b)}"
            )

    def test_cover_slide_renders_with_icon(self, real_icon_shared, tmp_path):
        from core.render.pptx_style import PptxStyleRenderer
        renderer = PptxStyleRenderer()
        out = tmp_path / "out_cover.png"
        renderer.render(
            self._data(self._make_step("cover", str(real_icon_shared))),
            1, out, tmp_path,
        )
        with Image.open(out) as png:
            r, g, b = png.getpixel((1750, 100))[:3]
            assert r > 200 and g < 80 and b < 80, (
                f"cover slide top-right 該有紅 icon, 拿到 {(r, g, b)}"
            )

    def test_outro_slide_renders_with_icon(self, real_icon_shared, tmp_path):
        from core.render.pptx_style import PptxStyleRenderer
        renderer = PptxStyleRenderer()
        out = tmp_path / "out_outro.png"
        renderer.render(
            self._data(self._make_step("outro", str(real_icon_shared))),
            1, out, tmp_path,
        )
        with Image.open(out) as png:
            r, g, b = png.getpixel((1750, 100))[:3]
            assert r > 200 and g < 80 and b < 80, (
                f"outro slide top-right 該有紅 icon, 拿到 {(r, g, b)}"
            )

    def test_pptx_no_icon_overlay_still_works(self, tmp_path):
        """沒 icon_overlay 欄位 — backwards compat, 既有 deck 不該炸."""
        from core.render.pptx_style import PptxStyleRenderer
        renderer = PptxStyleRenderer()
        out = tmp_path / "out_no_icon.png"
        renderer.render(
            self._data(self._make_step("pptx_slide", None)),
            1, out, tmp_path,
        )
        assert out.exists()

    def test_pptx_icon_canvas_h_respects_subtitle_band(
        self, real_icon_shared, tmp_path,
    ):
        """bottom-right icon 該停在 CONTENT_BOTTOM (=900) 上方, 不入字幕帶."""
        from core.render.pptx_style import PptxStyleRenderer
        renderer = PptxStyleRenderer()
        step = self._make_step("pptx_slide", str(real_icon_shared))
        step["icon_overlay"][0]["position"] = "bottom-right"
        out = tmp_path / "out_br.png"
        renderer.render(self._data(step), 1, out, tmp_path)
        with Image.open(out) as png:
            # forest 字幕帶 fill = SUBTITLE_STRIP_COLOR (~ 黑灰). 不該是紅
            r, g, b = png.getpixel((1750, 950))[:3]
            assert r < 100, f"字幕帶 (y=950) 不該有紅 icon, 拿到 {(r, g, b)}"


# ---------- V1c (iter 9): SlideRenderer 渲染整合 ----------


class TestSlideRendererIntegration:
    """V1c: SlideRenderer (pipeline) 接 compose_icons — iter 102 上線兩 layout
    (full / split-left) 是最早接 E2-5 icon 疊圖的 renderer, 但 iter 103 整合
    測試只補了 BlackboardRenderer + PptxStyleRenderer, SlideRenderer 自己從沒
    被直接整合測過. 此處補對稱覆蓋.

    契約重點: 兩 layout 都以 canvas_h=CONTENT_BOTTOM(900) 呼叫 compose_icons,
    讓 bottom-* icon 停在字幕帶上方 — 若誤傳 1080 (整高), bottom icon 會掉進
    y>=900 的字幕黑帶被蓋掉. 用 bottom-right icon 落點區分 900 vs 1080.
    """

    def _make_data(self, icon_path, *, layout="full", with_overlay=True):
        step = {
            "display": "投影片標題",
            "narration": "旁白",
            "layout": layout,
            "bullets": ["重點一", "重點二"],
        }
        if with_overlay:
            step["icon_overlay"] = [
                {"path": str(icon_path), "position": "top-right", "size_ratio": 0.1}
            ]
        return {"steps": [step], "meta": {}}

    def test_full_layout_renders_with_icon(self, real_icon_shared, tmp_path):
        import pipeline
        out = tmp_path / "slide_full.png"
        renderer = pipeline.SlideRenderer()
        data = self._make_data(real_icon_shared, layout="full")
        renderer.render(data, step_idx=1, out_p=str(out), q_work=None)
        assert out.exists()
        result = _Image.open(out).convert("RGB")
        assert result.size == (1920, 1080)
        # 無 bg, top-right icon 區 (x≈1820, y≈100) 該被紅 icon 疊上 (非純黑底)
        px = result.getpixel((1920 - 100, 100))
        assert px != (0, 0, 0)
        assert px[0] > 100

    def test_full_no_icon_overlay_still_works(self, tmp_path):
        import pipeline
        out = tmp_path / "slide_full_plain.png"
        renderer = pipeline.SlideRenderer()
        data = self._make_data(None, layout="full", with_overlay=False)
        renderer.render(data, step_idx=1, out_p=str(out), q_work=None)
        assert out.exists()
        result = _Image.open(out).convert("RGB")
        assert result.size == (1920, 1080)
        # 無 icon + 無 bg → top-right 仍純黑底 (compose_icons NoOp)
        assert result.getpixel((1920 - 100, 100)) == (0, 0, 0)

    def test_split_left_layout_renders_with_icon(self, real_icon_shared, tmp_path):
        import pipeline
        out = tmp_path / "slide_split.png"
        renderer = pipeline.SlideRenderer()
        data = self._make_data(real_icon_shared, layout="split-left")
        renderer.render(data, step_idx=1, out_p=str(out), q_work=None)
        assert out.exists()
        result = _Image.open(out).convert("RGB")
        assert result.size == (1920, 1080)
        # split-left 底色 (18,18,22); top-right icon 區該被紅 icon 蓋上
        px = result.getpixel((1920 - 100, 100))
        assert px[0] > 100

    def test_full_bottom_icon_uses_content_canvas_h(self, real_icon_shared, tmp_path):
        """bottom-right icon 該以 canvas_h=900 定位 (y 668..860), 不是 1080.

        size_ratio 0.1 → 192x192; bottom-right margin 40:
          canvas_h=900  → y 668..860 (落在內容區, y=700 在內)
          canvas_h=1080 → y 848..1040 (y=700 在外, 該點會是黑底)
        取 (1820, 700) 區分: 只有 canvas_h=900 該點才在 icon 內.
        """
        import pipeline
        from core.visuals import SUBTITLE_STRIP_COLOR
        out = tmp_path / "slide_bottom.png"
        renderer = pipeline.SlideRenderer()
        data = self._make_data(real_icon_shared, layout="full")
        data["steps"][0]["icon_overlay"] = [
            {"path": str(real_icon_shared), "position": "bottom-right", "size_ratio": 0.1}
        ]
        renderer.render(data, step_idx=1, out_p=str(out), q_work=None)
        result = _Image.open(out).convert("RGB")
        # y=700 落在 canvas_h=900 的 bottom icon 區 (668..860) → 該是 icon 色
        assert result.getpixel((1920 - 100, 700))[0] > 100
        # y=950 在字幕帶內 → 該是字幕帶色 (icon 沒漏進帶內)
        assert result.getpixel((1920 - 100, 950)) == SUBTITLE_STRIP_COLOR

    def test_split_left_subtitle_band_intact_with_icon(self, real_icon_shared, tmp_path):
        """split-left 也畫字幕帶 (y=900..1080) 且 bottom icon 不污染帶內."""
        import pipeline
        from core.visuals import SUBTITLE_STRIP_COLOR
        out = tmp_path / "slide_split_band.png"
        renderer = pipeline.SlideRenderer()
        data = self._make_data(real_icon_shared, layout="split-left")
        data["steps"][0]["icon_overlay"] = [
            {"path": str(real_icon_shared), "position": "bottom-right", "size_ratio": 0.1}
        ]
        renderer.render(data, step_idx=1, out_p=str(out), q_work=None)
        result = _Image.open(out).convert("RGB")
        assert result.getpixel((1920 - 100, 1000)) == SUBTITLE_STRIP_COLOR
