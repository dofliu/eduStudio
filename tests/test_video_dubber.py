"""core/video/dubber.py 測試（eduStudio 合併 B-2）。

只覆蓋不需 media 的純部分：Segment、generate_srt（檔案 I/O）、translate_segments（mock
translator）、merge 空段、lazy 單例。download/whisper/ffmpeg 合成需真 media，不在單元測試。
"""
from __future__ import annotations

from pathlib import Path

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
