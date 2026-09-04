"""core/video/dubber.py 測試（eduStudio 合併 B-2）。

只覆蓋不需 media 的純部分：Segment、generate_srt（檔案 I/O）、translate_segments（mock
translator）、merge 空段、lazy 單例。download/whisper/ffmpeg 合成需真 media，不在單元測試。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

import core.video.dubber as dub_mod
from core.video.dubber import Segment, VideoDubber


def _dubber(tmp_path: Path) -> VideoDubber:
    return VideoDubber(output_dir=str(tmp_path))


def test_segment_defaults():
    s = Segment(0.0, 1.0, "hi")
    assert s.translated_text == "" and s.audio_path == ""


def test_generate_srt_original(tmp_path):
    d = _dubber(tmp_path)
    segs = [Segment(0.0, 2.5, "hello"), Segment(65.0, 67.0, "world")]
    path = d.generate_srt(segs, str(tmp_path), use_translated=False)
    content = Path(path).read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:02,500" in content
    assert "00:01:05,000 --> 00:01:07,000" in content
    assert "hello" in content and "world" in content
    assert Path(path).name == "original.srt"


def test_generate_srt_translated(tmp_path):
    d = _dubber(tmp_path)
    segs = [Segment(0.0, 1.0, "hello", translated_text="你好")]
    path = d.generate_srt(segs, str(tmp_path), use_translated=True)
    content = Path(path).read_text(encoding="utf-8")
    assert "你好" in content and "hello" not in content
    assert Path(path).name == "translated.srt"


def test_translate_segments_uses_translator(tmp_path, monkeypatch):
    d = _dubber(tmp_path)
    monkeypatch.setattr(dub_mod.translator, "translate",
                        lambda text, s, t: f"[{t}]{text}")
    segs = [Segment(0.0, 1.0, "a"), Segment(1.0, 2.0, "b")]
    out = d.translate_segments(segs, "zh_TW", "en_US")
    assert out[0].translated_text == "[zh_TW]a"
    assert out[1].translated_text == "[zh_TW]b"


def test_merge_empty_segments_returns_blank(tmp_path):
    d = _dubber(tmp_path)
    # 沒有任何 audio_path 的片段 → 無音軌可合 → 回 ""
    assert d.merge_dubbed_audio([Segment(0.0, 1.0, "x")], 1.0, str(tmp_path)) == ""


def test_merge_skips_missing_audio_with_contiguous_indices(tmp_path, monkeypatch):
    # 三段中間缺一段音檔: filtergraph 的輸入索引與 [aN] 標籤都必須連續 (0,1),
    # 不能沿用 enumerate 的 (0,2) — 否則 [2:a] 指到不存在的輸入、amix 引用不到 [a1],
    # ffmpeg 直接崩 (CODE_REVIEW_2026-07 T1-1)。
    d = _dubber(tmp_path)
    a0 = tmp_path / "seg0.mp3"
    a2 = tmp_path / "seg2.mp3"
    a0.write_bytes(b"x")
    a2.write_bytes(b"x")
    segs = [
        Segment(0.0, 1.0, "a", audio_path=str(a0)),
        Segment(1.0, 2.0, "b", audio_path=str(tmp_path / "missing.mp3")),  # 缺檔 → skip
        Segment(2.0, 3.0, "c", audio_path=str(a2)),
    ]
    captured: dict = {}
    monkeypatch.setattr(d, "adjust_audio_speed", lambda path, dur: path)
    monkeypatch.setattr(d, "_run_cmd_checked", lambda cmd, what: captured.setdefault("cmd", cmd))
    monkeypatch.setattr(d, "_assert_nonempty_file", lambda path, what: None)
    out = d.merge_dubbed_audio(segs, 3.0, str(tmp_path))
    assert out.endswith("dubbed_audio.wav")
    cmd = captured["cmd"]
    assert cmd.count("-i") == 2  # 只餵兩個存在的音檔
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:a]" in fc and "[1:a]" in fc and "[2:a]" not in fc
    assert "[a0][a1]amix=inputs=2" in fc  # 標籤連續且 amix 數量一致


def test_speech_rate_table():
    assert VideoDubber.SPEECH_RATE["zh_TW"] == 4.0
    assert "default" in VideoDubber.SPEECH_RATE


def test_lazy_singleton(monkeypatch):
    monkeypatch.setattr(dub_mod, "_default_dubber", None)
    a = dub_mod.get_video_dubber()
    b = dub_mod.get_video_dubber()
    assert a is b


def test_get_audio_duration_bad_path_returns_zero(tmp_path):
    # ffprobe 對不存在檔回非數字 → get_audio_duration 回 0.0（不崩）
    d = _dubber(tmp_path)
    assert d.get_audio_duration(str(tmp_path / "nope.wav")) == 0.0


# ---------- T1-5: 中間檔清理 ----------

class TestPurgeIntermediates:
    """`process_video` 結束(成功或失敗)都要清掉暫存, 但成品一個都不能少。"""

    def _make_files(self, job_dir: Path, names):
        for n in names:
            (job_dir / n).write_text("x", encoding="utf-8")

    def test_removes_known_intermediates_only(self, tmp_path):
        d = _dubber(tmp_path)
        job = tmp_path / "job_x"
        job.mkdir()
        self._make_files(job, [
            "audio.wav", "dubbed_audio.wav",
            "tts_0000.mp3", "tts_0001.mp3",
            "tts_0001_adjusted.mp3", "tts_0001_adjusted_truncated.mp3",
            # 成品 + 不認識的檔 → 都不能碰
            "dubbed_video.mp4", "original.srt", "translated.srt",
            "video.mp4", "使用者自己放的.txt",
        ])
        removed = d._purge_intermediates(str(job), keep=set())
        assert removed == 6
        left = sorted(p.name for p in job.iterdir())
        assert left == sorted([
            "dubbed_video.mp4", "original.srt", "translated.srt",
            "video.mp4", "使用者自己放的.txt",
        ])

    def test_keep_set_wins_over_pattern(self, tmp_path):
        d = _dubber(tmp_path)
        job = tmp_path / "job_y"
        job.mkdir()
        self._make_files(job, ["audio.wav", "tts_0000.mp3"])
        keep = {str((job / "tts_0000.mp3").resolve())}
        d._purge_intermediates(str(job), keep=keep)
        assert not (job / "audio.wav").exists()
        assert (job / "tts_0000.mp3").exists(), "在 keep 裡的成品不可刪"

    def test_missing_dir_is_noop(self, tmp_path):
        d = _dubber(tmp_path)
        assert d._purge_intermediates(str(tmp_path / "nope"), keep=set()) == 0

    def test_process_video_purges_on_success(self, tmp_path, monkeypatch):
        d = _dubber(tmp_path)
        job = tmp_path / "job_ok"
        job.mkdir()

        def fake_inner(*args, **kwargs):
            jd = Path(kwargs["job_dir"])
            self._make_files(jd, ["audio.wav", "tts_0000.mp3", "dubbed_video.mp4"])
            kwargs["results"]["dubbed_video"] = str(jd / "dubbed_video.mp4")
            return kwargs["results"]

        monkeypatch.setattr(d, "_process_video_inner", fake_inner)
        out = d.process_video("/local.mp4", "auto", "zh_TW", job_dir=str(job))
        assert out["dubbed_video"].endswith("dubbed_video.mp4")
        assert (job / "dubbed_video.mp4").exists()
        assert not (job / "audio.wav").exists()
        assert not (job / "tts_0000.mp3").exists()

    def test_process_video_purges_on_failure(self, tmp_path, monkeypatch):
        """失敗時中間檔更沒有留著的理由 —— 但例外要照樣往外丟。"""
        d = _dubber(tmp_path)
        job = tmp_path / "job_bad"
        job.mkdir()

        def boom(*args, **kwargs):
            self._make_files(Path(kwargs["job_dir"]), ["audio.wav", "tts_0000.mp3"])
            raise RuntimeError("配音炸了")

        monkeypatch.setattr(d, "_process_video_inner", boom)
        with pytest.raises(RuntimeError, match="配音炸了"):
            d.process_video("/local.mp4", "auto", "zh_TW", job_dir=str(job))
        assert not (job / "audio.wav").exists()
        assert not (job / "tts_0000.mp3").exists()

    def test_purge_failure_does_not_break_result(self, tmp_path, monkeypatch):
        """清不掉暫存不該讓一支已經配好音的影片變成失敗。"""
        d = _dubber(tmp_path)
        job = tmp_path / "job_z"
        job.mkdir()
        self._make_files(job, ["audio.wav"])

        def fake_inner(*args, **kwargs):
            return {"dubbed_video": "/somewhere/out.mp4"}

        monkeypatch.setattr(d, "_process_video_inner", fake_inner)
        monkeypatch.setattr(
            dub_mod.os, "remove",
            lambda p: (_ for _ in ()).throw(OSError("permission denied")),
        )
        out = d.process_video("/local.mp4", "auto", "zh_TW", job_dir=str(job))
        assert out["dubbed_video"] == "/somewhere/out.mp4"

    def test_batch_keep_paths_collects_all_languages(self, tmp_path):
        d = _dubber(tmp_path)
        keep = d._batch_keep_paths({
            "original_video": "/a/video.mp4",
            "original_srt": "/a/original.srt",
            "languages": {
                "en": {"translated_srt": "/a/en/t.srt", "dubbed_video": "/a/en/d.mp4"},
                "ja": {"translated_srt": "/a/ja/t.srt"},
            },
        })
        assert keep == {
            os.path.abspath("/a/video.mp4"),
            os.path.abspath("/a/original.srt"),
            os.path.abspath("/a/en/t.srt"),
            os.path.abspath("/a/en/d.mp4"),
            os.path.abspath("/a/ja/t.srt"),
        }
