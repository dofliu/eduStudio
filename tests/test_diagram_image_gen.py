"""core/diagram_image_gen.py — iter 56 AI 生圖 helpers.

純函式 + mock Gemini call. 不打真 API.
"""
from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.diagram_image_gen import (
    _build_diagram_prompt,
    _extract_image_bytes,
    generate_diagrams_for_outline,
    generate_section_diagram_image,
)


def _has_google_genai() -> bool:
    """iter 87: 跳過需要 google.genai 的測試, 給 CI 沒裝該 SDK 用."""
    try:
        import google.genai  # noqa: F401
        return True
    except ImportError:
        return False


class TestBuildDiagramPrompt:
    def test_includes_title(self):
        out = _build_diagram_prompt({"title": "Receptive Field"})
        assert "Receptive Field" in out

    def test_includes_intent_when_present(self):
        out = _build_diagram_prompt({"title": "T", "intent": "explain RF"})
        assert "explain RF" in out

    def test_skips_intent_when_empty(self):
        out = _build_diagram_prompt({"title": "T", "intent": ""})
        assert "Concept focus:" not in out

    def test_topics_joined(self):
        out = _build_diagram_prompt({
            "title": "T", "topics": ["topic1", "topic2", ""],
        })
        # 空字串該被略過
        assert "topic1, topic2" in out
        assert "topic1, topic2, " not in out

    def test_includes_deck_title(self):
        out = _build_diagram_prompt({"title": "T"}, deck_title="My Deck")
        assert "My Deck" in out

    def test_style_requirements_in_prompt(self):
        out = _build_diagram_prompt({"title": "T"})
        # 確認核心 style hint 都帶
        assert "educational" in out.lower()
        assert "minimalist" in out.lower() or "minimal" in out.lower()
        assert "English" in out


class TestExtractImageBytes:
    def test_returns_raw_bytes(self):
        """SDK 偶爾直接給 bytes."""
        png_bytes = b"\x89PNG\r\n\x1a\n test"
        # 模擬 response 結構: candidates → content → parts → inline_data → data
        resp = MagicMock()
        part = MagicMock()
        part.inline_data.data = png_bytes
        resp.candidates = [MagicMock(content=MagicMock(parts=[part]))]
        assert _extract_image_bytes(resp) == png_bytes

    def test_returns_decoded_base64(self):
        """SDK 偶爾給 base64 str."""
        png_bytes = b"\x89PNG fake"
        encoded = base64.b64encode(png_bytes).decode()
        resp = MagicMock()
        part = MagicMock()
        part.inline_data.data = encoded
        resp.candidates = [MagicMock(content=MagicMock(parts=[part]))]
        assert _extract_image_bytes(resp) == png_bytes

    def test_empty_candidates_returns_none(self):
        resp = MagicMock()
        resp.candidates = []
        assert _extract_image_bytes(resp) is None

    def test_no_inline_data_returns_none(self):
        """parts 內全都是 text part, 沒 inline_data."""
        resp = MagicMock()
        part = MagicMock()
        part.inline_data = None
        resp.candidates = [MagicMock(content=MagicMock(parts=[part]))]
        assert _extract_image_bytes(resp) is None


class TestGenerateSectionDiagramImage:
    @pytest.mark.skipif(
        not _has_google_genai(),
        reason="google-genai SDK 未裝 (CI 沒裝該套件)",
    )
    def test_missing_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        ok, err = generate_section_diagram_image(
            {"title": "T"}, tmp_path / "x.png", api_key=None,
        )
        assert not ok
        assert "GEMINI_API_KEY" in err

    @pytest.mark.skipif(
        not _has_google_genai(),
        reason="google-genai SDK 未裝",
    )
    def test_api_failure_returns_false(self, tmp_path, monkeypatch):
        """Gemini API 拋例外 → 回 (False, error msg) 不該 raise."""
        import core.diagram_image_gen as mod

        class FakeClient:
            class models:
                @staticmethod
                def generate_content(**kw):
                    raise RuntimeError("rate limit")

        def fake_genai_client(api_key):
            return FakeClient()

        # monkey-patch genai.Client
        fake_genai = MagicMock()
        fake_genai.Client = fake_genai_client
        fake_types = MagicMock()
        monkeypatch.setattr("google.genai", fake_genai)
        monkeypatch.setattr("google.genai.types", fake_types)
        monkeypatch.setenv("GEMINI_API_KEY", "fake")

        ok, err = generate_section_diagram_image(
            {"title": "T"}, tmp_path / "x.png",
        )
        assert not ok
        assert "rate limit" in err


