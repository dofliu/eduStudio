"""core.deck schema 轉換測試。

三條轉換 (deck → v1 exam) 對應三條渲染路徑:
- deck_to_exam_schema:        黑板 (BlackboardRenderer)
- deck_to_exam_schema_pptx:   Forest pptx (PptxStyleRenderer)
- deck_to_exam_schema_slides: 投影片底圖 (SlideRenderer, PR-3h)
"""
from __future__ import annotations

import pytest

from core.deck import (
    assert_deck_minimum,
    deck_to_exam_schema,
    deck_to_exam_schema_pptx,
    deck_to_exam_schema_slides,
    normalize_deck,
)


@pytest.fixture
def basic_deck() -> dict:
    """最小完整 deck — 兩章, 每章兩張 slide。"""
    return {
        "deck_title": "範例課程",
        "source_type": "repo",
        "source_meta": {"primary_language": "python"},
        "sections": [
            {
                "id": "intro",
                "title": "專案目的",
                "slides": [
                    {
                        "id": "intro_1",
                        "title": "為什麼有這個專案",
                        "bullets": ["教學影片自動化", "省錄影時間"],
                        "code_snippet": None,
                        "code_lang": None,
                        "file_path": None,
                        "narration": "這個專案要解決 ... 問題。",
                        "notes": None,
                    },
                    {
                        "id": "intro_2",
                        "title": "scan_repo",
                        "bullets": ["走遍整個 repo", "skip binary"],
                        "code_snippet": "def scan_repo(p):\n    pass",
                        "code_lang": "python",
                        "file_path": "core/adapters/repo.py",
                        "narration": "scan_repo 函式做的事 ...",
                        "notes": None,
                    },
                ],
            },
            {
                "id": "ingest",
                "title": "Ingest 流程",
                "slides": [
                    {
                        "id": "ingest_1",
                        "title": "三段 Gemini",
                        "bullets": ["Pass 1 切章", "Pass 2 narration"],
                        "code_snippet": None,
                        "code_lang": None,
                        "file_path": None,
                        "narration": "ingest 階段先 ...",
                        "notes": None,
                    },
                ],
            },
        ],
    }


# ---------- normalize_deck ----------

class TestNormalizeDeck:
    def test_fills_missing_top_level(self):
        deck = {}
        normalize_deck(deck)
        assert deck["deck_title"] == "未命名"
        assert deck["source_type"] == "unknown"
        assert deck["source_meta"] == {}
        assert deck["sections"] == []

    def test_preserves_existing_top_level(self):
        deck = {"deck_title": "保留", "source_type": "repo", "sections": []}
        normalize_deck(deck)
        assert deck["deck_title"] == "保留"
        assert deck["source_type"] == "repo"

    def test_fills_missing_section_fields(self):
        deck = {"sections": [{}]}
        normalize_deck(deck)
        sec = deck["sections"][0]
        assert sec["id"] == "sec1"
        assert sec["title"] == "第 1 章"
        assert sec["slides"] == []

    def test_fills_missing_slide_fields(self):
        deck = {"sections": [{"id": "s1", "slides": [{}]}]}
        normalize_deck(deck)
        sl = deck["sections"][0]["slides"][0]
        assert sl["id"] == "s1_1"
        assert sl["bullets"] == []
        assert sl["code_snippet"] is None
        assert sl["narration"] == ""
        # iter 52: image_path 預設 None
        assert sl["image_path"] is None

    def test_preserves_existing_image_path(self):
        """iter 52: 已有 image_path 該被保留 (normalize 只補不蓋)."""
        deck = {"sections": [{"slides": [{"image_path": "fig_p3_1"}]}]}
        normalize_deck(deck)
        assert deck["sections"][0]["slides"][0]["image_path"] == "fig_p3_1"

    def test_icon_overlay_defaults_to_none(self):
        """iter 100 (E2-4): icon_overlay 預設 None — 動態視覺素材 RFC, 舊 deck 不該炸."""
        deck = {"sections": [{"id": "s1", "slides": [{}]}]}
        normalize_deck(deck)
        assert deck["sections"][0]["slides"][0]["icon_overlay"] is None

    def test_preserves_existing_icon_overlay(self):
        """已有 icon_overlay 該被保留 (normalize 只補不蓋)."""
        overlay = [
            {"path": "generic/question.svg", "position": "top-right",
             "size_ratio": 0.12, "start_ms": None, "duration_ms": None},
        ]
        deck = {"sections": [{"slides": [{"icon_overlay": overlay}]}]}
        normalize_deck(deck)
        assert deck["sections"][0]["slides"][0]["icon_overlay"] == overlay


