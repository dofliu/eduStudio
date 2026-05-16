"""iter 64: 封面 / 結尾頁主題差異化 — 對 reverse 主題畫粗框, 對 5 個有
signature_decor 的主題在右上角畫識別徽章.

驗收: 渲染真實 PNG, 在預期位置 sample 像素, 跟 palette 對照確認元素有出現.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

import pipeline


def _render_cover(theme: str, tmp_path: Path) -> Image.Image:
    out = tmp_path / f"cover_{theme}.png"
    data = {
        "theme": theme,
        "steps": [{
            "bg_type": "cover",
            "title": "Test 主題",
            "cover_speaker": "劉老師",
            "cover_org": "DofLab",
            "cover_date": "2026-05-16",
            "bullets": [], "code_snippet": None, "code_lang": None,
            "file_path": None, "image_path": None, "narration": "n",
            "section_title": "",
        }],
    }
    pipeline.render_frame(data, 1, out, tmp_path)
    return Image.open(out).convert("RGB")


def _render_outro(theme: str, tmp_path: Path) -> Image.Image:
    out = tmp_path / f"outro_{theme}.png"
    data = {
        "theme": theme,
        "steps": [{
            "bg_type": "outro",
            "title": "謝謝聆聽",
            "outro_speaker": "劉老師",
            "outro_org": "DofLab",
            "outro_url": "doflab.cc",
            "bullets": [], "code_snippet": None, "code_lang": None,
            "file_path": None, "image_path": None, "narration": "n",
            "section_title": "",
        }],
    }
    pipeline.render_frame(data, 1, out, tmp_path)
    return Image.open(out).convert("RGB")


def _color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return ((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2) ** 0.5


# brutalist / supergraphic / zine 是 banner_style="reverse" — 該畫粗框
REVERSE_THEMES = ["dof-brutalist", "dof-supergraphic", "dof-zine"]
# 非 reverse 主題, 不該畫粗框
NON_REVERSE_THEMES = ["forest", "navy", "journal", "dof-editorial"]


class TestBrutalistFrameOnReverseThemes:
    """iter 64: banner_style="reverse" 主題的封面 / 結尾該有外圍粗框
    (palette.primary 色). 非 reverse 主題不該有."""

    @pytest.mark.parametrize("theme", REVERSE_THEMES)
    def test_cover_has_frame(self, theme):
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_cover(theme, Path(td))
            palette = get_palette(theme)
            # frame 上邊 inset=80, thickness=12, 採點 (640, 86) 該是 primary
            px = img.getpixel((640, 86))
            assert _color_distance(px, palette["primary"]) < 30, (
                f"{theme} 封面 (640, 86) 該是 primary {palette['primary']}, "
                f"實際 {px}"
            )

    @pytest.mark.parametrize("theme", NON_REVERSE_THEMES)
    def test_cover_no_frame(self, theme):
        """非 reverse 主題該保持原本 bg 色, 不該有 primary 色框."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_cover(theme, Path(td))
            palette = get_palette(theme)
            px = img.getpixel((640, 86))
            # 該接近 bg 色 (不該是 primary)
            assert _color_distance(px, palette["bg"]) < 30, (
                f"{theme} 封面 (640, 86) 該是 bg {palette['bg']}, 實際 {px}"
            )

    @pytest.mark.parametrize("theme", REVERSE_THEMES)
    def test_outro_has_frame(self, theme):
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_outro(theme, Path(td))
            palette = get_palette(theme)
            px = img.getpixel((640, 86))
            assert _color_distance(px, palette["primary"]) < 30


class TestSignatureDecorOnCoverOutro:
    """iter 64 + 69: 全 15 主題都該有 THEME_SIGNATURE_DECORS, 封面 / 結尾
    右上角該畫對應的識別徽章 (跟 palette.bg 不同色). iter 69 補完 10 個之後
    沒主題會 fall back 到「沒 signature」分支."""

    # iter 69 後全 15 主題都有 signature
    SIGNATURE_THEMES = [
        "dof-shinobi", "dof-elven", "dof-arcade", "dof-brutalist", "dof-editorial",
        "forest", "navy", "frieren", "naruto", "journal",
        "dof-podium", "dof-notebook", "dof-zine", "dof-risograph", "dof-supergraphic",
    ]

    @pytest.mark.parametrize("theme", SIGNATURE_THEMES)
    def test_cover_has_signature(self, theme):
        """右上角區域 (signature decor 中心約 (1780, 130)) 該跟 bg 不同."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_cover(theme, Path(td))
            palette = get_palette(theme)
            # 密集採樣 (5x5, ±20 step) 蓋住小 glyph 如 editorial §
            samples = []
            for dx in (-40, -20, 0, 20, 40):
                for dy in (-40, -20, 0, 20, 40):
                    samples.append(img.getpixel((1780 + dx, 130 + dy)))
            max_dist = max(_color_distance(p, palette["bg"]) for p in samples)
            assert max_dist > 30, (
                f"{theme} 封面 signature 區無變化, "
                f"max distance vs bg = {max_dist:.1f}"
            )

    @pytest.mark.parametrize("theme", SIGNATURE_THEMES)
    def test_outro_has_signature(self, theme):
        """跟 cover 對稱."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            img = _render_outro(theme, Path(td))
            palette = get_palette(theme)
            samples = []
            for dx in (-40, -20, 0, 20, 40):
                for dy in (-40, -20, 0, 20, 40):
                    samples.append(img.getpixel((1780 + dx, 130 + dy)))
            max_dist = max(_color_distance(p, palette["bg"]) for p in samples)
            assert max_dist > 30


class TestRendersAllThemes:
    """iter 64: 確認所有 15 主題的 cover / outro 都能跑 (不 raise)."""

    ALL_THEMES = [
        "forest", "navy", "frieren", "naruto", "journal",
        "dof-editorial", "dof-podium", "dof-notebook", "dof-shinobi", "dof-elven",
        "dof-zine", "dof-arcade", "dof-risograph", "dof-supergraphic", "dof-brutalist",
    ]

    @pytest.mark.parametrize("theme", ALL_THEMES)
    def test_cover_renders(self, theme):
        with TemporaryDirectory() as td:
            img = _render_cover(theme, Path(td))
            assert img.size == (1920, 1080)

    @pytest.mark.parametrize("theme", ALL_THEMES)
    def test_outro_renders(self, theme):
        with TemporaryDirectory() as td:
            img = _render_outro(theme, Path(td))
            assert img.size == (1920, 1080)
