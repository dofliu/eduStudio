"""server.runner._augment_slide_images_inplace — 缺圖簡報補圖 runner 整合測試。

全程 mock=True (走 PIL 佔位圖, 不打 Gemini)。驗證:
- 只對 slides_pdf + augment_slide_images=True 生效 (其餘 source_type / 旗標關閉 → noop)
- deck.json 被回填 (slide.bg_image 改指合成頁, reviewed=False)
- 生過圖 → require_review 被自動轉 True
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fitz", reason="需要 PyMuPDF")
pytest.importorskip("PIL", reason="需要 Pillow")

import server.jobs as jobs_mod
from server.jobs import JobStore
from server.runner import _augment_slide_images_inplace
from server.schemas import CreateJobRequest, JobOptions, JobSource, SourceType


def _png(path, size=(960, 720), color=(40, 40, 40)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def _text_pdf(path, n=2):
    import fitz
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for i in range(n):
        p = doc.new_page(width=960, height=720)
        p.insert_text((72, 100), f"純文字頁 {i + 1}")
    doc.save(str(path))
    doc.close()


@pytest.fixture
def store(tmp_path, monkeypatch):
    jobs_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", jobs_root)
    return JobStore(root=jobs_root)


def _make_slides_job(store, base, *, augment=True, source_type=SourceType.SLIDES_PDF):
    """建一個 slides_pdf job + 寫 deck.json + 原頁 PNG + 純文字 PDF。回傳 rec。"""
    pdf = base / "deck.pdf"
    _text_pdf(pdf, n=2)
    # 原頁 PNG (asset_base = PROJECT_ROOT, 但測試用 deck source_meta 指 tmp pdf,
    # 原頁路徑用絕對路徑避免依賴 PROJECT_ROOT)
    _png(base / "p001.png")
    _png(base / "p002.png")

    rec = store.create(CreateJobRequest(
        source_type=source_type,
        source=JobSource(path=str(pdf)),
        options=JobOptions(mock=True, augment_slide_images=augment, require_review=False),
    ))
    deck = {
        "deck_title": "測試簡報",
        "source_type": "slides",
        "source_meta": {"pdf_path": str(pdf), "total_pages": 2},
        "sections": [{
            "id": "ch1", "title": "全部",
            "slides": [
                {"id": "ch1_p001", "title": "投影片 1", "narration": "第一頁。",
                 "bg_image": str(base / "p001.png")},
                {"id": "ch1_p002", "title": "投影片 2", "narration": "第二頁。",
                 "bg_image": str(base / "p002.png")},
            ],
        }],
    }
    store.deck_path(rec.id).write_text(json.dumps(deck), encoding="utf-8")
    return rec


def test_augments_imageless_slides_and_flips_review(store, tmp_path):
    rec = _make_slides_job(store, tmp_path / "src", augment=True)
    _augment_slide_images_inplace(store, rec)

    deck = json.loads(store.deck_path(rec.id).read_text(encoding="utf-8"))
    assert deck["image_augmentation"]["generated"] == 2
    for slide in deck["sections"][0]["slides"]:
        assert slide["image_generated"] is True
        assert slide["reviewed"] is False
        assert "aug_" in slide["bg_image"]
    # 生過圖 → require_review 自動轉 True
    assert store.get(rec.id).options.require_review is True


def test_noop_when_flag_off(store, tmp_path):
    rec = _make_slides_job(store, tmp_path / "src", augment=False)
    _augment_slide_images_inplace(store, rec)
    deck = json.loads(store.deck_path(rec.id).read_text(encoding="utf-8"))
    assert "image_augmentation" not in deck
    assert store.get(rec.id).options.require_review is False


def test_noop_for_non_slides_source(store, tmp_path):
    # document 來源即使開了旗標也不補 (本功能只對 slides_pdf)
    rec = _make_slides_job(store, tmp_path / "src", augment=True,
                           source_type=SourceType.DOCUMENT)
    _augment_slide_images_inplace(store, rec)
    deck = json.loads(store.deck_path(rec.id).read_text(encoding="utf-8"))
    assert "image_augmentation" not in deck
