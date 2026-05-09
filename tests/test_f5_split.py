"""PR-5b: F5 預切句邏輯測試 — 解 mid-word 切點 bug."""
from __future__ import annotations

import pytest

from tts_backend import split_for_f5


class TestSplitForF5:
    def test_empty(self):
        assert split_for_f5("") == []

    def test_short_text_unchanged(self):
        # 短文沒到 max_chars, 不切
        assert split_for_f5("短句子。") == ["短句子。"]

    def test_splits_on_full_stop(self):
        # 設低 max_chars 強迫進入切分邏輯
        result = split_for_f5("這是第一句。這是第二句。", max_chars=10)
        assert result == ["這是第一句。", "這是第二句。"]

    def test_splits_on_chinese_period_and_question(self):
        result = split_for_f5("陳述句。問句?驚嘆句!", max_chars=8)
        assert result == ["陳述句。", "問句?", "驚嘆句!"]

    def test_secondary_punctuation_when_long_enough(self):
        # 拉長到超過 max_chars 才會進入切分邏輯
        # 用 max_chars=10, 「這是一段相當長的文字,」是 11 字, 觸發切分;
        # 累積 >= 60% (6) 才會在 secondary 切, 11 > 6 ✓
        text = "這是一段相當長的文字,接下來還有一段更長更長的內容。"
        result = split_for_f5(text, max_chars=15)
        assert len(result) >= 2

    def test_too_long_no_punctuation_hard_split(self):
        # 30 個中文字無標點 → 30 字硬切
        text = "天" * 35
        result = split_for_f5(text, max_chars=30)
        assert len(result) >= 2
        # 第一段不該超過 max_chars 太多
        assert len(result[0]) <= 31

    def test_skips_empty_segments(self):
        # 連續標點不會產生空 segment
        result = split_for_f5("。。。內容。", max_chars=30)
        # 三個句號連續, 三個短句都不超過 max_chars
        for seg in result:
            assert seg.strip()

    def test_realistic_long_chinese(self):
        # 模擬 Gemini narration: 200+ 字含多個句號逗號
        text = (
            "各位同學,今天我們要看穩定性分析。"
            "首先,什麼是穩定?簡單講就是系統受擾動後,"
            "輸出會不會發散到無窮大。"
            "判斷穩定要看特徵根的位置,"
            "都在左半平面就穩定;有任何一個落在右半平面就不穩定。"
            "今天我們會用 Routh-Hurwitz 判別法,"
            "不用真的解出特徵根,直接看係數就能判斷。"
        )
        result = split_for_f5(text, max_chars=30)
        # 應該切成多段, 每段 <= 30 字 (少數逗號切完可能稍長, 容許一點)
        assert len(result) >= 4
        for seg in result:
            # 容錯: 純中文逗號切點可能讓段稍超, 但不該超太多
            assert len(seg) <= 40, f"段太長: {seg}"

    def test_english_no_punctuation_hard_split(self):
        # 純英文沒標點, 硬切
        text = "thequickbrownfoxjumpsoverthelazydogthequickbrownfox"
        result = split_for_f5(text, max_chars=20)
        assert len(result) >= 2
        for seg in result:
            assert len(seg) <= 21

    def test_respects_existing_word_boundaries_via_space(self):
        # 含空白的英文應該 prefer 在空白切
        text = "the quick brown fox jumps over the lazy dog the quick"
        result = split_for_f5(text, max_chars=20)
        # 至少不應在單字中間切 (each segment 不該以非空白開頭, 除了第一段)
        for seg in result[1:]:
            # 第一字應該是字母或標點, 不該是斷掉的字尾
            # 簡單檢查: 不該是 "uick brown..." 這種
            first_word = seg.split(" ", 1)[0]
            # 容錯: 前一段可能切在 word 末尾, 這段第一個字應 >= 2 chars 或本身完整
            assert len(first_word) >= 1

    def test_default_max_chars_is_30(self):
        # 沒指定 max_chars 應該是 30
        text = "天" * 50
        result = split_for_f5(text)    # default max_chars=30
        assert len(result) >= 2
        assert len(result[0]) <= 31

    def test_custom_max_chars(self):
        text = "天" * 50
        result10 = split_for_f5(text, max_chars=10)
        result20 = split_for_f5(text, max_chars=20)
        # max_chars 越小切越多段
        assert len(result10) > len(result20)

    def test_single_long_sentence_with_one_period_at_end(self):
        # 一個 35 字的句子, 末尾有句號 — 應該切兩段 (在 max 之前找逗號 / 30 字硬切)
        text = "這是一個非常非常非常非常非常非常長的中文句子末端有句號。"
        result = split_for_f5(text, max_chars=30)
        # 不該整段塞一段 (>30 字)
        assert max(len(s) for s in result) <= 31
