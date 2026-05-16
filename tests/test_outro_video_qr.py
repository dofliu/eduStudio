"""iter 66 + 67: outro 個人影片串接 + 結尾頁 QR codes."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from PIL import Image

import pipeline
from server.runner import _append_outro_to_deck


# ---------- iter 66: outro 影片串接 ----------

class TestPrepareOutroForProblems:
    """_prepare_outro_for_problems 應該行為跟 _prepare_intro 對稱."""

    def test_returns_none_when_outro_file_missing(self, tmp_path):
        """outro 檔不存在 → (None, 0.0), 不擋流程."""
        from server.runner import _prepare_outro_for_problems
        with patch("core.config.get_outro_video_path",
                   return_value="/nonexistent/outro.mp4"):
            result = _prepare_outro_for_problems([], tmp_path)
        assert result == (None, 0.0)


class TestAppendOutroVideoOption:
    """JobOptions.append_outro_video 該被 schema 接受."""

    def test_jobconfig_accepts_append_outro_video(self):
        from server.schemas import JobOptions
        opts = JobOptions(append_outro_video=True)
        assert opts.append_outro_video is True

    def test_default_append_outro_video_false(self):
        from server.schemas import JobOptions
        opts = JobOptions()
        assert opts.append_outro_video is False


# ---------- iter 67: QR codes ----------

class TestBuildOutroSectionQR:
    """build_outro_section 該帶 outro_show_qr / outro_youtube_url 欄位."""

    def test_qr_fields_in_slide(self):
        from core.outro_gen import build_outro_section
        sec = build_outro_section(
            url="example.com", show_qr=True,
            youtube_url="youtube.com/@x",
        )
        slide = sec["slides"][0]
        assert slide["outro_show_qr"] is True
        assert slide["outro_youtube_url"] == "youtube.com/@x"

    def test_qr_default_off(self):
        from core.outro_gen import build_outro_section
        sec = build_outro_section()
        slide = sec["slides"][0]
        assert slide["outro_show_qr"] is False
        assert slide["outro_youtube_url"] == ""

    def test_empty_youtube_url_stays_empty(self):
        from core.outro_gen import build_outro_section
        sec = build_outro_section(show_qr=True, youtube_url="")
        slide = sec["slides"][0]
        # show_qr=True 但 youtube_url 空 → renderer 跳過右側 QR
        assert slide["outro_show_qr"] is True
        assert slide["outro_youtube_url"] == ""


class TestAppendOutroDeckQR:
    """_append_outro_to_deck 透傳 show_qr / youtube_url."""

    def test_show_qr_true_passes_through(self):
        deck = {"sections": [{"id": "intro", "slides": [{}]}]}
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"), \
             patch("core.config.get_outro_thanks", return_value="T"), \
             patch("core.config.get_outro_url", return_value="u"), \
             patch("core.config.get_outro_youtube_url",
                   return_value="env-youtube.com"):
            _append_outro_to_deck(deck, show_qr=True)
        slide = deck["sections"][-1]["slides"][0]
        assert slide["outro_show_qr"] is True
        assert slide["outro_youtube_url"] == "env-youtube.com"

    def test_youtube_url_override(self):
        deck = {"sections": [{"id": "intro", "slides": [{}]}]}
        with patch("core.config.get_cover_speaker", return_value="X"), \
             patch("core.config.get_cover_org", return_value="Y"), \
             patch("core.config.get_outro_thanks", return_value="T"), \
             patch("core.config.get_outro_url", return_value="u"), \
             patch("core.config.get_outro_youtube_url",
                   return_value="env-youtube.com"):
            _append_outro_to_deck(
                deck, show_qr=True,
                youtube_url_override="custom-youtube.com",
            )
        slide = deck["sections"][-1]["slides"][0]
        assert slide["outro_youtube_url"] == "custom-youtube.com"


class TestQrCodeRendering:
    """實際 render outro page with QR, 驗 QR 區是 black/white 像素 (非 bg)."""

    def test_outro_with_qr_has_white_blocks_at_bottom(self):
        """QR code 區應該有大量白色像素 (QR 底色), 不是純 bg."""
        with TemporaryDirectory() as td:
            out = Path(td) / "outro_qr.png"
            data = {
                "theme": "forest",
                "steps": [{
                    "bg_type": "outro",
                    "title": "謝謝聆聽",
                    "outro_speaker": "X",
                    "outro_org": "Y",
                    "outro_url": "https://doflab.cc",
                    "outro_show_qr": True,
                    "outro_youtube_url": "https://youtube.com/@dofliu",
                    "bullets": [], "code_snippet": None, "code_lang": None,
                    "file_path": None, "image_path": None, "narration": "n",
                    "section_title": "",
                }],
            }
            pipeline.render_frame(data, 1, out, Path(td))
            img = Image.open(out).convert("RGB")
            # QR 位置: y=650-850 (字幕帶 900 之上 50px gap + 200px QR),
            # 左 QR x=120-320 / 右 QR x=1600-1800
            left_qr_samples = [img.getpixel((120 + dx, 650 + dy))
                               for dx in range(0, 200, 20)
                               for dy in range(0, 200, 20)]
            # 至少 20 個樣本接近純白 (QR 白底)
            whites = sum(1 for px in left_qr_samples
                         if sum(px) > 700)
            assert whites > 20, f"左下 QR 區白色像素太少 ({whites}), samples: {left_qr_samples[:3]}"
            # 也該有黑色 (QR 模塊)
            blacks = sum(1 for px in left_qr_samples
                         if sum(px) < 30)
            assert blacks > 10, f"左下 QR 區黑色像素太少 ({blacks})"

    def test_outro_without_qr_no_white_at_bottom(self):
        """show_qr=False 該不畫 QR (該區仍是 bg)."""
        from core.render.pptx_style import get_palette
        with TemporaryDirectory() as td:
            out = Path(td) / "outro_no_qr.png"
            data = {
                "theme": "forest",
                "steps": [{
                    "bg_type": "outro",
                    "title": "謝謝聆聽",
                    "outro_speaker": "X", "outro_org": "Y",
                    "outro_url": "https://doflab.cc",
                    "outro_show_qr": False,
                    "outro_youtube_url": "https://youtube.com/@x",
                    "bullets": [], "code_snippet": None, "code_lang": None,
                    "file_path": None, "image_path": None, "narration": "n",
                    "section_title": "",
                }],
            }
            pipeline.render_frame(data, 1, out, Path(td))
            img = Image.open(out).convert("RGB")
            palette = get_palette("forest")
            # 同樣 QR 區 (120-320, 650-850) 該全是 bg 色 (forest 深綠)
            # 因為沒畫 QR. 採 9 點都該接近 bg.
            for dx in (0, 100, 199):
                for dy in (0, 100, 199):
                    px = img.getpixel((120 + dx, 650 + dy))
                    dist = ((px[0]-palette["bg"][0])**2 + (px[1]-palette["bg"][1])**2
                            + (px[2]-palette["bg"][2])**2) ** 0.5
                    assert dist < 30, (
                        f"無 QR 模式下 ({120+dx}, {650+dy}) 該是 bg, 實際 {px}"
                    )
