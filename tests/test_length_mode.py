"""core/length_mode.py — iter 43 影片長度模式 preset.

純 dict / 純函式, 跟 LLM 完全無關, unit test 直跑.
"""
from __future__ import annotations

import pytest

from core.length_mode import LENGTH_PRESETS, estimate_deck_duration, preset


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

    def test_ultra_quick_has_all_required_keys(self):
        """iter 77 (B3): ultra_quick mode 該有完整欄位."""
        keys = set(LENGTH_PRESETS["ultra_quick"].keys())
        assert self.REQUIRED_KEYS.issubset(keys), (
            f"ultra_quick 缺欄位: {self.REQUIRED_KEYS - keys}"
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

    def test_ultra_quick_is_shorter_than_quick(self):
        """iter 77: ultra_quick 該明顯比 quick 短 — sections / chars 都少."""
        def low(s: str) -> int:
            return int(s.split("~")[0])
        def high(s: str) -> int:
            return int(s.split("~")[1])

        u = LENGTH_PRESETS["ultra_quick"]
        q = LENGTH_PRESETS["quick"]
        # sections 上限 ultra_quick 該 ≤ quick 下限
        assert high(u["sections_range"]) <= low(q["sections_range"])
        # narration chars 上限 ultra_quick 該 ≤ quick 下限
        assert high(u["narration_chars_range"]) <= low(q["narration_chars_range"])
        # narration budget 該少 (~900 vs 2500)
        assert u["total_narration_budget_chars"] < q["total_narration_budget_chars"]

    def test_ultra_quick_target_3_5_min(self):
        """target_minutes 該是 3~5 (短影片 / Shorts 規格)."""
        u = LENGTH_PRESETS["ultra_quick"]
        assert "3" in u["target_minutes"]
        assert "5" in u["target_minutes"]


class TestUltraQuickPreset:
    """iter 77: preset() 對 ultra_quick 該回對應 dict."""

    def test_ultra_quick_returns_ultra_quick_preset(self):
        p = preset("ultra_quick")
        assert p is LENGTH_PRESETS["ultra_quick"]


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
            figures_section="(no figures)",   # iter 52
            length_directive=p["length_directive"],
            slides_per_section_range=p["slides_per_section_range"],
            narration_chars_range=p["narration_chars_range"],
            narration_seconds_range=p["narration_seconds_range"],
        )
        assert p["narration_chars_range"] in filled


class TestEstimateDeckDuration:
    """iter 48: ingest 完估算 deck 總時長 vs 預算."""

    def test_empty_deck(self):
        est = estimate_deck_duration({})
        assert est["sections"] == 0
        assert est["total_slides"] == 0
        assert est["total_chars"] == 0
        assert est["estimated_minutes"] == 0.0
        assert est["over_budget"] is False

    def test_v1_exam_schema_problems_steps(self):
        """v1 schema (problems / steps) 也要算 (給 exam_pdf job 用)."""
        deck = {
            "problems": [
                {"steps": [{"narration": "甲" * 100}, {"narration": "乙" * 100}]},
                {"steps": [{"narration": "丙" * 200}]},
            ],
        }
        est = estimate_deck_duration(deck, "quick")
        assert est["sections"] == 2
        assert est["total_slides"] == 3
        assert est["total_chars"] == 400

    def test_new_deck_schema_sections_slides(self):
        deck = {
            "sections": [
                {"slides": [{"narration": "a" * 500}, {"narration": "b" * 500}]},
            ],
        }
        est = estimate_deck_duration(deck, "quick")
        assert est["total_chars"] == 1000
        assert est["sections"] == 1
        assert est["total_slides"] == 2

    def test_within_quick_budget(self):
        """quick 預算 2500 字, 11.9 分鐘對應 ~2380 字, 不該觸發 over_budget."""
        deck = {"sections": [{"slides": [{"narration": "x" * 2380}]}]}
        est = estimate_deck_duration(deck, "quick")
        assert est["over_budget"] is False
        assert est["estimated_minutes"] < 15

    def test_over_quick_budget(self):
        """模擬 iter 43 老 prompt 產的 8594 字 deck → 應 over_budget."""
        deck = {"sections": [{"slides": [{"narration": "x" * 8594}]}]}
        est = estimate_deck_duration(deck, "quick")
        assert est["over_budget"] is True
        assert est["over_ratio"] > 3.0   # 8594 / 2500 ≈ 3.44

    def test_lecture_budget_allows_more_chars(self):
        """同 8594 字在 lecture 預算 20000 內不該 over_budget."""
        deck = {"sections": [{"slides": [{"narration": "x" * 8594}]}]}
        est = estimate_deck_duration(deck, "lecture")
        assert est["over_budget"] is False

    def test_none_length_mode_uses_quick(self):
        deck = {"sections": [{"slides": [{"narration": "x" * 3000}]}]}
        est = estimate_deck_duration(deck, None)
        # None → quick (2500), 3000 字超預算
        assert est["over_budget"] is True

    def test_estimated_minutes_rounding(self):
        """estimated_minutes 四捨五入到一位小數."""
        deck = {"sections": [{"slides": [{"narration": "x" * 333}]}]}
        # 333 / 200 = 1.665 → 1.7
        est = estimate_deck_duration(deck, "quick")
        assert est["estimated_minutes"] == 1.7
