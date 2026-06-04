"""server.runner._run_ingest_song — SONG track ingest (M3b, 選 B 資產複製進 job dir).

純檔案搬運, 0 Gemini: 讀 song.json → 複製 audio + 逐段圖進 jobs/<id>/ → 路徑改寫
成相對 → 存 deck.json。job 自包含可搬 (劉老師 2026-06-04 拍板選 B)。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import server.jobs as jobs_mod
from server.jobs import JobStore
from server.runner import _run_ingest, _run_ingest_song
from server.schemas import CreateJobRequest, JobOptions, JobSource, SourceType


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


def _make_song_source(tmp_path: Path, *, with_assets=True, abs_audio=False) -> Path:
    """建來源 song.json + (選擇性) audio + image 檔, 回 song.json 路徑."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "images").mkdir()
    audio_ref = str((src / "track.mp3").resolve()) if abs_audio else "track.mp3"
    song = {
        "track_type": "song",
        "song_title": "測試歌",
        "audio_path": audio_ref,
        "segments": [
            {"id": "s1", "lines": ["第一段"], "start": 0.0, "end": 5.0, "image_path": "images/seg_s1.png"},
            {"id": "s2", "lines": ["第二段"], "start": 5.0, "end": 10.0, "image_path": "images/seg_s2.png"},
        ],
    }
    if with_assets:
        (src / "track.mp3").write_bytes(b"\x00audio")
        (src / "images" / "seg_s1.png").write_bytes(b"\x89PNG1")
        (src / "images" / "seg_s2.png").write_bytes(b"\x89PNG2")
    sp = src / "song.json"
    sp.write_text(json.dumps(song, ensure_ascii=False), encoding="utf-8")
    return sp


def _rec(store: JobStore, song_json: Path):
    return store.create(CreateJobRequest(
        source_type=SourceType.SONG,
        source=JobSource(path=str(song_json)),
        options=JobOptions(),
    ))


def _ingest(store, rec, song_json):
    deck_path = store.deck_path(rec.id)
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_run_ingest_song(store, rec, song_json, deck_path)), deck_path


class TestAssetCopy:
    def test_audio_and_images_copied_into_job_dir(self, store, tmp_path):
        sp = _make_song_source(tmp_path)
        rec = _rec(store, sp)
        deck, deck_path = _ingest(store, rec, sp)
        job_dir = deck_path.parent
        # audio 複製成 song.mp3
        assert (job_dir / "song.mp3").exists()
        assert (job_dir / "song.mp3").read_bytes() == b"\x00audio"
        # 兩張圖複製進 images/
        assert (job_dir / "images" / "seg_s1.png").exists()
        assert (job_dir / "images" / "seg_s2.png").exists()

    def test_paths_rewritten_relative_in_deck(self, store, tmp_path):
        sp = _make_song_source(tmp_path)
        rec = _rec(store, sp)
        deck, deck_path = _ingest(store, rec, sp)
        assert deck["audio_path"] == "song.mp3"
        assert deck["segments"][0]["image_path"] == "images/seg_s1.png"
        assert deck["segments"][1]["image_path"] == "images/seg_s2.png"
        # deck.json 寫盤內容一致
        on_disk = json.loads(deck_path.read_text(encoding="utf-8"))
        assert on_disk["audio_path"] == "song.mp3"

    def test_absolute_audio_resolved(self, store, tmp_path):
        sp = _make_song_source(tmp_path, abs_audio=True)
        rec = _rec(store, sp)
        deck, deck_path = _ingest(store, rec, sp)
        assert (deck_path.parent / "song.mp3").exists()
        assert deck["audio_path"] == "song.mp3"

    def test_job_self_contained_after_ingest(self, store, tmp_path):
        # 選 B 的目的: 刪掉來源, job dir 仍有完整資產
        sp = _make_song_source(tmp_path)
        rec = _rec(store, sp)
        deck, deck_path = _ingest(store, rec, sp)
        import shutil
        shutil.rmtree(sp.parent)  # 砍來源
        job_dir = deck_path.parent
        assert (job_dir / "song.mp3").exists()
        assert (job_dir / "images" / "seg_s1.png").exists()


class TestGraceful:
    def test_missing_audio_skipped_not_crash(self, store, tmp_path):
        sp = _make_song_source(tmp_path, with_assets=False)  # 來源缺檔
        rec = _rec(store, sp)
        deck, deck_path = _ingest(store, rec, sp)
        # 不炸; 缺檔不複製, audio_path 保留原值 (沒改寫成 song.mp3)
        assert not (deck_path.parent / "song.mp3").exists()
        assert deck["audio_path"] == "track.mp3"  # 原值

    def test_segment_without_image_path_skipped(self, store, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        song = {
            "track_type": "song", "song_title": "x", "audio_path": "",
            "segments": [{"id": "s1", "lines": ["無圖段"], "start": 0, "end": 5}],
        }
        sp = src / "song.json"
        sp.write_text(json.dumps(song, ensure_ascii=False), encoding="utf-8")
        rec = _rec(store, sp)
        deck, deck_path = _ingest(store, rec, sp)
        assert "image_path" not in deck["segments"][0] or not deck["segments"][0].get("image_path")


class TestValidation:
    def test_non_song_schema_raises(self, store, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        sp = src / "deck.json"
        sp.write_text(json.dumps({"deck_title": "x", "sections": []}), encoding="utf-8")
        rec = _rec(store, sp)
        with pytest.raises(ValueError, match="song schema"):
            _ingest(store, rec, sp)


class TestDispatch:
    def test_run_ingest_routes_song_to_song_ingest(self, store, tmp_path):
        # _run_ingest dispatch 認 SourceType.SONG → 走 _run_ingest_song
        sp = _make_song_source(tmp_path)
        rec = _rec(store, sp)
        store.deck_path(rec.id).parent.mkdir(parents=True, exist_ok=True)
        deck = asyncio.run(_run_ingest(store, rec))
        assert deck["track_type"] == "song"
        assert deck["audio_path"] == "song.mp3"  # 證明真的走了 song ingest (路徑改寫)
