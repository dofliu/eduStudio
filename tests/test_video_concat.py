"""core/video_concat.py — iter 41 從 Idea 4 拆出的 intro concat helper.

純函式部分 (offset_srt / _fmt) 一定能跑. ffmpeg-dependent 部分 (probe /
normalize / concat) 用 importorskip 守 ffmpeg 可達性, CI 沒 ffmpeg 不擋
collection. 但 GitHub Actions matrix 都有 ffmpeg, 所以這些 test 都該真跑.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from core.video_concat import (
    AudioSpec,
    _fmt,
    concat_videos,
    get_video_duration,
    merge_srts,
    normalize_intro_audio,
    offset_srt,
    probe_audio_spec,
)


# ---------- 純函式測試 ----------


class TestFmt:
    """_fmt(秒) → HH:MM:SS,mmm SRT 時間戳."""

    def test_zero(self):
        assert _fmt(0) == "00:00:00,000"

    def test_negative_clamps_to_zero(self):
        assert _fmt(-5.5) == "00:00:00,000"

    def test_simple_seconds(self):
        assert _fmt(5.5) == "00:00:05,500"

    def test_minutes(self):
        assert _fmt(125.123) == "00:02:05,123"

    def test_hours(self):
        assert _fmt(3661.5) == "01:01:01,500"


class TestOffsetSrt:
    """SRT 時間戳往後推."""

    SAMPLE = (
        "1\n"
        "00:00:00,000 --> 00:00:05,500\n"
        "第一句\n\n"
        "2\n"
        "00:00:05,500 --> 00:00:10,000\n"
        "第二句\n"
    )

    def test_zero_offset_returns_unchanged(self):
        assert offset_srt(self.SAMPLE, 0) == self.SAMPLE

    def test_negative_offset_returns_unchanged(self):
        """負值不該往前 (那會剪掉 cue 起始), 視同 noop."""
        assert offset_srt(self.SAMPLE, -1) == self.SAMPLE

    def test_offset_shifts_all_cues(self):
        out = offset_srt(self.SAMPLE, 8.0)
        # 第一個 cue 起始: 00:00:00 → 00:00:08
        assert "00:00:08,000 --> 00:00:13,500" in out
        # 第二個 cue 起始: 00:00:05.5 → 00:00:13.5
        assert "00:00:13,500 --> 00:00:18,000" in out

    def test_offset_preserves_text(self):
        out = offset_srt(self.SAMPLE, 8.0)
        assert "第一句" in out
        assert "第二句" in out
        # cue 編號也不該動
        assert "\n1\n" in "\n" + out
        assert "\n2\n" in out

    def test_fractional_offset(self):
        out = offset_srt(self.SAMPLE, 8.012)
        assert "00:00:08,012" in out

    def test_empty_srt(self):
        assert offset_srt("", 5.0) == ""

    def test_srt_without_cues_unchanged(self):
        """純文字沒時間戳, 不該被改."""
        s = "this has no cues\n"
        assert offset_srt(s, 5.0) == s


# ---------- ffmpeg 相關測試 ----------

# 沒 ffmpeg 就跳過 ffmpeg-dependent tests, 不擋 pure function 那些
_HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="需要 ffmpeg / ffprobe")


@pytest.fixture
def make_test_video(tmp_path):
    """產生一支 2 秒的測試影片 (color 純色 + 靜音 audio).

    回傳 (path, AudioSpec). 用 ffmpeg lavfi source, 不需要外部素材.
    """
    def _make(name: str, sr: int = 44100, ch: int = 2, dur: float = 2.0) -> tuple[Path, AudioSpec]:
        out = tmp_path / f"{name}.mp4"
        ch_layout = "stereo" if ch == 2 else "mono"
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c=red:s=320x240:r=30:d={dur}",
            "-f", "lavfi", "-i",
            f"anullsrc=channel_layout={ch_layout}:sample_rate={sr}",
            "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-ar", str(sr), "-ac", str(ch),
            str(out),
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return out, AudioSpec(sample_rate=sr, channels=ch, codec="aac")
    return _make


@needs_ffmpeg
class TestProbeAudioSpec:
    def test_probe_returns_correct_spec(self, make_test_video):
        path, spec = make_test_video("probe_test", sr=48000, ch=2)
        result = probe_audio_spec(path)
        assert result.sample_rate == 48000
        assert result.channels == 2
        assert result.codec == "aac"


@needs_ffmpeg
class TestNormalizeIntroAudio:
    def test_normalize_changes_sample_rate(self, make_test_video, tmp_path):
        intro, _ = make_test_video("intro", sr=44100, ch=2)
        target = AudioSpec(sample_rate=96000, channels=1, codec="aac")
        cache_dir = tmp_path / "cache"
        normalized = normalize_intro_audio(intro, target, cache_dir)
        assert normalized.exists()
        # normalize 後的 audio spec 應符合 target
        out_spec = probe_audio_spec(normalized)
        assert out_spec.sample_rate == 96000
        assert out_spec.channels == 1

    def test_normalize_uses_cache_on_second_call(self, make_test_video, tmp_path):
        intro, _ = make_test_video("intro", sr=44100, ch=2)
        target = AudioSpec(sample_rate=96000, channels=1, codec="aac")
        cache_dir = tmp_path / "cache"
        first = normalize_intro_audio(intro, target, cache_dir)
        first_mtime = first.stat().st_mtime
        # 第二次跑同樣參數應該回快取, mtime 不變
        second = normalize_intro_audio(intro, target, cache_dir)
        assert second == first
        assert second.stat().st_mtime == first_mtime

    def test_normalize_invalidates_when_target_changes(self, make_test_video, tmp_path):
        intro, _ = make_test_video("intro", sr=44100, ch=2)
        cache_dir = tmp_path / "cache"
        first = normalize_intro_audio(
            intro, AudioSpec(96000, 1, "aac"), cache_dir,
        )
        # 換 target spec 應產出新檔
        second = normalize_intro_audio(
            intro, AudioSpec(48000, 2, "aac"), cache_dir,
        )
        assert second != first

    def test_normalize_missing_intro_raises(self, tmp_path):
        target = AudioSpec(96000, 1, "aac")
        with pytest.raises(FileNotFoundError):
            normalize_intro_audio(
                tmp_path / "nope.mp4", target, tmp_path / "cache",
            )


@needs_ffmpeg
class TestConcatVideos:
    def test_concat_two_videos_sums_duration(self, make_test_video, tmp_path):
        v1, _ = make_test_video("v1", sr=44100, ch=2, dur=2.0)
        v2, _ = make_test_video("v2", sr=44100, ch=2, dur=3.0)
        out = tmp_path / "merged.mp4"
        concat_videos([v1, v2], out)
        assert out.exists()
        dur = get_video_duration(out)
        # 容忍 ±0.2s 誤差 (ffmpeg keyframe 對齊有抖動)
        assert 4.8 <= dur <= 5.2

    def test_concat_single_video_copies(self, make_test_video, tmp_path):
        v1, _ = make_test_video("v1", dur=2.0)
        out = tmp_path / "merged.mp4"
        concat_videos([v1], out)
        assert out.exists()
        assert abs(get_video_duration(out) - 2.0) < 0.2

    def test_concat_empty_raises(self, tmp_path):
        with pytest.raises(ValueError):
            concat_videos([], tmp_path / "out.mp4")

    def test_concat_cleans_up_list_file(self, make_test_video, tmp_path):
        v1, _ = make_test_video("v1", dur=2.0)
        v2, _ = make_test_video("v2", dur=2.0)
        out = tmp_path / "merged.mp4"
        concat_videos([v1, v2], out)
        # 暫存 concat list 不該留下
        assert not (tmp_path / "merged.concat.txt").exists()


@needs_ffmpeg
class TestGetVideoDuration:
    def test_returns_float_seconds(self, make_test_video):
        v, _ = make_test_video("dur_test", dur=2.5)
        d = get_video_duration(v)
        assert 2.3 <= d <= 2.7


class TestMergeSrts:
    """iter 45: 多章 SRT 合併成單一 SRT (cue 重編號 + 累積時間偏移)."""

    def test_empty_returns_empty(self):
        assert merge_srts([]) == ""

    def test_single_part_renumbers_from_1(self):
        srt = (
            "5\n00:00:00,000 --> 00:00:02,000\nfirst\n\n"
            "7\n00:00:02,000 --> 00:00:04,000\nsecond\n"
        )
        merged = merge_srts([(srt, 4.0)])
        # cue 編號應從 1 開始
        lines = merged.split("\n")
        cue_nums = [l for l in lines if l.strip().isdigit()]
        assert cue_nums[0] == "1"
        assert cue_nums[1] == "2"

    def test_two_parts_offset_and_renumber(self):
        srt1 = "1\n00:00:00,000 --> 00:00:02,000\n甲\n"
        srt2 = "1\n00:00:00,000 --> 00:00:03,000\n乙\n"
        merged = merge_srts([(srt1, 5.0), (srt2, 4.0)])
        # 第二章的第一 cue 應該 offset 到 5.0 秒
        assert "00:00:05,000 --> 00:00:08,000" in merged
        # cue 編號連續 1, 2
        lines = merged.split("\n")
        cue_nums = [l for l in lines if l.strip().isdigit()]
        assert cue_nums == ["1", "2"]
        # 兩章內容都在
        assert "甲" in merged
        assert "乙" in merged

    def test_empty_srt_part_with_offset(self):
        """空 srt 仍能帶 offset 影響後續 (intro 場景: intro 沒 SRT 但佔 8 秒)."""
        srt2 = "1\n00:00:00,000 --> 00:00:02,000\nlater\n"
        merged = merge_srts([("", 8.0), (srt2, 2.0)])
        # 第二段該偏移 8 秒
        assert "00:00:08,000 --> 00:00:10,000" in merged
        # cue id 1 (重新計數)
        lines = merged.split("\n")
        cue_nums = [l for l in lines if l.strip().isdigit()]
        assert cue_nums == ["1"]

    def test_three_parts_cumulative_offset(self):
        srt1 = "1\n00:00:00,000 --> 00:00:01,000\na\n"
        srt2 = "1\n00:00:00,000 --> 00:00:01,000\nb\n"
        srt3 = "1\n00:00:00,000 --> 00:00:01,000\nc\n"
        merged = merge_srts([(srt1, 10.0), (srt2, 20.0), (srt3, 30.0)])
        # 三段 cue 起始: 0, 10, 30
        assert "00:00:00,000 --> 00:00:01,000" in merged
        assert "00:00:10,000 --> 00:00:11,000" in merged
        assert "00:00:30,000 --> 00:00:31,000" in merged

    def test_returns_trailing_newline(self):
        srt = "1\n00:00:00,000 --> 00:00:01,000\ntxt\n"
        merged = merge_srts([(srt, 1.0)])
        assert merged.endswith("\n")
