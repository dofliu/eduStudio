"""core/song_build — mp3/mp4 → song.json（AI 協助製作）。mock whisper，不跑真轉錄。"""
from __future__ import annotations

from types import SimpleNamespace

import core.song_build as sb
from core.song_render import is_song_schema


def _seg(start, end, text):
    return SimpleNamespace(start=start, end=end, text=text)


class TestBuildSongJson:
    def test_maps_segments(self, monkeypatch):
        from core.meeting import summarizer
        monkeypatch.setattr(summarizer.meeting_summarizer, "transcribe",
                            lambda path, language="auto": (
                                [_seg(0.0, 4.5, "第一句歌詞"), _seg(4.5, 9.2, "第二句歌詞")], "zh"))
        song = sb.build_song_json_from_media("D:/songs/my_song.mp3", "我的歌")
        assert is_song_schema(song)            # 走 song_render type guard
        assert song["song_title"] == "我的歌"
        assert song["audio_path"] == "my_song.mp3"
        assert len(song["segments"]) == 2
        s0 = song["segments"][0]
        assert s0 == {"id": "s1", "lines": ["第一句歌詞"], "start": 0.0, "end": 4.5,
                      "image_path": "images/seg_s1.png", "reviewed": False}

    def test_skips_blank_and_titles_from_filename(self, monkeypatch):
        from core.meeting import summarizer
        monkeypatch.setattr(summarizer.meeting_summarizer, "transcribe",
                            lambda path, language="auto": (
                                [_seg(0, 2, "  "), _seg(2, 5, "有內容"), _seg(5, 6, "")], "zh"))
        song = sb.build_song_json_from_media("/x/那首歌.mp4")
        assert song["song_title"] == "那首歌"           # 檔名當預設標題
        assert len(song["segments"]) == 1               # 空白段跳過
        assert song["segments"][0]["id"] == "s1"        # id 連續重編

    def test_all_reviewed_false(self, monkeypatch):
        from core.meeting import summarizer
        monkeypatch.setattr(summarizer.meeting_summarizer, "transcribe",
                            lambda path, language="auto": ([_seg(0, 1, "a"), _seg(1, 2, "b")], "en"))
        song = sb.build_song_json_from_media("/x/s.mp3")
        assert all(s["reviewed"] is False for s in song["segments"])  # 硬規則 #1
