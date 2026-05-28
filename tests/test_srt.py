"""core/srt.py — iter 37 從 pipeline.py 抽出的 build_srt + _fmt_srt_time。

純函式 no I/O 沒依賴, 完整 unit test 易寫。
"""
from __future__ import annotations

import pytest

from core.srt import (
    SUBTITLE_CUE_CHAR_BUDGET,
    _fmt_srt_time,
    build_srt,
    narration_to_cues,
)


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


class TestNarrationToCues:
    """narration_to_cues — 字幕帶切分單一真實來源 (N3 per-cue 上限治本)."""

    def test_none_and_empty(self):
        assert narration_to_cues(None) == []
        assert narration_to_cues("") == []
        assert narration_to_cues("   ") == []

    def test_short_sentence_unchanged(self):
        # 短句不切, 跟舊行為一致 (一句一 cue)
        assert narration_to_cues("這是測試。") == ["這是測試。"]

    def test_default_budget_is_module_constant(self):
        # 不傳 max_cue_chars 該套用 SUBTITLE_CUE_CHAR_BUDGET
        long = "一二三，四五六，七八九，十一二，三四五，六七八，九十甲，乙丙丁。"
        assert narration_to_cues(long) == narration_to_cues(
            long, max_cue_chars=SUBTITLE_CUE_CHAR_BUDGET
        )

    def test_long_sentence_split_at_clause_punct(self):
        # 過長句按逗號 greedy 裝箱到 ≤ budget
        cues = narration_to_cues("一二三四五，六七八九十，甲乙丙丁戊。", max_cue_chars=8)
        assert cues == ["一二三四五，", "六七八九十，", "甲乙丙丁戊。"]
        assert all(len(c) <= 8 for c in cues)

    def test_clause_packing_fills_to_budget(self):
        # 短子句該 greedy 併到接近 budget, 不是一句一 cue
        cues = narration_to_cues("一二，三四，五六，七八。", max_cue_chars=6)
        # "一二，三四，"(6) | "五六，七八。"(6)
        assert cues == ["一二，三四，", "五六，七八。"]
        assert all(len(c) <= 6 for c in cues)

    def test_unsplittable_long_clause_kept_whole(self):
        # 沒有次級標點可切 → 不硬斷詞, 整段保留 (寧可超出也不破壞語意)
        s = "一二三四五六七八九十甲乙丙丁。"
        cues = narration_to_cues(s, max_cue_chars=8)
        assert cues == [s]
        assert len(cues[0]) > 8

    def test_english_clause_spacing_preserved(self):
        # 英文逗號後空白不該被吃掉 (避免 "Hello,world")
        cues = narration_to_cues("Hello, world, foo bar baz.", max_cue_chars=12)
        assert cues == ["Hello,", "world,", "foo bar baz."]

    def test_budget_zero_disables_clause_split(self):
        # max_cue_chars <= 0 關閉次級切分 (回一句一 cue, 對照修前)
        s = "一二三四五，六七八九十，甲乙丙丁戊。"
        assert narration_to_cues(s, max_cue_chars=0) == [s]

    def test_mixed_sentences_and_clause_split(self):
        # 終止標點先切句, 過長句再按次級標點切
        cues = narration_to_cues("短句。長句一二三，四五六七八。", max_cue_chars=6)
        # "短句。" | "長句一二三，" | "四五六七八。"
        assert cues == ["短句。", "長句一二三，", "四五六七八。"]
        assert all(len(c) <= 6 for c in cues)


class TestBuildSrtPerCueCap:
    """build_srt 的 per-cue 上限整合 (N3)."""

    def test_long_narration_capped_into_multiple_cues(self):
        steps = [{"narration": "一二三四五，六七八九十，甲乙丙丁戊。"}]
        durs = [12.0]
        result = build_srt(steps, durs, pause_after_each=0, max_cue_chars=8)
        cue_lines = [l for l in result.split("\n") if l.isdigit()]
        assert cue_lines == ["1", "2", "3"]
        # 每個 cue 文字都 ≤ budget
        text_lines = [l for l in result.split("\n")
                      if l and not l.isdigit() and "-->" not in l]
        assert all(len(t) <= 8 for t in text_lines)

    def test_capped_last_cue_eats_remaining_time(self):
        # 切多 cue 後最後一個仍吃到 step 結束時間
        steps = [{"narration": "一二三四五，六七八九十。"}]
        durs = [10.0]
        result = build_srt(steps, durs, pause_after_each=0, max_cue_chars=5)
        ts_lines = [l for l in result.split("\n") if "-->" in l]
        last_end = ts_lines[-1].split(" --> ")[1]
        assert last_end == "00:00:10,000"

    def test_duration_split_proportional_across_cues(self):
        # 兩個等長 cue → 第一個結束在中點 (按字數比例)
        steps = [{"narration": "一二三四五，六七八九十。"}]
        durs = [10.0]
        result = build_srt(steps, durs, pause_after_each=0, max_cue_chars=5)
        # 兩 cue 各 6 字, 第一 cue 結束 = 10 * 6/12 = 5.0
        assert "00:00:05,000 -->" in result

    def test_disabled_cap_matches_one_cue_per_sentence(self):
        # max_cue_chars=0 → 跟舊「一句一 cue」行為一致
        steps = [{"narration": "一二三四五，六七八九十，甲乙丙丁戊。"}]
        durs = [10.0]
        result = build_srt(steps, durs, pause_after_each=0, max_cue_chars=0)
        cue_lines = [l for l in result.split("\n") if l.isdigit()]
        assert cue_lines == ["1"]

    def test_default_cap_keeps_short_narration_single_cue(self):
        # 短 narration 在預設 budget 下仍單 cue (回歸保證)
        steps = [{"narration": "這是一句短的旁白。"}]
        durs = [5.0]
        result = build_srt(steps, durs)
        cue_lines = [l for l in result.split("\n") if l.isdigit()]
        assert cue_lines == ["1"]
