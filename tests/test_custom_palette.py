"""iter 76 (A3): 自訂主題色票 override — hex 解析 + palette merge + 渲染整合."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

import pipeline
from core.render.pptx_style import (
    THEMES,
    _hex_to_rgb,
    merge_custom_palette,
)


class TestHexToRgb:
    def test_hash_prefix(self):
        assert _hex_to_rgb("#ff0000") == (255, 0, 0)

    def test_no_prefix(self):
        assert _hex_to_rgb("00ff00") == (0, 255, 0)

    def test_uppercase(self):
        assert _hex_to_rgb("#0000FF") == (0, 0, 255)

    def test_invalid_returns_none(self):
        assert _hex_to_rgb("nope") is None
        assert _hex_to_rgb("#zzz") is None
        assert _hex_to_rgb("123") is None
        assert _hex_to_rgb("") is None
        assert _hex_to_rgb(None) is None

    def test_whitespace_tolerated(self):
        assert _hex_to_rgb("  #ff0000  ") == (255, 0, 0)


class TestMergeCustomPalette:
    def test_no_overrides_returns_base(self):
        base = THEMES["forest"]
        merged = merge_custom_palette(base)
        # 不該 mutate base
        assert merged == base

    def test_bg_override(self):
        base = THEMES["forest"]
        merged = merge_custom_palette(base, custom_bg="#ff0000")
        assert merged["bg"] == (255, 0, 0)
        # 其他 token 不變
        assert merged["primary"] == base["primary"]
        assert merged["highlight"] == base["highlight"]

    def test_all_three_overrides(self):
        base = THEMES["forest"]
        merged = merge_custom_palette(
            base,
            custom_bg="#111111",
            custom_primary="#eeeeee",
            custom_highlight="#ffd700",
        )
        assert merged["bg"] == (17, 17, 17)
        assert merged["primary"] == (238, 238, 238)
        assert merged["highlight"] == (255, 215, 0)
        # 其他 5 token 仍跟 base
        assert merged["banner"] == base["banner"]
        assert merged["secondary"] == base["secondary"]

    def test_invalid_hex_falls_back_to_base(self):
        base = THEMES["forest"]
        merged = merge_custom_palette(base, custom_bg="garbage")
        assert merged["bg"] == base["bg"]

    def test_mix_valid_invalid(self):
        """有效 hex 套用, 無效 fallback, 不影響整體."""
        base = THEMES["forest"]
        merged = merge_custom_palette(
            base, custom_bg="#abcdef", custom_primary="invalid",
        )
        assert merged["bg"] == (171, 205, 239)
        assert merged["primary"] == base["primary"]


class TestSchemaAcceptsPaletteOverrides:
    def test_jobconfig_accepts_3_palette_fields(self):
        from server.schemas import JobOptions
        opts = JobOptions(
            palette_bg="#abc123",
            palette_primary="#111111",
            palette_highlight="#ffd700",
        )
        assert opts.palette_bg == "#abc123"
        assert opts.palette_primary == "#111111"
        assert opts.palette_highlight == "#ffd700"

    def test_defaults_are_none(self):
        from server.schemas import JobOptions
        opts = JobOptions()
        assert opts.palette_bg is None
        assert opts.palette_primary is None
        assert opts.palette_highlight is None


class TestRendererPicksUpCustomPalette:
    """End-to-end: data dict 帶 palette_* → render 出來的 PNG 反映自訂色."""

    def test_custom_bg_appears_in_render(self):
        """自訂 bg=#ff0000 → render 出的 PNG 大量像素該是純紅 (除字幕帶外)."""
        with TemporaryDirectory() as td:
            out = Path(td) / "custom.png"
            data = {
                "theme": "forest",
                "palette_bg": "#ff0000",
                "steps": [{
                    "bg_type": "pptx_slide",
                    "title": "T", "section_title": "S",
                    "bullets": ["A"], "code_snippet": None, "code_lang": None,
                    "file_path": None, "image_path": None, "narration": "n",
                }],
            }
            pipeline.render_frame(data, 1, out, Path(td))
            img = Image.open(out).convert("RGB")
            # 中央 (600, 600) 該是接近純紅
            px = img.getpixel((600, 600))
            assert px[0] > 200 and px[1] < 50 and px[2] < 50, (
                f"自訂 bg 該套用, (600, 600) 實際 {px}"
            )

    def test_no_palette_override_keeps_theme_default(self):
        """沒給 palette_* → 用主題基底."""
        with TemporaryDirectory() as td:
            out = Path(td) / "default.png"
            data = {
                "theme": "forest",
                "steps": [{
                    "bg_type": "pptx_slide",
                    "title": "T", "section_title": "S",
                    "bullets": ["A"], "code_snippet": None, "code_lang": None,
                    "file_path": None, "image_path": None, "narration": "n",
                }],
            }
            pipeline.render_frame(data, 1, out, Path(td))
            img = Image.open(out).convert("RGB")
            # forest bg = (30, 58, 46) 深綠
            px = img.getpixel((600, 600))
            base_bg = THEMES["forest"]["bg"]
            assert all(abs(px[i] - base_bg[i]) < 30 for i in range(3)), (
                f"沒 override 該用 forest 預設 bg {base_bg}, 實際 {px}"
            )
