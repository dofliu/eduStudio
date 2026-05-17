"""iter 68: bullets layout dispatch + 字幕條 palette 化.

a. 字幕條 palette 化: 淺底主題 (journal / editorial / brutalist 等) 字幕帶
   該用 palette["banner"] 不再硬寫 #0a0a0a.
b. bullets layout 變體: classic / numbered / centered 三種, 依 theme
   dispatch (journal/editorial → numbered, podium/elven → centered, 其他
   classic).
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

import pipeline


def _render_full_slide(theme: str, tmp_path: Path) -> Image.Image:
    """渲染一張帶 3 條 bullet 的標準 pptx_slide, 供採點測試用."""
    out = tmp_path / f"slide_{theme}.png"
    data = {
        "theme": theme,
        "steps": [{
            "bg_type": "pptx_slide",
            "title": "測試標題",
            "section_title": "第 1 章 概念",
            "bullets": [
                "第一條重點: 內容說明 A",
                "第二條重點: 內容說明 B",
                "第三條重點: 內容說明 C",
            ],
            "code_snippet": None, "code_lang": None,
            "file_path": None, "image_path": None,
            "narration": "n",
        }],
    }
    pipeline.render_frame(data, 1, out, tmp_path)
    return Image.open(out).convert("RGB")


def _color_distance(a, b):
    return ((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2) ** 0.5


# ---------- iter 68a: 字幕條 palette ----------

class TestSubtitleStripPalette:
    """iter 68a: 字幕帶用 palette["banner"], 不再硬寫黑."""

    LIGHT_BG_THEMES = ["journal", "dof-editorial", "dof-brutalist",
                       "dof-supergraphic", "dof-elven"]
    DARK_BG_THEMES = ["forest", "navy", "dof-shinobi", "dof-arcade"]

    @pytest.mark.parametrize("theme", LIGHT_BG_THEMES + DARK_BG_THEMES)
    def test_subtitle_strip_matches_banner(self, theme):
        """字幕帶區 (y > 900) 中央採點應該接近 palette["banner"]."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_full_slide(theme, Path(td))
            palette = get_palette(theme)
            # 字幕帶中央 (960, 990) — 排除上邊框過渡帶
            px = img.getpixel((960, 990))
            dist = _color_distance(px, palette["banner"])
            assert dist < 30, (
                f"{theme} 字幕帶 (960, 990) 該接近 banner {palette['banner']}, "
                f"實際 {px}, dist={dist:.1f}"
            )

    def test_light_bg_no_longer_pure_black(self):
        """淺底主題字幕帶不該是純黑 (iter 68a 修的就是這個)."""
        with TemporaryDirectory() as td:
            img = _render_full_slide("journal", Path(td))
            px = img.getpixel((960, 990))
            # 不該是純黑或接近純黑
            assert sum(px) > 100, (
                f"journal 字幕帶應該不是純黑, 實際 {px}"
            )


# ---------- iter 68b: bullets layout 變體 ----------

class TestContentLayoutDispatch:
    """get_content_layout(theme) 該回正確的 layout 名."""

    def test_journal_is_numbered(self):
        from core.render.pptx_style import get_content_layout
        assert get_content_layout("journal") == "numbered"

    def test_editorial_is_numbered(self):
        from core.render.pptx_style import get_content_layout
        assert get_content_layout("dof-editorial") == "numbered"

    def test_podium_is_centered(self):
        from core.render.pptx_style import get_content_layout
        assert get_content_layout("dof-podium") == "centered"

    def test_elven_is_centered(self):
        from core.render.pptx_style import get_content_layout
        assert get_content_layout("dof-elven") == "centered"

    def test_forest_is_classic(self):
        from core.render.pptx_style import get_content_layout
        assert get_content_layout("forest") == "classic"

    def test_unknown_theme_falls_back_classic(self):
        from core.render.pptx_style import get_content_layout
        assert get_content_layout("nonexistent-theme") == "classic"

    def test_none_falls_back_classic(self):
        from core.render.pptx_style import get_content_layout
        assert get_content_layout(None) == "classic"


