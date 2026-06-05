"""core/meeting/summarizer.py 測試（eduStudio 合併 B-2）。

純方法（format/time）+ generate_summary（mock 核心 _gemini_complete，預設 gemini 後端，
不打真 API）。extract_audio/transcribe 需 ffmpeg/whisper+media，不在單元測試覆蓋。
"""
from __future__ import annotations

import core.translation.service as tsvc
from core.meeting.summarizer import (
    SUMMARY_TYPES,
    MeetingSummarizer,
    TranscriptSegment,
)


def test_format_time():
    m = MeetingSummarizer()
    assert m._format_time(65) == "01:05"
    assert m._format_time(3725) == "01:02:05"


def test_format_transcript_with_and_without_time():
    m = MeetingSummarizer()
    segs = [TranscriptSegment(0.0, 1.0, "hello"), TranscriptSegment(65.0, 66.0, "world")]
    with_t = m.format_transcript(segs, with_timestamps=True)
    assert "[00:00] hello" in with_t and "[01:05] world" in with_t
    plain = m.format_transcript(segs, with_timestamps=False)
    assert plain == "hello\nworld"


def test_default_backend_is_gemini():
    assert MeetingSummarizer().ai_backend == "gemini"


def test_generate_summary_gemini_mocked(monkeypatch):
    monkeypatch.setattr(tsvc, "_gemini_complete", lambda prompt: "SUMMARY")
    m = MeetingSummarizer()  # 預設 gemini
    out = m.generate_summary("transcript text", ["key_points", "decisions"])
    assert out == {"key_points": "SUMMARY", "decisions": "SUMMARY"}


def test_generate_summary_skips_unknown_type(monkeypatch):
    monkeypatch.setattr(tsvc, "_gemini_complete", lambda prompt: "S")
    m = MeetingSummarizer()
    out = m.generate_summary("t", ["bogus_type", "full_summary"])
    assert "bogus_type" not in out and out["full_summary"] == "S"


def test_generate_summary_exception_becomes_message(monkeypatch):
    def boom(prompt):
        raise RuntimeError("quota")
    monkeypatch.setattr(tsvc, "_gemini_complete", boom)
    out = MeetingSummarizer().generate_summary("t", ["key_points"])
    assert out["key_points"].startswith("Summary generation failed") and "quota" in out["key_points"]


def test_summary_types_have_prompts():
    for info in SUMMARY_TYPES.values():
        assert "name" in info and "prompt" in info
