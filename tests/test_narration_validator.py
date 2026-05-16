"""iter 79 (C1): narration 長度驗證 — 純函式測試."""
from __future__ import annotations

import pytest

from core.narration_validator import (
    _parse_range_high,
    validate_slide_narration,
    check_deck_narration_lengths,
    format_validation_report,
)


class TestParseRangeHigh:
    def test_normal_range(self):
        assert _parse_range_high("60~80") == 80

    def test_quick_range(self):
        assert _parse_range_high("80~120") == 120

    def test_lecture_range(self):
        assert _parse_range_high("180~280") == 280

    def test_invalid_returns_999(self):
        assert _parse_range_high("nope") == 999
        assert _parse_range_high(None) == 999
        assert _parse_range_high("") == 999


class TestValidateSlideNarration:
    def test_under_budget(self):
        r = validate_slide_narration("短句子", max_chars=100)
        assert r["length"] == 3
        assert r["max"] == 100
        assert r["over"] is False
        assert r["excess"] == 0

    def test_over_budget(self):
        n = "x" * 150
        r = validate_slide_narration(n, max_chars=100)
        assert r["length"] == 150
        assert r["over"] is True
        assert r["excess"] == 50

    def test_at_boundary(self):
        n = "x" * 100
        r = validate_slide_narration(n, max_chars=100)
        assert r["over"] is False
        assert r["excess"] == 0

    def test_one_over_boundary(self):
        n = "x" * 101
        r = validate_slide_narration(n, max_chars=100)
        assert r["over"] is True
        assert r["excess"] == 1

    def test_empty_narration(self):
        r = validate_slide_narration("", max_chars=100)
        assert r["length"] == 0
        assert r["over"] is False

    def test_none_narration(self):
        r = validate_slide_narration(None, max_chars=100)
        assert r["length"] == 0


class TestCheckDeckNarrationLengths:
    """掃完整 deck (sections/slides) 統計 over-budget."""

    def _make_deck(self, narrations: list[str]) -> dict:
        return {
            "sections": [{
                "id": "intro",
                "slides": [
                    {"id": f"intro_{i+1}", "narration": n}
                    for i, n in enumerate(narrations)
                ],
            }],
        }

    def test_all_under_budget(self):
        deck = self._make_deck(["短", "短", "短"])
        # quick mode 上限 120 字, 全在範圍內
        report = check_deck_narration_lengths(deck, "quick")
        assert report["total_slides"] == 3
        assert report["over_budget_count"] == 0
        assert report["over_budget_ratio"] == 0.0
        assert report["worst_slide"] is None

    def test_some_over_budget(self):
        deck = self._make_deck(["短", "x" * 150, "x" * 200])
        report = check_deck_narration_lengths(deck, "quick")
        assert report["total_slides"] == 3
        assert report["over_budget_count"] == 2
        assert report["worst_slide"]["excess"] == 80   # 200 - 120

    def test_ultra_quick_max_is_80(self):
        """ultra_quick mode 上限 80 字."""
        deck = self._make_deck(["x" * 100])
        report = check_deck_narration_lengths(deck, "ultra_quick")
        assert report["max_chars"] == 80
        assert report["over_budget_count"] == 1

    def test_skips_cover_section(self):
        """_cover / _outro section 該跳過 (narration 是模板, 不該檢查)."""
        deck = {
            "sections": [
                {"id": "_cover", "slides": [{"narration": "x" * 500}]},
                {"id": "main", "slides": [{"narration": "短"}]},
                {"id": "_outro", "slides": [{"narration": "x" * 500}]},
            ],
        }
        report = check_deck_narration_lengths(deck, "quick")
        # 只該掃 main 一張
        assert report["total_slides"] == 1
        assert report["over_budget_count"] == 0

    def test_v1_exam_schema(self):
        """支援 v1 exam schema (problems / steps)."""
        deck = {
            "problems": [{
                "id": "q1",
                "steps": [{"narration": "x" * 50}, {"narration": "x" * 150}],
            }],
        }
        report = check_deck_narration_lengths(deck, "quick")
        assert report["total_slides"] == 2
        assert report["over_budget_count"] == 1

    def test_empty_deck(self):
        report = check_deck_narration_lengths({}, "quick")
        assert report["total_slides"] == 0
        assert report["over_budget_count"] == 0


class TestFormatValidationReport:
    def test_no_over_budget_message(self):
        report = check_deck_narration_lengths(
            {"sections": [{"id": "s", "slides": [{"narration": "短"}]}]},
            "quick",
        )
        msg = format_validation_report(report, "quick")
        assert "0/1" in msg
        assert "quick" in msg

    def test_over_budget_message_includes_worst(self):
        deck = {"sections": [{"id": "s", "slides": [
            {"id": "bad", "narration": "x" * 200},
        ]}]}
        report = check_deck_narration_lengths(deck, "quick")
        msg = format_validation_report(report, "quick")
        assert "1/1" in msg
        assert "bad" in msg
        assert "200" in msg
