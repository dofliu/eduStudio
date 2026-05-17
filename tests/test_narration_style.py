"""iter 92 L2: narration_style preset 載入 + prompt 注入測試.

不實際 call Gemini, 只測 _get_style_directive / _get_persona_directive
跟 prompt template format 出來的字串包含對應 style 內容.
"""
from __future__ import annotations

import pytest

from core.scriptor import (
    LONGFORM_SECTION_PROMPT,
    SECTION_PROMPT,
    _VALID_STYLES,
    _get_persona_directive,
    _get_style_directive,
)


class TestStyleDirectiveLoader:
    def test_all_five_styles_exist(self):
        for name in _VALID_STYLES:
            content = _get_style_directive(name)
            assert content, f"style {name} 該有非空內容"
            assert "教學風格" in content, f"style {name} 該有 header marker"

    def test_default_is_storyteller(self):
        """None / 空字串 → storyteller (跟 iter 82 行為一致)."""
        default = _get_style_directive(None)
        assert default == _get_style_directive("storyteller")
        empty = _get_style_directive("")
        assert empty == _get_style_directive("storyteller")

    def test_unknown_style_fallback_to_storyteller(self):
        """未知 style 字串該 fallback, 不該爆 / 不該空字串."""
        unknown = _get_style_directive("xyz_not_a_real_style")
        assert unknown == _get_style_directive("storyteller")

    def test_case_insensitive(self):
        assert _get_style_directive("WUXIA") == _get_style_directive("wuxia")
        assert _get_style_directive("Comedy") == _get_style_directive("comedy")

    def test_storyteller_keeps_example_phrasing(self):
        """storyteller 該保留 iter 82 的「先舉例再講原理」標誌, 確保向後相容."""
        content = _get_style_directive("storyteller")
        assert "先舉例" in content
        assert "比喻" in content

    def test_academic_uses_definition_first(self):
        content = _get_style_directive("academic")
        assert "定義" in content

    def test_wuxia_uses_martial_terms(self):
        content = _get_style_directive("wuxia")
        # 武俠典型用詞至少出現 1 個
        assert any(t in content for t in ["招式", "心法", "內功"])

    def test_dialogue_uses_question_pattern(self):
        content = _get_style_directive("dialogue")
        assert "你" in content
        # dialogue 該有「你會問 / 你可能會想」之類的 prompt
        assert any(t in content for t in ["問", "?"])

    def test_comedy_mentions_humor_elements(self):
        content = _get_style_directive("comedy")
        # 至少包含 1 個 comedy 風格 marker
        assert any(t in content for t in ["自嘲", "吐槽", "梗"])


class TestPersonaDirective:
    def test_none_returns_empty(self):
        assert _get_persona_directive(None) == ""
        assert _get_persona_directive("") == ""
        assert _get_persona_directive("default") == ""

    def test_nonexistent_persona_returns_empty(self):
        """L3 placeholder — 沒對應 file 該回空字串不爆."""
        assert _get_persona_directive("not_a_real_persona") == ""

    def test_jliu_persona_loads(self):
        """iter 92 v1 scaffold — 劉老師個人風格."""
        content = _get_persona_directive("jliu")
        assert content, "jliu.txt 該有內容"
        assert "勤益" in content or "副教授" in content, "該帶背景資訊"
        # 含口頭禪 / 慣用語段落
        assert any(t in content for t in ["對吧", "你會發現", "白話"])


class TestPromptFormatting:
    """prompt template 該有 {style_directive} + {persona_directive} placeholder."""

    def test_repo_section_prompt_has_style_placeholder(self):
        assert "{style_directive}" in SECTION_PROMPT
        assert "{persona_directive}" in SECTION_PROMPT

    def test_longform_section_prompt_has_style_placeholder(self):
        assert "{style_directive}" in LONGFORM_SECTION_PROMPT
        assert "{persona_directive}" in LONGFORM_SECTION_PROMPT

    def test_format_repo_with_storyteller(self):
        """完整 .format() 不該 KeyError, 結果該含 storyteller 內容."""
        result = SECTION_PROMPT.format(
            deck_title="X", summary="Y", section_idx=1, total_sections=1,
            section_id="s1", section_title="T", section_intent="I",
            section_topics="a, b", section_files_section="(no files)",
            length_directive="quick", slides_per_section_range="3-5",
            narration_chars_range="60-120", narration_seconds_range="20-40",
            style_directive=_get_style_directive("storyteller"),
            persona_directive=_get_persona_directive(None),
        )
        assert "先舉例" in result  # storyteller 標誌

    def test_format_longform_with_wuxia(self):
        result = LONGFORM_SECTION_PROMPT.format(
            deck_title="X", summary="Y", section_idx=1, total_sections=1,
            section_id="s1", section_title="T", section_intent="I",
            section_topics="a, b", document_content="...",
            figures_section="(none)", length_directive="quick",
            slides_per_section_range="3-5",
            narration_chars_range="60-120", narration_seconds_range="20-40",
            style_directive=_get_style_directive("wuxia"),
            persona_directive=_get_persona_directive(None),
        )
        # wuxia 該明顯不同於 storyteller — 找武俠詞
        assert any(t in result for t in ["招式", "心法", "內功"])
