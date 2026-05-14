"""core/length_mode.py — iter 43 影片長度模式 preset.

純 dict / 純函式, 跟 LLM 完全無關, unit test 直跑.
"""
from __future__ import annotations

import pytest

from core.length_mode import LENGTH_PRESETS, preset


class TestPreset:
    """preset() 正確處理已知 / 未知 / None 值."""

    def test_quick_returns_quick_preset(self):
        p = preset("quick")
        assert p is LENGTH_PRESETS["quick"]
        # quick mode 數量 spec 應該是「快速」範圍
        assert "8~15" in p["target_minutes"]

    def test_lecture_returns_lecture_preset(self):
        p = preset("lecture")
        assert p is LENGTH_PRESETS["lecture"]
        # lecture 應該包含「60~180」或類似授課時長
        assert "60" in p["target_minutes"]

    def test_none_falls_back_to_quick(self):
        """None → quick (保現有預設行為)."""
        assert preset(None) is LENGTH_PRESETS["quick"]

    def test_empty_string_falls_back_to_quick(self):
        assert preset("") is LENGTH_PRESETS["quick"]

    def test_unknown_mode_falls_back_to_quick(self):
        """不認識的模式 fallback 不該炸."""
        assert preset("super_long") is LENGTH_PRESETS["quick"]


class TestLengthPresetsContent:
    """確認 LENGTH_PRESETS 字典結構, 兩個 mode 都有完整欄位."""

    REQUIRED_KEYS = {
        "target_minutes",
        "sections_range",
        "slides_per_section_range",
        "narration_chars_range",
        "narration_seconds_range",
        "length_directive",
    }

    def test_quick_has_all_required_keys(self):
        keys = set(LENGTH_PRESETS["quick"].keys())
        assert self.REQUIRED_KEYS.issubset(keys), (
            f"quick 缺欄位: {self.REQUIRED_KEYS - keys}"
        )

    def test_lecture_has_all_required_keys(self):
        keys = set(LENGTH_PRESETS["lecture"].keys())
        assert self.REQUIRED_KEYS.issubset(keys), (
            f"lecture 缺欄位: {self.REQUIRED_KEYS - keys}"
        )

    def test_lecture_is_longer_than_quick(self):
        """sanity check: lecture 的章節數應比 quick 多, 不然根本沒區別."""
        # 兩個都用「N~M」字串表達, 拆出來看下界
        def low(s: str) -> int:
            return int(s.split("~")[0])

        q = LENGTH_PRESETS["quick"]
        l = LENGTH_PRESETS["lecture"]
        assert low(l["sections_range"]) >= low(q["sections_range"])
        assert low(l["narration_chars_range"]) >= low(q["narration_chars_range"])


class TestPromptIntegration:
    """確認 length_mode preset 跟 outliner / scriptor prompts 對得上."""

    def test_outliner_longform_accepts_length_keys(self):
        from core.prompts_loader import load_prompt

        prompt = load_prompt("outliner_longform")
        p = preset("lecture")
        # 應該能完整 format, 不 raise KeyError
        filled = prompt.format(
            title="測試",
            source_label="file",
            source_extra="",
            char_count=1000,
            content="...",
            length_directive=p["length_directive"],
            sections_range=p["sections_range"],
            slides_per_section_range=p["slides_per_section_range"],
        )
        # lecture preset 的章節範圍 ("8~15") 應出現在最終 prompt
        assert p["sections_range"] in filled

    def test_outliner_repo_accepts_length_keys(self):
        from core.prompts_loader import load_prompt

        prompt = load_prompt("outliner_repo")
        p = preset("quick")
        filled = prompt.format(
            root_name="test_repo",
            primary_language="python",
            lang_stats="{}",
            tree="",
            key_files_section="",
            length_directive=p["length_directive"],
            sections_range=p["sections_range"],
            slides_per_section_range=p["slides_per_section_range"],
        )
        assert p["sections_range"] in filled

    def test_scriptor_repo_accepts_length_keys(self):
        from core.prompts_loader import load_prompt

        prompt = load_prompt("scriptor_repo_section")
        p = preset("lecture")
        filled = prompt.format(
            deck_title="d",
            summary="s",
            section_idx=1,
            total_sections=1,
            section_id="s1",
            section_title="t",
            section_intent="i",
            section_topics="topics",
            section_files_section="files",
            length_directive=p["length_directive"],
            slides_per_section_range=p["slides_per_section_range"],
            narration_chars_range=p["narration_chars_range"],
            narration_seconds_range=p["narration_seconds_range"],
        )
        assert p["narration_chars_range"] in filled

    def test_scriptor_longform_accepts_length_keys(self):
        from core.prompts_loader import load_prompt

        prompt = load_prompt("scriptor_longform_section")
        p = preset("quick")
        filled = prompt.format(
            deck_title="d",
            summary="s",
            section_idx=1,
            total_sections=1,
            section_id="s1",
            section_title="t",
            section_intent="i",
            section_topics="topics",
            document_content="...",
            length_directive=p["length_directive"],
            slides_per_section_range=p["slides_per_section_range"],
            narration_chars_range=p["narration_chars_range"],
            narration_seconds_range=p["narration_seconds_range"],
        )
        assert p["narration_chars_range"] in filled