# ---------- assert_deck_minimum ----------

class TestAssertDeckMinimum:
    def test_passes_on_valid(self, basic_deck):
        assert_deck_minimum(basic_deck)  # 不丟例外

    def test_fails_on_no_sections(self):
        with pytest.raises(ValueError, match="缺 sections"):
            assert_deck_minimum({"sections": []})

    def test_fails_on_section_no_slides(self):
        deck = {"sections": [{"id": "s1", "slides": []}]}
        with pytest.raises(ValueError, match="沒有 slides"):
            assert_deck_minimum(deck)

    def test_fails_on_empty_narration(self):
        deck = {
            "sections": [{
                "id": "s1",
                "slides": [{"id": "s1_1", "narration": ""}],
            }],
        }
        with pytest.raises(ValueError, match="narration 為空"):
            assert_deck_minimum(deck)


# ---------- deck_to_exam_schema (黑板) ----------

class TestDeckToExamSchema:
    def test_basic_conversion(self, basic_deck):
        exam = deck_to_exam_schema(basic_deck)
        assert exam["exam_title"] == "範例課程"
        assert exam["source_type"] == "deck"  # 跟 slides 區分
        assert len(exam["problems"]) == 2

    def test_section_id_preserved(self, basic_deck):
        exam = deck_to_exam_schema(basic_deck)
        assert exam["problems"][0]["id"] == "intro"
        assert exam["problems"][1]["id"] == "ingest"

    def test_problem_number_format(self, basic_deck):
        exam = deck_to_exam_schema(basic_deck)
        assert exam["problems"][0]["number"] == "第 1 章 專案目的"
        assert exam["problems"][1]["number"] == "第 2 章 Ingest 流程"

    def test_step_count_matches_slides(self, basic_deck):
        exam = deck_to_exam_schema(basic_deck)
        assert len(exam["problems"][0]["steps"]) == 2
        assert len(exam["problems"][1]["steps"]) == 1

    def test_step_display_includes_title_and_bullets(self, basic_deck):
        exam = deck_to_exam_schema(basic_deck)
        display = exam["problems"][0]["steps"][0]["display"]
        assert "為什麼有這個專案" in display
        assert "教學影片自動化" in display
        assert "•" in display    # bullet marker

    def test_step_display_includes_code(self, basic_deck):
        exam = deck_to_exam_schema(basic_deck)
        display = exam["problems"][0]["steps"][1]["display"]
        assert "def scan_repo" in display
        assert "core/adapters/repo.py" in display    # file path 當註解 header

    def test_skips_section_with_empty_slides(self):
        deck = {
            "deck_title": "test",
            "sections": [
                {"id": "s1", "title": "有內容", "slides": [{"id": "s1_1", "narration": "n"}]},
                {"id": "s2", "title": "空", "slides": []},
            ],
        }
        exam = deck_to_exam_schema(deck)
        assert len(exam["problems"]) == 1
        assert exam["problems"][0]["id"] == "s1"


# ---------- deck_to_exam_schema_pptx (Forest 主題) ----------

