"""core/outro_gen.py — iter 63 結尾 section 生成. 純函式, 沒 LLM call."""
from __future__ import annotations

from core.outro_gen import build_outro_section, section_is_outro


class TestBuildOutroSection:
    def test_returns_valid_section_dict(self):
        sec = build_outro_section(speaker="劉老師", org="DofLab")
        assert sec["id"] == "_outro"
        assert "slides" in sec
        assert len(sec["slides"]) == 1

    def test_slide_has_outro_bg_type(self):
        sec = build_outro_section()
        assert sec["slides"][0]["bg_type"] == "outro"

    def test_meta_fields_in_slide(self):
        sec = build_outro_section(
            speaker="John", org="Lab", url="example.com",
        )
        slide = sec["slides"][0]
        assert slide["outro_speaker"] == "John"
        assert slide["outro_org"] == "Lab"
        assert slide["outro_url"] == "example.com"

    def test_default_thanks_text(self):
        sec = build_outro_section()
        assert sec["slides"][0]["title"] == "謝謝聆聽"

    def test_custom_thanks_text(self):
        sec = build_outro_section(thanks_text="See you next time")
        assert sec["slides"][0]["title"] == "See you next time"

    def test_default_url(self):
        sec = build_outro_section()
        assert sec["slides"][0]["outro_url"] == "doflab.cc"

    def test_empty_url_uses_default(self):
        sec = build_outro_section(url="   ")
        assert sec["slides"][0]["outro_url"] == "doflab.cc"

    def test_narration_includes_speaker_org_url(self):
        sec = build_outro_section(
            speaker="劉老師", org="DofLab", url="doflab.cc",
        )
        narration = sec["slides"][0]["narration"]
        assert "劉老師" in narration
        assert "DofLab" in narration
        assert "doflab.cc" in narration

    def test_narration_override_replaces_template(self):
        """narration_override 非空 → 用 override 不套模板."""
        custom = "今天就到這裡, 感謝各位."
        sec = build_outro_section(
            speaker="X", org="Y", narration_override=custom,
        )
        assert sec["slides"][0]["narration"] == custom

    def test_narration_override_empty_falls_back(self):
        sec = build_outro_section(
            speaker="講者A", org="單位B", narration_override="",
        )
        narration = sec["slides"][0]["narration"]
        assert "講者A" in narration

    def test_empty_speaker_uses_fallback(self):
        sec = build_outro_section(speaker="", org="Lab")
        narration = sec["slides"][0]["narration"]
        assert "劉老師" in narration   # fallback default

    def test_no_bullets(self):
        sec = build_outro_section()
        assert sec["slides"][0]["bullets"] == []

    def test_image_path_none(self):
        sec = build_outro_section()
        assert sec["slides"][0]["image_path"] is None

    def test_section_title_empty(self):
        """結尾 slide 不畫 section banner."""
        sec = build_outro_section()
        assert sec["slides"][0]["section_title"] == ""


class TestSectionIsOutro:
    def test_outro_section_by_id(self):
        sec = build_outro_section()
        assert section_is_outro(sec) is True

    def test_outro_section_by_bg_type(self):
        sec = {"id": "custom_id", "slides": [{"bg_type": "outro"}]}
        assert section_is_outro(sec) is True

    def test_normal_section_not_outro(self):
        sec = {"id": "intro", "slides": [{"bg_type": "pptx_slide"}]}
        assert section_is_outro(sec) is False

    def test_empty_section(self):
        assert section_is_outro({}) is False
        assert section_is_outro({"id": "x", "slides": []}) is False
