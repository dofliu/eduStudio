"""core/intro_rewriter.py — iter 42 開場白多樣化.

純函式 + dict 處理, 不打 LLM 不開 process, 全部 unit test 直跑.
"""
from __future__ import annotations

import pytest

from core.intro_rewriter import (
    AUDIENCE_BY_SOURCE_TYPE,
    GENERAL_VARIANTS,
    STUDENT_VARIANTS,
    _pick_variant,
    _stable_seed,
    rewrite_deck_intros,
    rewrite_narration_intro,
)


class TestStableSeed:
    """_stable_seed: 跨 process 穩定的 hash, 不靠 PYTHONHASHSEED."""

    def test_same_key_same_seed(self):
        assert _stable_seed("abc") == _stable_seed("abc")

    def test_different_keys_different_seeds(self):
        assert _stable_seed("abc") != _stable_seed("xyz")

    def test_empty_string_works(self):
        # 不該 raise
        seed = _stable_seed("")
        assert isinstance(seed, int)
        assert seed >= 0


class TestPickVariant:
    def test_student_audience_returns_student_variant(self):
        v = _pick_variant("student", "q1")
        assert v in STUDENT_VARIANTS

    def test_general_audience_returns_general_variant(self):
        v = _pick_variant("general", "intro")
        assert v in GENERAL_VARIANTS

    def test_unknown_audience_returns_none(self):
        assert _pick_variant("alien", "q1") is None

    def test_same_key_same_variant(self):
        """同 key 同 audience 多次呼叫結果一致."""
        v1 = _pick_variant("student", "q1")
        v2 = _pick_variant("student", "q1")
        assert v1 == v2

    def test_different_keys_can_differ(self):
        """跨足夠多 key 至少要有 2 個以上不同變體 (不是全部都選同一個)."""
        seen = set()
        for i in range(50):
            seen.add(_pick_variant("student", f"q{i}"))
        # 變體庫 8 個, 50 個 key 應該至少撞到 3 個以上
        assert len(seen) >= 3


class TestRewriteNarrationIntro:
    """單句旁白開頭問候語替換."""

    def test_replace_kakuei_tongxue(self):
        out = rewrite_narration_intro("各位同學好,這題我們看", "student", "q1")
        assert "各位同學好" not in out or out.startswith("各位同學好,")
        # 至少要替換成某個 student 變體
        assert any(out.startswith(v) for v in STUDENT_VARIANTS)
        # 後段內容保留
        assert "這題我們看" in out

    def test_replace_dajiahao(self):
        out = rewrite_narration_intro("大家好,今天聊聊", "general", "intro")
        assert any(out.startswith(v) for v in GENERAL_VARIANTS)
        assert "今天聊聊" in out

    def test_no_greeting_returns_unchanged(self):
        """沒問候語 → 不該硬塞變體進去."""
        original = "函式 f(x) 的定義是,先看分母"
        out = rewrite_narration_intro(original, "student", "q1")
        assert out == original

    def test_empty_narration_returns_empty(self):
        assert rewrite_narration_intro("", "student", "q1") == ""

    def test_whitespace_only_returns_unchanged(self):
        assert rewrite_narration_intro("   ", "student", "q1") == "   "

    def test_greeting_with_full_width_comma(self):
        out = rewrite_narration_intro("各位同學好,接下來解這道題", "student", "q1")
        assert "接下來解這道題" in out

    def test_greeting_with_period(self):
        out = rewrite_narration_intro("大家好。今天的主題", "general", "doc")
        assert "今天的主題" in out

    def test_stable_across_calls(self):
        """同 key 兩次跑結果一致."""
        n = "各位同學好,接下來"
        a = rewrite_narration_intro(n, "student", "q1")
        b = rewrite_narration_intro(n, "student", "q1")
        assert a == b

    def test_only_greeting_no_rest(self):
        """只有問候語沒後文 → 替換後句尾仍乾淨."""
        out = rewrite_narration_intro("各位同學好。", "student", "q1")
        # 不該變成 "xxx,," 雙逗號
        assert ",," not in out


