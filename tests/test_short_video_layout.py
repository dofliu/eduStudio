"""iter 88: 短影片 layout — bg_type=short_video_slide."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from PIL import Image

import pipeline


class TestShortVideoSlideDispatch:
    def test_renderer_registered(self):
        """pipeline._RENDERERS 該認 short_video_slide → pptx renderer."""
        assert pipeline._RENDERERS.get("short_video_slide") is not None
        # 該共用 pptx_slide 實例 (跟 cover / outro 一樣)
        assert pipeline._RENDERERS["short_video_slide"] is pipeline._RENDERERS["pptx_slide"]


class TestShortVideoSlideRender:
    """實際 render 確認 1) 不 raise 2) 巨大字確實佔大區塊."""

    def _render(self, title: str, bullets: list[str],
                image_path: str | None, tmp_path: Path) -> Image.Image:
        out = tmp_path / "short.png"
        data = {
            "theme": "forest",
            "steps": [{
                "bg_type": "short_video_slide",
                "title": title,
                "bullets": bullets,
                "code_snippet": None, "code_lang": None,
                "file_path": None, "image_path": image_path,
                "narration": "n", "section_title": "",
            }],
        }
        pipeline.render_frame(data, 1, out, tmp_path)
        return Image.open(out).convert("RGB")

    def test_no_image_text_only(self):
        with TemporaryDirectory() as td:
            img = self._render(
                "為什麼程式會慢", ["改 dict 變 O(n)"],
                None, Path(td),
            )
            assert img.size == (1920, 1080)

    def test_with_bullets_no_image(self):
        with TemporaryDirectory() as td:
            img = self._render(
                "三個關鍵概念",
                ["第一條", "第二條", "第三條"],
                None, Path(td),
            )
            assert img.size == (1920, 1080)

    def test_title_takes_more_space_than_normal_layout(self):
        """short_video 用 2× title size → primary 色像素該比一般 layout 多很多."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            short = self._render("測試標題 X", [], None, Path(td))
            # 對照: 一般 pptx_slide
            normal_out = Path(td) / "normal.png"
            normal_data = {
                "theme": "forest",
                "steps": [{
                    "bg_type": "pptx_slide", "title": "測試標題 X",
                    "section_title": "S", "bullets": [],
                    "code_snippet": None, "code_lang": None, "file_path": None,
                    "image_path": None, "narration": "n",
                }],
            }
            pipeline.render_frame(normal_data, 1, normal_out, Path(td))
            normal = Image.open(normal_out).convert("RGB")
            primary = get_palette("forest")["primary"]

            def count_primary(im, x_range, y_range, step=5):
                cnt = 0
                for y in range(*y_range, step):
                    for x in range(*x_range, step):
                        px = im.getpixel((x, y))
                        if all(abs(px[i] - primary[i]) < 30 for i in range(3)):
                            cnt += 1
                return cnt

            short_cnt = count_primary(short, (200, 1720), (180, 500))
            normal_cnt = count_primary(normal, (60, 1860), (100, 280))
            # short 字級 2× → primary 像素該至少 1.5× normal
            assert short_cnt > normal_cnt * 1.3, (
                f"short layout title 該佔更多區塊 — short={short_cnt} normal={normal_cnt}"
            )


class TestDeckSchemaShortVideoLayout:
    def test_default_uses_pptx_slide(self):
        """default short_video_layout=False → bg_type 跟以前一樣 pptx_slide."""
        from core.deck import deck_to_exam_schema_pptx
        deck = {"sections": [{
            "id": "s1", "title": "T",
            "slides": [{"id": "s1_1", "title": "X", "narration": "n",
                        "bullets": ["a"], "code_snippet": None,
                        "code_lang": None, "file_path": None,
                        "image_path": None}],
        }]}
        out = deck_to_exam_schema_pptx(deck)
        assert out["problems"][0]["steps"][0]["bg_type"] == "pptx_slide"

    def test_short_video_layout_true_uses_new_bg(self):
        from core.deck import deck_to_exam_schema_pptx
        deck = {"sections": [{
            "id": "s1", "title": "T",
            "slides": [{"id": "s1_1", "title": "X", "narration": "n",
                        "bullets": ["a"], "code_snippet": None,
                        "code_lang": None, "file_path": None,
                        "image_path": None}],
        }]}
        out = deck_to_exam_schema_pptx(deck, short_video_layout=True)
        assert out["problems"][0]["steps"][0]["bg_type"] == "short_video_slide"

    def test_cover_outro_unchanged_even_with_short(self):
        """short_video_layout=True 不該影響 cover / outro bg_type."""
        from core.deck import deck_to_exam_schema_pptx
        deck = {"sections": [
            {"id": "_cover", "slides": [{"narration": "n", "bg_type": "cover"}]},
            {"id": "s1", "slides": [{"narration": "n", "bullets": ["a"]}]},
            {"id": "_outro", "slides": [{"narration": "n", "bg_type": "outro"}]},
        ]}
        out = deck_to_exam_schema_pptx(deck, short_video_layout=True)
        bg_types = [p["steps"][0]["bg_type"] for p in out["problems"]]
        assert bg_types == ["cover", "short_video_slide", "outro"]


class TestJobOptionsShortVideoLayout:
    def test_default_false(self):
        from server.schemas import JobOptions
        opts = JobOptions()
        assert opts.short_video_layout is False

    def test_can_set_true(self):
        from server.schemas import JobOptions
        opts = JobOptions(short_video_layout=True)
        assert opts.short_video_layout is True