class TestDeckToExamSchemaPptx:
    def test_step_has_pptx_slide_bg_type(self, basic_deck):
        exam = deck_to_exam_schema_pptx(basic_deck)
        for prob in exam["problems"]:
            for step in prob["steps"]:
                assert step["bg_type"] == "pptx_slide"

    def test_step_preserves_renderer_fields(self, basic_deck):
        exam = deck_to_exam_schema_pptx(basic_deck)
        # 第一章第二張 slide 有 code_snippet
        step = exam["problems"][0]["steps"][1]
        assert step["title"] == "scan_repo"
        assert step["bullets"] == ["走遍整個 repo", "skip binary"]
        assert step["code_snippet"] == "def scan_repo(p):\n    pass"
        assert step["code_lang"] == "python"
        assert step["file_path"] == "core/adapters/repo.py"
        assert step["section_title"] == "專案目的"

    def test_source_type_is_deck_pptx(self, basic_deck):
        exam = deck_to_exam_schema_pptx(basic_deck)
        assert exam["source_type"] == "deck_pptx"

    def test_filters_empty_bullets(self):
        # bullets 含空字串應該被過濾, 不畫到投影片
        deck = {
            "deck_title": "t",
            "sections": [{
                "id": "s1", "title": "T",
                "slides": [{
                    "id": "s1_1", "title": "x",
                    "bullets": ["有內容", "", None, "另一條"],
                    "narration": "n",
                }],
            }],
        }
        exam = deck_to_exam_schema_pptx(deck)
        assert exam["problems"][0]["steps"][0]["bullets"] == ["有內容", "另一條"]

    def test_image_path_passed_through_to_step(self):
        """iter 53: deck_to_exam_schema_pptx 該把 slide.image_path 帶到 step."""
        deck = {
            "deck_title": "t",
            "sections": [{
                "id": "s1", "title": "T",
                "slides": [
                    {"id": "s1_1", "title": "x", "bullets": ["a"],
                     "narration": "n", "image_path": "fig_p3_1"},
                    {"id": "s1_2", "title": "y", "bullets": ["b"],
                     "narration": "n", "image_path": None},
                ],
            }],
        }
        exam = deck_to_exam_schema_pptx(deck)
        steps = exam["problems"][0]["steps"]
        assert steps[0]["image_path"] == "fig_p3_1"
        assert steps[1]["image_path"] is None

    def test_image_path_missing_defaults_to_none(self):
        """slide 沒 image_path key → step 該補 None (不該 KeyError)."""
        deck = {
            "sections": [{
                "id": "s1", "title": "T",
                "slides": [{"id": "s1_1", "title": "x", "bullets": ["a"],
                            "narration": "n"}],
            }],
        }
        exam = deck_to_exam_schema_pptx(deck)
        assert exam["problems"][0]["steps"][0]["image_path"] is None

    def test_icon_overlay_passed_through_to_step(self):
        """iter 100 (E2-4): pptx 路徑該把 slide.icon_overlay 帶到 step."""
        overlay = [
            {"path": "domain_wind/wind_turbine.svg", "position": "bottom-right",
             "size_ratio": 0.18},
        ]
        deck = {
            "deck_title": "t",
            "sections": [{
                "id": "s1", "title": "T",
                "slides": [
                    {"id": "s1_1", "title": "x", "bullets": ["a"],
                     "narration": "n", "icon_overlay": overlay},
                    {"id": "s1_2", "title": "y", "bullets": ["b"],
                     "narration": "n", "icon_overlay": None},
                ],
            }],
        }
        exam = deck_to_exam_schema_pptx(deck)
        steps = exam["problems"][0]["steps"]
        assert steps[0]["icon_overlay"] == overlay
        assert steps[1]["icon_overlay"] is None

    def test_icon_overlay_missing_defaults_to_none(self):
        """slide 沒 icon_overlay key → step 該補 None (不該 KeyError, 舊 deck 相容)."""
        deck = {
            "sections": [{
                "id": "s1", "title": "T",
                "slides": [{"id": "s1_1", "title": "x", "bullets": ["a"],
                            "narration": "n"}],
            }],
        }
        exam = deck_to_exam_schema_pptx(deck)
        assert exam["problems"][0]["steps"][0]["icon_overlay"] is None


# ---------- deck_to_exam_schema_slides (PR-3h, 簡報原圖) ----------