class TestRewriteDeckIntros:
    """deck 級別: 走兩種 schema."""

    def test_v1_exam_schema_rewrites_first_step_only(self):
        deck = {
            "exam_title": "材料力學",
            "problems": [
                {
                    "id": "q1",
                    "steps": [
                        {"narration": "各位同學好,先看題目"},
                        {"narration": "各位同學好,第二步計算"},
                    ],
                },
            ],
        }
        out = rewrite_deck_intros(deck, "exam_pdf")
        first = out["problems"][0]["steps"][0]["narration"]
        second = out["problems"][0]["steps"][1]["narration"]
        # 第一步該被改 (不再是「各位同學好」開頭, 除非剛好挑到同樣 variant)
        # 第二步不該動
        assert second == "各位同學好,第二步計算"
        # 第一步至少要還是 student 變體開頭
        assert any(first.startswith(v) for v in STUDENT_VARIANTS)

    def test_new_deck_schema_rewrites_first_slide_per_section(self):
        deck = {
            "deck_title": "MSG-IRAG",
            "sections": [
                {
                    "id": "intro",
                    "slides": [
                        {"narration": "大家好,這篇文章"},
                        {"narration": "大家好,第二張"},
                    ],
                },
                {
                    "id": "method",
                    "slides": [
                        {"narration": "大家好,方法部分"},
                    ],
                },
            ],
        }
        out = rewrite_deck_intros(deck, "document")
        # section "intro" 第一張 narration 被改
        assert out["sections"][0]["slides"][0]["narration"] != "大家好,這篇文章"
        # 第二張 narration 不該動
        assert out["sections"][0]["slides"][1]["narration"] == "大家好,第二張"
        # section "method" 第一張也被改
        assert out["sections"][1]["slides"][0]["narration"] != "大家好,方法部分"

    def test_source_type_affects_audience(self):
        """同樣 deck, 不同 source_type 出不同變體庫的開頭."""
        deck_student_input = {
            "problems": [
                {"id": "q1", "steps": [{"narration": "各位同學好,題目"}]},
            ],
        }
        deck_general_input = {
            "problems": [
                {"id": "q1", "steps": [{"narration": "大家好,內容"}]},
            ],
        }
        out_student = rewrite_deck_intros(deck_student_input, "exam_pdf")
        out_general = rewrite_deck_intros(deck_general_input, "document")
        s = out_student["problems"][0]["steps"][0]["narration"]
        g = out_general["problems"][0]["steps"][0]["narration"]
        assert any(s.startswith(v) for v in STUDENT_VARIANTS)
        assert any(g.startswith(v) for v in GENERAL_VARIANTS)

    def test_empty_deck_returns_empty(self):
        assert rewrite_deck_intros({}, "exam_pdf") == {}

    def test_unknown_schema_returns_unchanged(self):
        weird = {"foo": "bar"}
        assert rewrite_deck_intros(weird, "exam_pdf") == weird

    def test_unknown_source_type_falls_back_to_student(self):
        deck = {"problems": [
            {"id": "q1", "steps": [{"narration": "各位同學好,內容"}]},
        ]}
        out = rewrite_deck_intros(deck, "????")
        first = out["problems"][0]["steps"][0]["narration"]
        # 應該還是 student 變體
        assert any(first.startswith(v) for v in STUDENT_VARIANTS)

    def test_empty_steps_skipped(self):
        deck = {"problems": [{"id": "q1", "steps": []}]}
        out = rewrite_deck_intros(deck, "exam_pdf")
        assert out["problems"][0]["steps"] == []

    def test_stable_rewriting(self):
        """同 deck 跑兩次結果一致 (不會跳)."""
        import copy
        deck = {"problems": [
            {"id": "q1", "steps": [{"narration": "各位同學好,內容"}]},
        ]}
        a = rewrite_deck_intros(copy.deepcopy(deck), "exam_pdf")
        b = rewrite_deck_intros(copy.deepcopy(deck), "exam_pdf")
        assert a == b


class TestAudienceMapping:
    """source_type → audience 的對應, 跟用戶確認的規則一致."""

    def test_exam_pdf_is_student(self):
        assert AUDIENCE_BY_SOURCE_TYPE["exam_pdf"] == "student"

    def test_slides_pdf_is_student(self):
        assert AUDIENCE_BY_SOURCE_TYPE["slides_pdf"] == "student"

    def test_document_is_general(self):
        assert AUDIENCE_BY_SOURCE_TYPE["document"] == "general"

    def test_repo_is_general(self):
        assert AUDIENCE_BY_SOURCE_TYPE["repo"] == "general"

    def test_url_is_general(self):
        assert AUDIENCE_BY_SOURCE_TYPE["url"] == "general"
