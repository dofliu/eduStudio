"""SONG track M0 渲染骨架測試 — is_song_schema / song_segments_to_srt / build_song_mv_cmd.

純 offline (不真跑 ffmpeg / whisperx / demucs), 對應 docs/SONG_MV_TRACK_RFC.md M0.
"""
from __future__ import annotations

import pytest

from core.song_render import (
    build_song_mv_cmd,
    build_song_mv_kenburns_cmd,
    is_song_schema,
    song_segments_to_srt,
)


def _song(segments):
    return {"track_type": "song", "song_title": "測試歌", "segments": segments}


class TestIsSongSchema:
    def test_song_dict_true(self):
        assert is_song_schema(_song([{"id": "seg_1", "lines": ["x"], "start": 0, "end": 1}]))

    def test_song_empty_segments_still_song(self):
        # track_type 標記在 + segments 是 list (即使空) → 仍是 song schema
        assert is_song_schema(_song([])) is True

    def test_deck_schema_false(self):
        assert is_song_schema({"deck_title": "x", "sections": []}) is False

    def test_exam_schema_false(self):
        assert is_song_schema({"exam_title": "x", "problems": []}) is False

    def test_missing_track_type_false(self):
        # 有 segments 但無 track_type 標記 → 不靠 'segments' in data 硬判
        assert is_song_schema({"segments": []}) is False

    def test_wrong_track_type_false(self):
        assert is_song_schema({"track_type": "deck", "segments": []}) is False

    def test_segments_not_list_false(self):
        assert is_song_schema({"track_type": "song", "segments": "nope"}) is False

    def test_non_dict_false(self):
        assert is_song_schema(None) is False
        assert is_song_schema([]) is False


class TestSongSegmentsToSrt:
    def test_basic_two_segments(self):
        srt = song_segments_to_srt([
            {"id": "s1", "lines": ["第一行"], "start": 0.0, "end": 12.3},
            {"id": "s2", "lines": ["第二行"], "start": 12.3, "end": 20.0},
        ])
        # cue 編號 + 時間戳格式 + 歌詞
        assert "1\n00:00:00,000 --> 00:00:12,300\n第一行" in srt
        assert "2\n00:00:12,300 --> 00:00:20,000\n第二行" in srt

    def test_multiline_lines_joined_with_newline(self):
        srt = song_segments_to_srt([
            {"id": "s1", "lines": ["上句", "下句"], "start": 0.0, "end": 5.0},
        ])
        assert "上句\n下句" in srt

    def test_bypasses_char_budget_no_split(self):
        # 故意一行超過 core.srt SUBTITLE_CUE_CHAR_BUDGET (40), 歌詞不該被字數切分
        long_line = "這是一句故意寫得非常長的歌詞用來證明歌詞行不會被四十字的字幕字數上限切成兩個 cue"
        srt = song_segments_to_srt([
            {"id": "s1", "lines": [long_line], "start": 0.0, "end": 10.0},
        ])
        # 整行原樣在同一個 cue (只有 1 個 cue 編號 "1")
        assert long_line in srt
        assert srt.count("-->") == 1

    def test_invalid_segments_skipped_and_renumbered(self):
        srt = song_segments_to_srt([
            {"id": "ok1", "lines": ["有效"], "start": 0.0, "end": 5.0},
            {"id": "bad_no_end", "lines": ["缺end"], "start": 5.0},        # 跳過
            {"id": "bad_endlestart", "lines": ["顛倒"], "start": 9.0, "end": 9.0},  # end<=start 跳過
            {"id": "bad_empty", "lines": [], "start": 10.0, "end": 12.0},  # 空 lines 跳過
            {"id": "ok2", "lines": ["也有效"], "start": 12.0, "end": 15.0},
        ])
        # 只有 2 個有效 cue, 編號連續 1,2 (跳號不該出現)
        assert srt.count("-->") == 2
        assert srt.startswith("1\n")
        assert "2\n00:00:12,000 --> 00:00:15,000\n也有效" in srt
        assert "缺end" not in srt and "顛倒" not in srt

    def test_empty_returns_empty(self):
        assert song_segments_to_srt([]) == ""

    def test_all_invalid_returns_empty(self):
        assert song_segments_to_srt([{"lines": [], "start": 0, "end": 1}]) == ""


class TestBuildSongMvCmd:
    def test_cmd_has_color_bg_audio_subtitles(self):
        cmd = build_song_mv_cmd("song.mp3", "song.srt", "out")
        joined = " ".join(cmd)
        assert "lavfi" in joined
        assert "color=c=black:s=1920x1080" in joined
        assert "song.mp3" in cmd          # audio input
        assert "subtitles=song.srt:" in joined
        assert "-shortest" in cmd          # 背景無限長, 截到音軌
        assert cmd[-1] == "out.mp4"

    def test_audio_mapped_not_tts(self):
        # 歌曲音檔當配樂 (input 1), video 來自 color (input 0)
        cmd = build_song_mv_cmd("track.wav", "lyrics.srt", "mv")
        assert "0:v" in cmd and "1:a" in cmd

    def test_custom_style_params(self):
        cmd = build_song_mv_cmd(
            "a.mp3", "b.srt", "c", width=1280, height=720,
            bg_color="navy", font_size=48, font_name="SimHei",
        )
        joined = " ".join(cmd)
        assert "color=c=navy:s=1280x720" in joined
        assert "FontSize=48" in joined
        assert "FontName=SimHei" in joined

    def test_lyrics_centered(self):
        # MV 歌詞置中 (ASS Alignment=2 = 底部置中)
        joined = " ".join(build_song_mv_cmd("a.mp3", "b.srt", "c"))
        assert "Alignment=2" in joined


class TestBuildSongMvKenburnsCmd:
    def test_per_image_zoompan_and_concat(self):
        cmd = build_song_mv_kenburns_cmd(
            [("seg1.png", 5.0), ("seg2.png", 8.0)], "song.mp3", "song.srt", "out"
        )
        joined = " ".join(cmd)
        # 兩張圖各一個 -loop 1 input
        assert cmd.count("-loop") == 2
        assert "seg1.png" in cmd and "seg2.png" in cmd
        # 各自 zoompan + concat n=2 + 字幕
        assert "zoompan" in joined
        assert "concat=n=2:v=1:a=0" in joined
        assert "subtitles=song.srt" in joined
        assert cmd[-1] == "out.mp4"

    def test_audio_mapped_after_images(self):
        # 2 圖 → audio 是 input index 2
        cmd = build_song_mv_kenburns_cmd(
            [("a.png", 3.0), ("b.png", 3.0)], "track.mp3", "l.srt", "mv"
        )
        assert "song.mp3" not in cmd  # sanity
        assert "track.mp3" in cmd
        assert "2:a" in cmd  # audio map index = 圖數

    def test_frames_scale_with_duration_and_fps(self):
        # d=frames = round(秒 * fps); 10 秒 @ 30fps = 300
        cmd = build_song_mv_kenburns_cmd([("x.png", 10.0)], "a.mp3", "s.srt", "o", fps=30)
        assert "d=300:" in " ".join(cmd)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            build_song_mv_kenburns_cmd([], "a.mp3", "s.srt", "o")
