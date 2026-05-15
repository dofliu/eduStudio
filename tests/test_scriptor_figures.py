"""core/scriptor.py — iter 52 figure helpers.

只測純函式 (_format_figures_for_prompt / _sanitize_slide_image_paths),
不打 Gemini. script_long_form 整條 e2e 需要 mock client, 範圍超出本檔.
"""
from __future__ import annotations

from core.scriptor import (
    _attach_ai_diagrams_to_first_slide,
    _dedupe_image_paths_across_deck,
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


class TestDedupeImagePathsAcrossDeck:
    """iter 52b: 跨 section 去 image_path 重複."""

    def test_dedupe_across_sections(self):
        """實測重現: fig_p6_1 在 intro 跟 method_results 都被選 → 留第一個."""
        sections = [
            {"id": "intro", "slides": [
                {"id": "s1", "image_path": None},
                {"id": "s2", "image_path": "fig_p6_1"},
            ]},
            {"id": "method", "slides": [
                {"id": "m1", "image_path": "fig_p6_1"},   # 重複, 該清掉
                {"id": "m2", "image_path": "fig_p18_2"},
            ]},
            {"id": "impl", "slides": [
                {"id": "i1", "image_path": "fig_p18_2"},   # 重複, 該清掉
            ]},
        ]
        _dedupe_image_paths_across_deck(sections)
        assert sections[0]["slides"][1]["image_path"] == "fig_p6_1"
        assert sections[1]["slides"][0]["image_path"] is None      # dedup
        assert sections[1]["slides"][1]["image_path"] == "fig_p18_2"
        assert sections[2]["slides"][0]["image_path"] is None      # dedup

    def test_unique_paths_unchanged(self):
        sections = [
            {"slides": [{"image_path": "fig_p3_1"}, {"image_path": "fig_p4_1"}]},
            {"slides": [{"image_path": "fig_p5_1"}]},
        ]
        _dedupe_image_paths_across_deck(sections)
        assert sections[0]["slides"][0]["image_path"] == "fig_p3_1"
        assert sections[0]["slides"][1]["image_path"] == "fig_p4_1"
        assert sections[1]["slides"][0]["image_path"] == "fig_p5_1"

    def test_empty_deck_safe(self):
        sections = []
        _dedupe_image_paths_across_deck(sections)
        assert sections == []

    def test_all_null_unchanged(self):
        sections = [
            {"slides": [{"image_path": None}, {"image_path": None}]},
        ]
        _dedupe_image_paths_across_deck(sections)
        assert all(s["image_path"] is None for s in sections[0]["slides"])


class TestAttachAiDiagramsToFirstSlide:
    """iter 56d: AI 生圖 (id = ai_<section_id>) 自動配給對應 section 第一張 slide."""

    def test_attaches_to_first_slide_when_null(self):
        sections = [
            {"id": "intro", "slides": [
                {"id": "intro_1", "image_path": None},
                {"id": "intro_2", "image_path": None},
            ]},
            {"id": "method", "slides": [
                {"id": "method_1", "image_path": None},
            ]},
        ]
        figure_ids = {"ai_intro", "ai_method"}
        _attach_ai_diagrams_to_first_slide(sections, figure_ids)
        # 第一張 slide 該被配上 AI 圖
        assert sections[0]["slides"][0]["image_path"] == "ai_intro"
        # 第二張不該動
        assert sections[0]["slides"][1]["image_path"] is None
        # 另一 section 同樣處理
        assert sections[1]["slides"][0]["image_path"] == "ai_method"

    def test_respects_existing_image_path(self):
        """第一張已有別張圖 (Gemini 配的 / 用戶手動配的) → 不覆寫."""
        sections = [{
            "id": "intro",
            "slides": [
                {"id": "intro_1", "image_path": "fig_p3_1"},   # 既有 PDF 圖
                {"id": "intro_2", "image_path": None},
            ],
        }]
        _attach_ai_diagrams_to_first_slide(sections, {"ai_intro", "fig_p3_1"})
        # 不該被 ai_intro 覆蓋
        assert sections[0]["slides"][0]["image_path"] == "fig_p3_1"

    def test_skip_if_ai_fig_already_used_in_section(self):
        """Gemini 自己已挑了 ai_<sec> 配給其他 slide → 不要再配第一張造成 section 內重複."""
        sections = [{
            "id": "method",
            "slides": [
                {"id": "method_1", "image_path": None},
                {"id": "method_2", "image_path": "ai_method"},   # 已用
                {"id": "method_3", "image_path": None},
            ],
        }]
        _attach_ai_diagrams_to_first_slide(sections, {"ai_method"})
        # 第一張不該再被配, 否則 section 內 ai_method 重複
        assert sections[0]["slides"][0]["image_path"] is None
        assert sections[0]["slides"][1]["image_path"] == "ai_method"

    def test_skip_section_without_matching_ai_fig(self):
        """figure_ids 內沒對應的 ai_<section_id> → 該 section 不動 (沒生 AI 圖)."""
        sections = [{
            "id": "intro",
            "slides": [{"id": "intro_1", "image_path": None}],
        }]
        # figure_ids 只有 PDF 圖, 沒 ai_intro
        _attach_ai_diagrams_to_first_slide(sections, {"fig_p3_1"})
        assert sections[0]["slides"][0]["image_path"] is None

    def test_skip_section_without_id(self):
        sections = [{"slides": [{"image_path": None}]}]
        _attach_ai_diagrams_to_first_slide(sections, {"ai_xxx"})
        assert sections[0]["slides"][0]["image_path"] is None

    def test_skip_section_without_slides(self):
        sections = [{"id": "intro", "slides": []}]
        _attach_ai_diagrams_to_first_slide(sections, {"ai_intro"})
        # 沒 slide 不該炸
        assert sections[0]["slides"] == []

    def test_empty_sections_safe(self):
        sections = []
        _attach_ai_diagrams_to_first_slide(sections, {"ai_intro"})
        assert sections == []

    def test_mixed_sections(self):
        """有些 section 有 AI 圖, 有些沒 (跨 section 各自獨立)."""
        sections = [
            {"id": "intro", "slides": [{"image_path": None}]},
            {"id": "no_ai", "slides": [{"image_path": None}]},
            {"id": "results", "slides": [{"image_path": "fig_p5_1"}]},
        ]
        # 只有 intro 跟 results 生了 AI 圖, no_ai section 沒
        _attach_ai_diagrams_to_first_slide(sections, {"ai_intro", "ai_results"})
        assert sections[0]["slides"][0]["image_path"] == "ai_intro"
        assert sections[1]["slides"][0]["image_path"] is None
        # results 第一張已有圖 (PDF), 不該被覆寫
        assert sections[2]["slides"][0]["image_path"] == "fig_p5_1"

    def test_mermaid_prefix_also_attached(self):
        """iter 57b: mermaid_<sec_id> 也該被自動 attach."""
        sections = [
            {"id": "intro", "slides": [{"image_path": None}]},
            {"id": "method", "slides": [{"image_path": None}]},
        ]
        # 只有 mermaid 圖 (沒 AI image)
        _attach_ai_diagrams_to_first_slide(
            sections, {"mermaid_intro", "mermaid_method"},
        )
        assert sections[0]["slides"][0]["image_path"] == "mermaid_intro"
        assert sections[1]["slides"][0]["image_path"] == "mermaid_method"

    def test_ai_prefix_priority_over_mermaid(self):
        """iter 57b: 同 section 兩種圖都有時, ai_ 優先 (image gen 通常更漂亮)."""
        sections = [{"id": "intro", "slides": [{"image_path": None}]}]
        # ai_intro 跟 mermaid_intro 都生成了
        _attach_ai_diagrams_to_first_slide(
            sections, {"ai_intro", "mermaid_intro"},
        )
        # 應該配 ai_intro (優先)
        assert sections[0]["slides"][0]["image_path"] == "ai_intro"

    def test_falls_back_to_mermaid_when_no_ai(self):
        """ai_<sec> 沒有但 mermaid_<sec> 有, 該配 mermaid."""
        sections = [{"id": "intro", "slides": [{"image_path": None}]}]
        _attach_ai_diagrams_to_first_slide(
            sections, {"mermaid_intro"},   # 只有 mermaid
        )
        assert sections[0]["slides"][0]["image_path"] == "mermaid_intro"
