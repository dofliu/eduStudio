"""core/srt.py — iter 37 從 pipeline.py 抽出的 build_srt + _fmt_srt_time。

純函式 no I/O 沒依賴, 完整 unit test 易寫。
"""
from __future__ import annotations

import pytest

from core.srt import _fmt_srt_time, build_srt


class TestFmtSrtTime:
    """_fmt_srt_time(秒) → HH:MM:SS,mmm SRT timestamp."""

    def test_zero(self):
        assert _fmt_srt_time(0) == "00:00:00,000"

    def test_negative_clamps_to_zero(self):
        assert _fmt_srt_time(-5.5) == "00:00:00,000"

    def test_seconds_only(self):
        assert _fmt_srt_time(5.5) == "00:00:05,500"

    def test_minutes(self):
        assert _fmt_srt_time(125.123) == "00:02:05,123"

    def test_hours(self):
        assert _fmt_srt_time(3661.5) == "01:01:01,500"

    def test_format_padding(self):
        """每段都該補零 (HH:MM:SS,mmm 固定 12 字)."""
        result = _fmt_srt_time(0.001)
        assert result == "00:00:00,001"
        assert len(result) == 12


class TestBuildSrt:
    """build_srt(steps, durations) → SRT 字串."""

    def test_empty_steps(self):
        assert build_srt([], []) == ""

    def test_empty_narration_skipped(self):
        """沒 narration 的 step 不產 cue."""
        steps = [{"narration": ""}, {"narration": "  "}, {"narration": None}]
        durs = [1.0, 1.0, 1.0]
        assert build_srt(steps, durs) == ""

    def test_single_sentence(self):
        steps = [{"narration": "這是測試"}]
        durs = [10.0]
        result = build_srt(steps, durs)
        # 應有 1 個 cue, 包含 sentence
        assert "1\n" in result
        assert "這是測試" in result
        assert "00:00:00,000" in result  # 開始時間

    def test_multiple_sentences_in_one_step(self):
        """多句切 sentence 按字數比例分配時間."""
        steps = [{"narration": "第一句。第二句更長。"}]
        durs = [10.0]
        result = build_srt(steps, durs)
        # 兩個 cue
        assert "1\n" in result
        assert "2\n" in result
        # 兩個句子內容都在
        assert "第一句" in result
        assert "第二句更長" in result

    def test_cue_numbering_sequential(self):
        """cue id 順序遞增, 跨 step 也連續."""
        steps = [
            {"narration": "step1。"},
            {"narration": "step2。"},
            {"narration": "step3。"},
        ]
        durs = [1.0, 1.0, 1.0]
        result = build_srt(steps, durs)
        # 3 個 cue
        lines = result.split("\n")
        cue_lines = [l for l in lines if l.isdigit()]
        assert cue_lines == ["1", "2", "3"]

    def test_pause_after_each_advances_t(self):
        """pause_after_each 累加到下個 step 起始時間."""
        steps = [
            {"narration": "first"},
            {"narration": "second"},
        ]
        durs = [10.0, 5.0]
        result = build_srt(steps, durs, pause_after_each=2.0)
        # second cue 起始 = 10.0 + 2.0 = 12.0 → "00:00:12,000"
        assert "00:00:12,000 -->" in result

    def test_pause_skipped_when_no_narration_but_t_advances(self):
        """空 narration step 不產 cue 但 t 仍累加 (含 pause)."""
        steps = [
            {"narration": "first"},
            {"narration": ""},        # 空, 不產 cue
            {"narration": "third"},
        ]
        durs = [5.0, 3.0, 2.0]
        result = build_srt(steps, durs, pause_after_each=1.0)
        # third 起始: 5+1 (first 完成) + 3+1 (空 narration step 也累加) = 10.0
        assert "00:00:10,000 -->" in result

    def test_last_sentence_eats_remaining_time(self):
        """最後一句吃到 step 結束時間, 避免 float 累積誤差."""
        steps = [{"narration": "甲。乙。丙。"}]
        durs = [9.0]
        result = build_srt(steps, durs, pause_after_each=0)
        # 最後一個 cue 結束時間應該剛好 9.000
        lines = result.split("\n")
        # 找最後一個 timestamp 行
        ts_lines = [l for l in lines if "-->" in l]
        last_ts = ts_lines[-1]
        end_time = last_ts.split(" --> ")[1]
        assert end_time == "00:00:09,000"

    def test_durations_shorter_than_steps_zip(self):
        """durations 比 steps 短, zip 取短的不炸."""
        steps = [
            {"narration": "a。"},
            {"narration": "b。"},
            {"narration": "c。"},
        ]
        durs = [1.0]    # 只有 1 個
        result = build_srt(steps, durs)
        # 只 1 個 cue
        cue_lines = [l for l in result.split("\n") if l.isdigit()]
        assert cue_lines == ["1"]

    def test_english_punctuation_split(self):
        """英文標點! ? 也切句."""
        steps = [{"narration": "Hello! How are you? Fine."}]
        durs = [10.0]
        result = build_srt(steps, durs)
        cue_lines = [l for l in result.split("\n") if l.isdigit()]
        # 3 個 cue: "Hello!" / "How are you?" / "Fine."
        assert len(cue_lines) == 3
