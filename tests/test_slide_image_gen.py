"""core.slide_image_gen — 缺圖簡報逐頁補圖 測試。

涵蓋:
- detect_imageless_pages: 純文字頁 vs 含大圖頁的判別 (用 fitz 合成 PDF)
- _slide_to_section: 旁白第一句 → intent
- generate_slide_image(mock): 寫出佔位 PNG
- compose_augmented_page: 兩圖合成一張新頁 (尺寸正確)
- augment_deck_with_images(mock): deck 缺圖頁補圖 → bg_image 改指合成頁,
  保留 source_bg_image, 標 reviewed=False / image_generated=True, summary 正確

全程 mock=True, 不打 Gemini / 不需網路。需要 PyMuPDF (fitz) 與 Pillow。
"""
from __future__ import annotations

import pytest

pytest.importorskip("fitz", reason="需要 PyMuPDF")
pytest.importorskip("PIL", reason="需要 Pillow")

from core import slide_image_gen as sig


def _make_png(path, size=(400, 300), color=(120, 60, 200)):
    from PIL import Image
    Image.new("RGB", size, color).save(path)
    return path


def _make_pdf(path, *, n_text_pages=1, image_png=None):
    """合成一份 PDF: 先 n_text_pages 張純文字頁, 最後一張 (若給 image_png) 嵌大圖。"""
    import fitz
    doc = fitz.open()
    for i in range(n_text_pages):
        page = doc.new_page(width=960, height=720)
        page.insert_text((72, 100), f"純文字投影片 {i + 1}\n只有文字沒有配圖" * 3)
    if image_png is not None:
        page = doc.new_page(width=960, height=720)
        page.insert_text((72, 60), "這頁有一張大圖")
        # 嵌入覆蓋大半頁的點陣圖
        page.insert_image(fitz.Rect(80, 120, 880, 680), filename=str(image_png))
    doc.save(str(path))
    doc.close()
    return path


class TestDetectImagelessPages:
    def test_text_page_flagged_image_page_not(self, tmp_path):
        img = _make_png(tmp_path / "pic.png")
        pdf = _make_pdf(tmp_path / "deck.pdf", n_text_pages=2, image_png=img)
        imageless = sig.detect_imageless_pages(pdf)
        # 頁 1、2 純文字 → 缺圖; 頁 3 含大圖 → 不缺
        assert 1 in imageless and 2 in imageless
        assert 3 not in imageless

    def test_all_text_pages(self, tmp_path):
        pdf = _make_pdf(tmp_path / "t.pdf", n_text_pages=3, image_png=None)
        assert sig.detect_imageless_pages(pdf) == [1, 2, 3]


class TestSlideToSection:
    def test_intent_from_first_sentence(self):
        slide = {"id": "ch1_p001", "title": "梯度下降", "narration": "梯度下降是最佳化的核心。它沿著斜率走。"}
        sec = sig._slide_to_section(slide)
        assert sec["title"] == "梯度下降"
        assert sec["intent"] == "梯度下降是最佳化的核心"


class TestGenerateSlideImageMock:
    def test_mock_writes_placeholder(self, tmp_path):
        out = tmp_path / "ai.png"
        ok, err = sig.generate_slide_image({"id": "ch1_p001", "title": "T"}, out, mock=True)
        assert ok and err == ""
        assert out.exists() and out.stat().st_size > 0


