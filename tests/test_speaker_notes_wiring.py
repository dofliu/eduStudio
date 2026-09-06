"""PPTX 講者備註 → 逐頁旁白: ingest 串接與 runner 載入 (不打 Gemini)。

擷取與 prompt 注入本身在 tests/test_pptx_augment.py::TestSpeakerNotes。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fitz", reason="需要 PyMuPDF (PDF → PNG)")

import slide_ingest  # noqa: E402


def _sample_pdf() -> Path:
    pdf = Path("sample_exam.pdf")
    if not pdf.exists():
        pytest.skip("repo 沒有 sample_exam.pdf")
    return pdf


def _ingest(tmp_path, monkeypatch, notes):
    """mock ingest (不打 Gemini), 回傳 deck。

    頁圖路徑要能 relative_to(BASE_DIR), 所以 SLIDES_ROOT / BASE_DIR 一起導到 tmp。
    """
    monkeypatch.setattr(slide_ingest, "SLIDES_ROOT", tmp_path / "slides")
    monkeypatch.setattr(slide_ingest, "BASE_DIR", tmp_path)
    out = tmp_path / "deck.json"
    slide_ingest.ingest(_sample_pdf(), out, mock=True, single=False, brief=False,
                        as_deck=True, speaker_notes=notes)
    return json.loads(out.read_text(encoding="utf-8"))


def _narrations(deck) -> list[str]:
    return [s.get("narration", "") for sec in deck["sections"] for s in sec["slides"]]


def test_notes_reach_pages(tmp_path, monkeypatch):
    """有備註的頁在 mock 旁白裡標記出來; 沒備註的頁維持原樣。"""
    total = len(_narrations(_ingest(tmp_path / "a", monkeypatch, None)))
    notes = [""] * total
    notes[0] = "這頁要講齒輪箱溫升。"
    got = _narrations(_ingest(tmp_path / "b", monkeypatch, notes))
    assert "依講者備註" in got[0]
    assert all("依講者備註" not in n for n in got[1:])


def test_length_mismatch_is_ignored(tmp_path, monkeypatch):
    """PPTX 頁數與 PDF 對不上 → 整份不使用, 不可錯位套到別頁。"""
    got = _narrations(_ingest(tmp_path / "c", monkeypatch, ["只有一則備註", "多的", "更多的", "還有"]))
    assert all("依講者備註" not in n for n in got) or len(got) == 4


def test_no_notes_keeps_original_behaviour(tmp_path, monkeypatch):
    for notes in (None, []):
        assert all("依講者備註" not in n for n in _narrations(_ingest(tmp_path / f"d{notes}", monkeypatch, notes)))


# ---------- runner 端載入 ----------
def _rec(path: str):
    from server.schemas import JobOptions

    class R:
        options = JobOptions(speaker_notes_path=path)
    return R()


def test_runner_loads_notes(tmp_path):
    from server.runner import _load_speaker_notes

    f = tmp_path / "notes.json"
    f.write_text(json.dumps(["第一頁講稿", ""], ensure_ascii=False), encoding="utf-8")
    assert _load_speaker_notes(_rec(str(f))) == ["第一頁講稿", ""]


def test_runner_tolerates_bad_notes(tmp_path):
    """沒設 / 檔案不存在 / 格式不是 list → 回 [], 絕不讓旁白階段炸掉。"""
    from server.runner import _load_speaker_notes

    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a list"}', encoding="utf-8")
    assert _load_speaker_notes(_rec("")) == []
    assert _load_speaker_notes(_rec(str(tmp_path / "missing.json"))) == []
    assert _load_speaker_notes(_rec(str(bad))) == []
