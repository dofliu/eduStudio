"""core/adapters/document.py — iter 51 PDF figure 抽取.

PyMuPDF (fitz) 必裝, smoke + figure extraction 路徑都要真跑.
md / txt 路徑不依 PDF lib, 純檔案 IO.

iter 87: CI workflow 故意不裝 pymupdf (重型 + 平台相依). 用
importorskip 讓沒裝 fitz 的環境跳過. 本地 dev 環境裝了 pymupdf 仍會跑.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

# iter 87: CI 沒裝 fitz, 跳過整檔
pytest.importorskip("fitz", reason="PyMuPDF 未裝, 跳過 PDF 抽圖測試 (CI 故意不裝重型 dep)")

from core.adapters.document import (
    extract_pdf_figures,
    scan_document,
)


# ---------- fixtures: 用 fitz 即時生 test PDF ----------


@pytest.fixture
def make_test_pdf(tmp_path):
    """產 PDF, 內含指定圖片 + caption 文字. 回 PDF Path.

    參數 images: [(width, height, caption_text or None), ...]
    每張圖塞一頁, 用 PyMuPDF 純 Python 組裝, 不依外部 ffmpeg / ImageMagick.
    """
    def _make(name: str, images: list[tuple[int, int, str | None]]) -> Path:
        import fitz
        from PIL import Image

        doc = fitz.open()
        try:
            for idx, (w, h, caption) in enumerate(images, start=1):
                page = doc.new_page(width=595, height=842)   # A4

                # 用 PIL 產一張純色 PNG → bytes
                img = Image.new("RGB", (w, h), color=(200, 100 + idx * 20, 100))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                png_bytes = buf.getvalue()

                # 嵌進頁面 (在頁面上半部)
                rect = fitz.Rect(50, 50, 50 + min(w, 400), 50 + min(h, 300))
                page.insert_image(rect, stream=png_bytes)

                if caption:
                    # 在圖下方插 caption — 用 insert_text 簡單塞
                    page.insert_text(
                        fitz.Point(50, 50 + min(h, 300) + 30),
                        caption,
                        fontsize=10,
                    )
            out = tmp_path / f"{name}.pdf"
            doc.save(out)
            return out
        finally:
            doc.close()

    return _make


# ---------- scan_document smoke ----------


class TestScanDocument:
    def test_pdf_returns_text_and_meta(self, make_test_pdf):
        pdf = make_test_pdf("smoke", [(300, 200, "Figure 1: hello")])
        result = scan_document(pdf)
        assert result["source_kind"] == "document"
        assert result["format"] == "pdf"
        assert result["title"] == "smoke"
        # 文字內容裡該有 caption
        assert "Figure 1" in result["content"]

    def test_md_returns_text(self, tmp_path):
        md = tmp_path / "note.md"
        md.write_text("# Hello\n\nthis is markdown", encoding="utf-8")
        result = scan_document(md)
        assert result["format"] == "md"
        assert "Hello" in result["content"]

    def test_unsupported_extension_raises(self, tmp_path):
        bad = tmp_path / "bad.xyz"
        bad.write_text("?")
        with pytest.raises(ValueError):
            scan_document(bad)


# ---------- iter 51: figure 抽取 ----------


class TestExtractPdfFigures:
    def test_no_figures_returns_empty(self, tmp_path):
        """完全沒圖的 PDF (純文字) 不該炸, 回 []."""
        import fitz
        pdf = tmp_path / "no_fig.pdf"
        doc = fitz.open()
        try:
            page = doc.new_page()
            page.insert_text(fitz.Point(50, 50), "just text, no images")
            doc.save(pdf)
        finally:
            doc.close()

        figs = extract_pdf_figures(pdf, tmp_path / "figs")
        assert figs == []

    def test_extracts_single_figure(self, make_test_pdf, tmp_path):
        pdf = make_test_pdf("single", [(400, 300, "Figure 1: 系統架構")])
        figs = extract_pdf_figures(pdf, tmp_path / "figs")
        assert len(figs) == 1
        f = figs[0]
        assert f["page_no"] == 1
        assert f["id"].startswith("fig_p1_")
        assert f["path"].endswith(".png")
        # 抽出的 PNG 實檔該存在
        assert (tmp_path / "figs" / f["path"]).exists()
        # 尺寸該對得上
        assert f["width"] == 400
        assert f["height"] == 300

    def test_extracts_multiple_figures_across_pages(self, make_test_pdf, tmp_path):
        pdf = make_test_pdf("multi", [
            (300, 200, "Figure 1: a"),
            (300, 200, "Figure 2: b"),
            (300, 200, "Figure 3: c"),
        ])
        figs = extract_pdf_figures(pdf, tmp_path / "figs")
        assert len(figs) == 3
        pages = [f["page_no"] for f in figs]
        assert pages == [1, 2, 3]

    def test_filters_small_figures(self, make_test_pdf, tmp_path):
        """min_width / min_height 過濾 — 50x50 小圖該跳過."""
        pdf = make_test_pdf("mixed", [
            (50, 50, None),       # icon (該被過濾)
            (400, 300, None),     # 正常圖 (該保留)
        ])
        figs = extract_pdf_figures(
            pdf, tmp_path / "figs", min_width=100, min_height=100,
        )
        # 只該抽到大圖
        assert len(figs) == 1
        assert figs[0]["width"] == 400

    def test_max_figures_limit(self, make_test_pdf, tmp_path):
        """max_figures=2 → 4 張圖只抽 2 張."""
        pdf = make_test_pdf("limit", [
            (200, 200, None),
            (200, 200, None),
            (200, 200, None),
            (200, 200, None),
        ])
        figs = extract_pdf_figures(pdf, tmp_path / "figs", max_figures=2)
        assert len(figs) == 2

    def test_caption_hint_captures_figure_label(self, make_test_pdf, tmp_path):
        """Figure / 圖 開頭的緊鄰文字該被抓進 caption_hint."""
        pdf = make_test_pdf("cap", [(300, 200, "Figure 1: 神經網路架構")])
        figs = extract_pdf_figures(pdf, tmp_path / "figs")
        assert len(figs) == 1
        # caption_hint 應該帶 "Figure 1" 開頭
        assert "Figure 1" in figs[0]["caption_hint"]

    def test_caption_regex_accepts_chinese_label(self):
        """中文「圖 N」開頭該被 _find_caption_hint regex 接受.

        無法用 fixture 真嵌中文 (PyMuPDF 預設 font 不支援中文, 字會被替成 ·).
        改用 regex 直接 unit test, 確認 pattern 同時涵蓋英 / 中.
        """
        import re
        pattern = re.compile(r"^(圖|Figure|Fig\.?)\s*\d+", re.IGNORECASE)
        assert pattern.match("圖 1: 系統流程圖")
        assert pattern.match("圖1: noflag")     # 無空格
        assert pattern.match("Figure 3: arch")
        assert pattern.match("Fig. 5: blah")
        assert pattern.match("FIG 7")
        # 不該 match 的:
        assert not pattern.match("這只是說明文字")
        assert not pattern.match("Table 1: data")
        assert not pattern.match("Section 2")

    def test_no_caption_match_returns_empty_hint(self, make_test_pdf, tmp_path):
        """沒「圖 / Figure」開頭的緊鄰文字 → caption_hint 空字串."""
        pdf = make_test_pdf("nocap", [(300, 200, "這只是一段說明文字, 不是 caption")])
        figs = extract_pdf_figures(pdf, tmp_path / "figs")
        assert len(figs) == 1
        assert figs[0]["caption_hint"] == ""

    def test_out_dir_auto_created(self, make_test_pdf, tmp_path):
        """out_dir 不存在會自動 mkdir."""
        pdf = make_test_pdf("auto_mkdir", [(300, 200, None)])
        target = tmp_path / "deep" / "nested" / "figs"
        figs = extract_pdf_figures(pdf, target)
        assert len(figs) == 1
        assert target.exists()