class TestDeckToExamSchemaSlides:
    @pytest.fixture
    def slide_deck(self) -> dict:
        return {
            "deck_title": "Chap05 講解",
            "source_type": "slides",
            "sections": [{
                "id": "ch1",
                "title": "穩定性分析簡介",
                "slides": [
                    {
                        "id": "ch1_p001",
                        "title": "投影片 1",
                        "bullets": [],
                        "narration": "第一頁旁白。",
                        "bg_image": "slides/Chap05/p001.png",
                        "bg_type": "slide",
                        "layout": "full",
                    },
                    {
                        "id": "ch1_p002",
                        "title": "投影片 2",
                        "bullets": [],
                        "narration": "第二頁旁白。",
                        "bg_image": "slides/Chap05/p002.png",
                        "bg_type": "slide",
                        "layout": "full",
                    },
                ],
            }],
        }

    def test_bg_image_preserved(self, slide_deck):
        exam = deck_to_exam_schema_slides(slide_deck)
        steps = exam["problems"][0]["steps"]
        assert steps[0]["bg_image"] == "slides/Chap05/p001.png"
        assert steps[1]["bg_image"] == "slides/Chap05/p002.png"

    def test_bg_type_default_slide(self, slide_deck):
        exam = deck_to_exam_schema_slides(slide_deck)
        steps = exam["problems"][0]["steps"]
        assert steps[0]["bg_type"] == "slide"

    def test_layout_preserved(self, slide_deck):
        exam = deck_to_exam_schema_slides(slide_deck)
        steps = exam["problems"][0]["steps"]
        assert steps[0]["layout"] == "full"

    def test_source_type_is_slides(self, slide_deck):
        exam = deck_to_exam_schema_slides(slide_deck)
        assert exam["source_type"] == "slides"

    def test_section_id_preserved_for_section_render(self, slide_deck):
        # PR-4a: section render 用 section_id, deck → exam 後 problems[].id 必須等於原 section id
        exam = deck_to_exam_schema_slides(slide_deck)
        assert exam["problems"][0]["id"] == "ch1"

    def test_default_bg_type_when_missing(self):
        # slide 沒帶 bg_type 時, 預設給 "slide" (PR-3h 設計)
        deck = {
            "deck_title": "t",
            "sections": [{
                "id": "ch1", "title": "T",
                "slides": [{
                    "id": "ch1_p1", "title": "p1",
                    "bullets": [], "narration": "n",
                    "bg_image": "slides/x/p001.png",
                    # 故意不帶 bg_type / layout
                }],
            }],
        }
        exam = deck_to_exam_schema_slides(deck)
        step = exam["problems"][0]["steps"][0]
        assert step["bg_type"] == "slide"
        assert step["layout"] == "full"

    def test_title_and_bullets_passthrough_for_split_left(self):
        # Phase 4: split-left layout 要讀 step.title + step.bullets,
        # deck → v1 exam 必須透傳這兩欄 (full layout 不讀, 但仍透傳保 schema 一致)
        deck = {
            "deck_title": "t",
            "sections": [{
                "id": "ch1", "title": "T",
                "slides": [{
                    "id": "ch1_p1",
                    "title": "傅立葉頻譜分析",
                    "bullets": ["定義", "用途", "實例"],
                    "narration": "n",
                    "bg_image": "slides/x/p001.png",
                    "layout": "split-left",
                }],
            }],
        }
        exam = deck_to_exam_schema_slides(deck)
        step = exam["problems"][0]["steps"][0]
        assert step["layout"] == "split-left"
        assert step["title"] == "傅立葉頻譜分析"
        assert step["bullets"] == ["定義", "用途", "實例"]
        # display 仍保持向後相容 (= title 或 "投影片")
        assert step["display"] == "傅立葉頻譜分析"

    def test_icon_overlay_passed_through_to_step_slides(self):
        """iter 100 (E2-4): slides_pdf 路徑也要把 icon_overlay 透傳 (review UI 共用)."""
        overlay = [
            {"path": "generic/lightbulb.svg", "position": "top-right",
             "size_ratio": 0.10},
        ]
        deck = {
            "deck_title": "t",
            "sections": [{
                "id": "ch1", "title": "T",
                "slides": [{
                    "id": "ch1_p1", "title": "x", "bullets": [],
                    "narration": "n", "bg_image": "p.png", "layout": "full",
                    "icon_overlay": overlay,
                }],
            }],
        }
        exam = deck_to_exam_schema_slides(deck)
        assert exam["problems"][0]["steps"][0]["icon_overlay"] == overlay

    def test_icon_overlay_missing_defaults_to_none_slides(self):
        """slide 沒 icon_overlay → slides 路徑 step 該補 None."""
        deck = {
            "deck_title": "t",
            "sections": [{
                "id": "ch1", "title": "T",
                "slides": [{
                    "id": "ch1_p1", "title": "x", "bullets": [],
                    "narration": "n", "bg_image": "p.png",
                }],
            }],
        }
        exam = deck_to_exam_schema_slides(deck)
        assert exam["problems"][0]["steps"][0]["icon_overlay"] is None

    def test_bullets_independent_copy(self):
        # 透傳 bullets 不能跟原 slide 共用 list, 不然 caller mutate 會污染原 deck
        original_bullets = ["a", "b"]
        deck = {
            "deck_title": "t",
            "sections": [{
                "id": "ch1", "title": "T",
                "slides": [{
                    "id": "ch1_p1", "title": "x", "bullets": original_bullets,
                    "narration": "n", "bg_image": "p.png",
                    "layout": "split-left",
                }],
            }],
        }
        exam = deck_to_exam_schema_slides(deck)
        exam["problems"][0]["steps"][0]["bullets"].append("c")
        assert original_bullets == ["a", "b"]    # 原 list 未被波及