class TestGenerateDiagramsForOutline:
    def test_skips_section_with_empty_id(self, tmp_path, monkeypatch):
        """sec_id 全是非法字元時 safe_id 變空, 該 section 跳過."""
        outline = {"sections": [{"id": "@@@@", "title": "T"}]}
        # mock 真的 generate 不該被呼叫到
        monkeypatch.setattr(
            "core.diagram_image_gen.generate_section_diagram_image",
            lambda *a, **kw: (True, ""),
        )
        out = generate_diagrams_for_outline(outline, tmp_path)
        assert out == []

    def test_max_per_outline_respected(self, tmp_path, monkeypatch):
        outline = {"sections": [
            {"id": "s1"}, {"id": "s2"}, {"id": "s3"},
            {"id": "s4"}, {"id": "s5"},
        ]}
        monkeypatch.setattr(
            "core.diagram_image_gen.generate_section_diagram_image",
            lambda section, out_path, **kw: (True, ""),
        )
        out = generate_diagrams_for_outline(outline, tmp_path, max_per_outline=2)
        assert len(out) == 2
        assert [f["id"] for f in out] == ["ai_s1", "ai_s2"]

    def test_failed_sections_skipped(self, tmp_path, monkeypatch):
        """生圖失敗 (Gemini quota / safety) 的 section 不該進 figure list."""
        outline = {"sections": [
            {"id": "good", "title": "good"},
            {"id": "bad", "title": "bad"},
        ]}

        def fake_gen(section, out_path, **kw):
            if section["id"] == "bad":
                return (False, "fake quota error")
            return (True, "")

        monkeypatch.setattr(
            "core.diagram_image_gen.generate_section_diagram_image", fake_gen,
        )
        out = generate_diagrams_for_outline(outline, tmp_path)
        assert len(out) == 1
        assert out[0]["id"] == "ai_good"

    def test_figure_schema_matches_pdf_format(self, tmp_path, monkeypatch):
        """回的 dict 該跟 extract_pdf_figures 同 schema 讓 scriptor reuse."""
        outline = {"sections": [{"id": "intro", "title": "Intro to RF"}]}
        monkeypatch.setattr(
            "core.diagram_image_gen.generate_section_diagram_image",
            lambda section, out_path, **kw: (True, ""),
        )
        out = generate_diagrams_for_outline(outline, tmp_path)
        f = out[0]
        # 跟 PDF figures 一致的 keys
        assert set(f.keys()) >= {
            "id", "page_no", "path", "width", "height", "caption_hint",
        }
        assert f["id"] == "ai_intro"
        assert f["path"] == "ai_intro.png"
        assert f["caption_hint"] == "Intro to RF"
        assert f["page_no"] == 0   # AI 圖 no page concept

    def test_section_id_with_special_chars_sanitized(self, tmp_path, monkeypatch):
        """sec_id 含非 alnum 字元應被清掉, 不該變成 path traversal vector."""
        outline = {"sections": [{"id": "../bad/id", "title": "x"}]}
        monkeypatch.setattr(
            "core.diagram_image_gen.generate_section_diagram_image",
            lambda section, out_path, **kw: (True, ""),
        )
        out = generate_diagrams_for_outline(outline, tmp_path)
        # safe_id 過濾後 = "badid", 不含 / .. 等
        assert len(out) == 1
        assert "/" not in out[0]["id"]
        assert ".." not in out[0]["id"]
        assert out[0]["id"] == "ai_badid"