class TestNumberedLayout:
    """numbered layout 該畫出「01 / 02 / 03」編號."""

    def test_journal_has_number_marker(self):
        """numbered layout 該在 bullet 左側出現 secondary 色的「01」字樣."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_full_slide("journal", Path(td))
            palette = get_palette("journal")
            # 編號 01 / 02 / 03 在左側 (SIDE_MARGIN+14 ~ +90 區), secondary 色.
            # 密集採掃 (step 5) 才能抓到 antialiased glyph 邊緣.
            sec = palette["secondary"]
            count = 0
            for y in range(180, 700, 5):
                for x in range(110, 200, 5):
                    px = img.getpixel((x, y))
                    if _color_distance(px, sec) < 40:
                        count += 1
            # 至少 20 個樣本接近 secondary 色 (數字筆畫)
            assert count > 20, (
                f"journal (numbered) 該有 secondary 色編號像素, 找到 {count} 個"
            )

    def test_classic_has_bullet_marker(self):
        """classic layout 該在左側出現 highlight 色的「•」marker.

        iter 87b: NotoSansCJK (Linux CI) 跟 msjh (Windows) 對 • 字形位置 +
        anti-aliased 邊緣略不同, 採點密度提高 + 閾值降低, 不再 pin 字型版本.
        """
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_full_slide("forest", Path(td))
            palette = get_palette("forest")
            # • marker 在 x ~118 (SIDE_MARGIN+18), highlight 色
            hl = palette["highlight"]
            count = 0
            # 密集採樣 (5x5 step) 蓋字型寬度差異
            for y in range(170, 720, 5):
                for x in range(105, 170, 3):
                    px = img.getpixel((x, y))
                    if _color_distance(px, hl) < 70:
                        count += 1
            assert count > 2, (
                f"forest (classic) 該有 highlight 色 marker 像素, 找到 {count} 個"
            )


class TestCenteredLayout:
    """centered layout: bullets 該居中 (中央區有文字, 左右 200px 內近全 bg)."""

    def test_podium_bullets_centered(self):
        """podium 用 centered, 左 200px 邊應該大致 bg 色 (沒 bullet)."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_full_slide("dof-podium", Path(td))
            palette = get_palette("dof-podium")
            bg = palette["bg"]
            # 左 200px 採 9 點該大致是 bg (classic 那邊會有 • marker 在這區)
            samples = []
            for y in range(180, 700, 50):
                for x in range(110, 200, 30):
                    samples.append(img.getpixel((x, y)))
            non_bg_count = sum(1 for px in samples if _color_distance(px, bg) > 30)
            # centered 不該有 marker / 編號在左 200px, 大部分點該是 bg
            # 允許少量像素 (字幕帶 spillover 等), 但 < 30%
            assert non_bg_count < len(samples) * 0.3, (
                f"podium (centered) 左 200px 該大致 bg, 異常點 {non_bg_count}/{len(samples)}"
            )


class TestIter71NewLayouts:
    """iter 71: 補完的 5 個 layout 變體 — 確認 dispatch table 對 + render 不 raise."""

    @pytest.mark.parametrize("theme,layout", [
        ("dof-zine", "offset"),
        ("dof-brutalist", "offset"),
        ("dof-supergraphic", "offset"),
        ("dof-arcade", "arcade_hud"),
        ("dof-notebook", "notebook_lined"),
        ("dof-shinobi", "shinobi_vertical"),
        ("dof-risograph", "risograph_offset"),
    ])
    def test_layout_dispatch_correct(self, theme, layout):
        from core.render.pptx_style import get_content_layout
        assert get_content_layout(theme) == layout

    @pytest.mark.parametrize("theme", [
        "dof-zine", "dof-brutalist", "dof-supergraphic",
        "dof-arcade", "dof-notebook", "dof-shinobi", "dof-risograph",
    ])
    def test_new_layout_renders(self, theme):
        """5 個新 layout 對應的主題 render 1 張 slide 不 raise."""
        with TemporaryDirectory() as td:
            img = _render_full_slide(theme, Path(td))
            assert img.size == (1920, 1080)

    def test_arcade_hud_has_item_tag(self):
        """arcade_hud layout 該畫 [ITEM_NN] 方括號 (mono 字型, highlight 色)."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_full_slide("dof-arcade", Path(td))
            palette = get_palette("dof-arcade")
            hl = palette["highlight"]
            # bullet 左側 (SIDE_MARGIN+10 ~ +200, y=180-700) 該有 highlight 色像素
            count = 0
            for y in range(180, 700, 5):
                for x in range(110, 280, 5):
                    px = img.getpixel((x, y))
                    if _color_distance(px, hl) < 60:
                        count += 1
            assert count > 30, f"arcade_hud 該有 highlight tag 像素, 找到 {count}"

    def test_shinobi_vertical_has_marker_bar(self):
        """shinobi_vertical 該有 ┃ 縱線 (highlight 色). 左邊 SIDE_MARGIN+18 ~ +22."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_full_slide("dof-shinobi", Path(td))
            palette = get_palette("dof-shinobi")
            hl = palette["highlight"]
            # 縱線 x ∈ [118, 122], y 隨 bullet 行
            count = 0
            for y in range(180, 700, 5):
                for x in range(116, 124):
                    px = img.getpixel((x, y))
                    if _color_distance(px, hl) < 50:
                        count += 1
            assert count > 30, f"shinobi_vertical 該有縱線 (┃) 像素, 找到 {count}"


class TestAllThemesStillRender:
    """iter 68: 加 dispatch 後, 15 主題 + 3 layout 都該能 render 不 raise."""

    ALL_THEMES = [
        "forest", "navy", "frieren", "naruto", "journal",
        "dof-editorial", "dof-podium", "dof-notebook", "dof-shinobi", "dof-elven",
        "dof-zine", "dof-arcade", "dof-risograph", "dof-supergraphic", "dof-brutalist",
    ]

    @pytest.mark.parametrize("theme", ALL_THEMES)
    def test_full_slide_renders(self, theme):
        with TemporaryDirectory() as td:
            img = _render_full_slide(theme, Path(td))
            assert img.size == (1920, 1080)
