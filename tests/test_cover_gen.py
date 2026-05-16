"""core/cover_gen.py — iter 62 封面 section 生成.

純函式, 沒 LLM call. 直跑.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from core.cover_gen import build_cover_section, section_is_cover


class TestBuildCoverSection:
    def test_returns_valid_section_dict(self):
        sec = build_cover_section("My Topic", speaker="劉老師", org="DofLab")
        # 該有 section schema 該有的欄位
        assert sec["id"] == "_cover"
        assert "slides" in sec
        assert len(sec["slides"]) == 1

    def test_slide_has_cover_bg_type(self):
        sec = build_cover_section("T")
        slide = sec["slides"][0]
        assert slide["bg_type"] == "cover"

    def test_meta_fields_in_slide(self):
        sec = build_cover_section(
            "Title", speaker="John", org="Lab", date_str="2026-01-01",
        )
        slide = sec["slides"][0]
        assert slide["cover_speaker"] == "John"
        assert slide["cover_org"] == "Lab"
        assert slide["cover_date"] == "2026-01-01"

    def test_default_date_is_today(self):
        sec = build_cover_section("T")
        slide = sec["slides"][0]
        today = datetime.now().strftime("%Y-%m-%d")
        assert slide["cover_date"] == today

    def test_narration_includes_speaker_and_title(self):
        sec = build_cover_section(
            "我的主題", speaker="劉老師", org="DofLab",
        )
        narration = sec["slides"][0]["narration"]
        assert "劉老師" in narration
        assert "我的主題" in narration
        assert "DofLab" in narration

    def test_empty_speaker_uses_fallback(self):
        """speaker 給空字串時, narration 該用「劉老師」fallback."""
        sec = build_cover_section("T", speaker="", org="Lab")
        narration = sec["slides"][0]["narration"]
        assert "劉老師" in narration   # fallback default

    def test_no_bullets(self):
        """封面 slide 該沒 bullets — meta 走專屬欄位顯示."""
        sec = build_cover_section("T")
        assert sec["slides"][0]["bullets"] == []

    def test_title_used_as_section_title(self):
        sec = build_cover_section("My Topic")
        assert sec["title"] == "My Topic"
        # 但封面 slide 的 section_title 該是空 (不畫 banner)
        assert sec["slides"][0]["section_title"] == ""

    def test_image_path_none(self):
        """封面不該有圖, 走文字 layout."""
        sec = build_cover_section("T")
        assert sec["slides"][0]["image_path"] is None


class TestSectionIsCover:
    def test_cover_section_by_id(self):
        sec = build_cover_section("T")
        assert section_is_cover(sec) is True

    def test_cover_section_by_bg_type(self):
        """id 不是 _cover, 但 slide bg_type=cover 也算."""
        sec = {
            "id": "custom_id",
            "slides": [{"bg_type": "cover"}],
        }
        assert section_is_cover(sec) is True

    def test_normal_section_not_cover(self):
        sec = {"id": "intro", "slides": [{"bg_type": "pptx_slide"}]}
        assert section_is_cover(sec) is False

    def test_empty_section(self):
        assert section_is_cover({}) is False
        assert section_is_cover({"id": "x", "slides": []}) is False