class TestComposeAugmentedPage:
    def test_compose_dimensions(self, tmp_path):
        orig = _make_png(tmp_path / "orig.png", size=(800, 600), color=(30, 60, 30))
        ai = _make_png(tmp_path / "ai.png", size=(1024, 1024), color=(200, 200, 240))
        out = sig.compose_augmented_page(orig, ai, tmp_path / "aug.png", width=1920, height=1080)
        from PIL import Image
        assert out.exists()
        assert Image.open(out).size == (1920, 1080)

    def test_compose_without_original(self, tmp_path):
        ai = _make_png(tmp_path / "ai.png", size=(1024, 1024))
        out = sig.compose_augmented_page(tmp_path / "nope.png", ai, tmp_path / "aug.png")
        assert out.exists()

    @pytest.mark.parametrize("layout", sig.LAYOUTS)
    def test_all_layouts_produce_full_frame(self, tmp_path, layout):
        from PIL import Image
        orig = _make_png(tmp_path / "orig.png", size=(800, 600), color=(30, 60, 30))
        ai = _make_png(tmp_path / "ai.png", size=(1024, 1024), color=(200, 200, 240))
        out = sig.compose_augmented_page(
            orig, ai, tmp_path / f"aug_{layout}.png", layout=layout,
            width=1920, height=1080,
        )
        assert Image.open(out).size == (1920, 1080)

    def test_unknown_layout_falls_back(self, tmp_path):
        from PIL import Image
        orig = _make_png(tmp_path / "orig.png", size=(800, 600))
        ai = _make_png(tmp_path / "ai.png", size=(1024, 1024))
        out = sig.compose_augmented_page(orig, ai, tmp_path / "aug.png", layout="bogus")
        assert Image.open(out).size == (1920, 1080)


class TestAugmentDeckWithImages:
    def _deck(self, base):
        # 兩頁: p001 純文字 (缺圖), p002 也純文字, 都給原頁 PNG
        _make_png(base / "p001.png", size=(960, 720), color=(40, 40, 40))
        _make_png(base / "p002.png", size=(960, 720), color=(50, 50, 50))
        return {
            "deck_title": "測試簡報",
            "sections": [{
                "id": "ch1", "title": "全部",
                "slides": [
                    {"id": "ch1_p001", "title": "投影片 1", "narration": "第一頁說明。",
                     "bg_image": "p001.png"},
                    {"id": "ch1_p002", "title": "投影片 2", "narration": "第二頁說明。",
                     "bg_image": "p002.png"},
                ],
            }],
        }

    def test_only_missing_without_pdf_skips_pages_with_bg(self, tmp_path):
        # only_missing 且無 pdf → 退化成「沒有 bg_image 才補」; 兩頁都有 bg → 不補
        deck = self._deck(tmp_path)
        out = sig.augment_deck_with_images(
            deck, figures_dir=tmp_path / "figures", pdf_path=None,
            only_missing=True, mock=True, asset_base=tmp_path,
        )
        assert out["image_augmentation"]["generated"] == 0

    def test_all_pages_mode_augments_each(self, tmp_path):
        deck = self._deck(tmp_path)
        out = sig.augment_deck_with_images(
            deck, figures_dir=tmp_path / "figures", pdf_path=None,
            only_missing=False, mock=True, asset_base=tmp_path,
        )
        assert out["image_augmentation"]["generated"] == 2
        for slide in out["sections"][0]["slides"]:
            assert slide["image_generated"] is True
            assert slide["reviewed"] is False
            assert slide["source_bg_image"] in ("p001.png", "p002.png")
            # bg_image 已改指合成頁, 且檔案存在
            assert slide["bg_image"].startswith("figures/aug_")
            assert (tmp_path / slide["bg_image"]).exists()

    def test_max_images_caps_generation(self, tmp_path):
        deck = self._deck(tmp_path)
        out = sig.augment_deck_with_images(
            deck, figures_dir=tmp_path / "figures", pdf_path=None,
            only_missing=False, mock=True, asset_base=tmp_path, max_images=1,
        )
        assert out["image_augmentation"]["generated"] == 1

    def test_only_missing_with_pdf_targets_detected_pages(self, tmp_path):
        # 造 2 頁純文字 PDF → 兩頁都缺圖 → 都補
        _make_pdf(tmp_path / "deck.pdf", n_text_pages=2, image_png=None)
        deck = self._deck(tmp_path)
        out = sig.augment_deck_with_images(
            deck, figures_dir=tmp_path / "figures", pdf_path=tmp_path / "deck.pdf",
            only_missing=True, mock=True, asset_base=tmp_path,
        )
        assert out["image_augmentation"]["generated"] == 2
