"""core/scriptor.py — iter 52 figure helpers.

只測純函式 (_format_figures_for_prompt / _sanitize_slide_image_paths),
不打 Gemini. script_long_form 整條 e2e 需要 mock client, 範圍超出本檔.
"""
from __future__ import annotations

from core.scriptor import (
    _format_figures_for_prompt,
    _sanitize_slide_image_paths,
)


class TestFormatFiguresForPrompt:
    def test_empty_returns_helpful_message(self):
        out = _format_figures_for_prompt([])
        # 應該有「沒抽到」之類的提示, 讓 Gemini 知道是 prompt 設計而不是 bug
        assert "null" in out

    def test_single_figure_formatted(self):
        figs = [{
            "id": "fig_p3_1", "page_no": 3, "width": 400, "height": 300,
            "caption_hint": "Figure 1: arch",
        }]
        out = _format_figures_for_prompt(figs)
        assert "fig_p3_1" in out
        assert "page 3" in out
        assert "400" in out
        assert "Figure 1" in out

    def test_no_caption_hides_caption_part(self):
        figs = [{
            "id": "fig_p3_1", "page_no": 3, "width": 400, "height": 300,
            "caption_hint": "",
        }]
        out = _format_figures_for_prompt(figs)
        assert "fig_p3_1" in out
        # 沒 caption 不該有 dash separator
        assert " — " not in out

    def test_sorted_by_page_then_id(self):
        figs = [
            {"id": "fig_p7_1", "page_no": 7, "width": 400, "height": 300, "caption_hint": ""},
            {"id": "fig_p3_1", "page_no": 3, "width": 400, "height": 300, "caption_hint": ""},
            {"id": "fig_p3_2", "page_no": 3, "width": 400, "height": 300, "caption_hint": ""},
        ]
        out = _format_figures_for_prompt(figs)
        lines = out.split("\n")
        # 順序: p3_1 → p3_2 → p7_1
        assert lines[0].startswith("- fig_p3_1")
        assert lines[1].startswith("- fig_p3_2")
        assert lines[2].startswith("- fig_p7_1")


class TestSanitizeSlideImagePaths:
    def test_keeps_valid_id(self):
        sec = {"slides": [{"id": "s1", "image_path": "fig_p3_1"}]}
        _sanitize_slide_image_paths(sec, {"fig_p3_1", "fig_p4_1"})
        assert sec["slides"][0]["image_path"] == "fig_p3_1"

    def test_strips_invalid_id(self):
        """Gemini 亂打不存在的 id 應該被清掉."""
        sec = {"slides": [{"id": "s1", "image_path": "fig_p99_99"}]}
        _sanitize_slide_image_paths(sec, {"fig_p3_1"})
        assert sec["slides"][0]["image_path"] is None

    def test_strips_non_string(self):
        sec = {"slides": [{"id": "s1", "image_path": 123}]}
        _sanitize_slide_image_paths(sec, {"fig_p3_1"})
        assert sec["slides"][0]["image_path"] is None

    def test_missing_image_path_added_as_none(self):
        sec = {"slides": [{"id": "s1"}]}
        _sanitize_slide_image_paths(sec, {"fig_p3_1"})
        assert sec["slides"][0]["image_path"] is None

    def test_duplicate_within_section_keeps_first(self):
        """同 section 內同 figure 用兩次, 第二次該清掉."""
        sec = {"slides": [
            {"id": "s1", "image_path": "fig_p3_1"},
            {"id": "s2", "image_path": "fig_p3_1"},   # 重複
            {"id": "s3", "image_path": "fig_p4_1"},
        ]}
        _sanitize_slide_image_paths(sec, {"fig_p3_1", "fig_p4_1"})
        assert sec["slides"][0]["image_path"] == "fig_p3_1"
        assert sec["slides"][1]["image_path"] is None
        assert sec["slides"][2]["image_path"] == "fig_p4_1"

    def test_empty_slides_list_safe(self):
        sec = {"slides": []}
        _sanitize_slide_image_paths(sec, {"fig_p3_1"})
        assert sec["slides"] == []

    def test_no_slides_key_safe(self):
        sec = {}
        _sanitize_slide_image_paths(sec, {"fig_p3_1"})
        # 不該炸, 也不該加 slides key
        assert "slides" not in sec

    def test_null_image_path_stays_null(self):
        sec = {"slides": [{"id": "s1", "image_path": None}]}
        _sanitize_slide_image_paths(sec, {"fig_p3_1"})
        assert sec["slides"][0]["image_path"] is None
