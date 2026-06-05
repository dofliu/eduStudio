"""core/infocards presentation_service + presentation_themes 測試（Phase C presentation）。

mock Gemini，不打真 API。覆蓋：theme 解析、後端補欄位（typography/density/promptUsed/
presentationTheme）、themeColor fallback、版型/chart Literal coerce、imagePrompt 政策過濾、
逐頁生圖只對允許版型。
"""
from __future__ import annotations

import core.infocards.presentation_service as pres
from core.infocards.presentation_themes import get_theme_by_style
from core.infocards.schemas import PresentationData

_FAKE = {
    "mainTitle": "控制系統導論",
    "subtitle": "從傳遞函數到穩定性",
    "themeColor": "#123456",
    "style": "navy",
    "slides": [
        {"id": "s1", "layout": "title_cover", "title": "控制系統導論", "content": "",
         "speakerNotes": "開場", "imagePrompt": "an engineering control room"},
        {"id": "s2", "layout": "bullet_list", "title": "大綱", "content": "重點",
         "speakerNotes": "提示", "bulletPoints": ["• 傳遞函數", "• 穩定性"]},
        {"id": "s3", "layout": "chart_focus", "title": "極點分布", "content": "",
         "speakerNotes": "看圖", "chartData": {"labels": ["P1", "P2"], "values": [1.0, 2.0], "type": "bar"}},
    ],
}


class TestThemes:
    def test_known_style(self):
        assert get_theme_by_style("navy")["id"] == "navy"
        assert get_theme_by_style("forest")["accent"] == "#166534"

    def test_unknown_falls_back_professional(self):
        assert get_theme_by_style("nonexistent")["id"] == "professional"
        assert get_theme_by_style("custom")["id"] == "professional"


class TestNeedsAIImage:
    def test_required_optional_layouts(self):
        for lay in ("title_cover", "text_and_image", "diagram_image", "full_image"):
            assert pres.needs_ai_image(lay) is True

    def test_native_layouts_no_image(self):
        for lay in ("bullet_list", "big_number", "chart_focus", "two_column", "code_block"):
            assert pres.needs_ai_image(lay) is False


class TestGeneratePresentationData:
    def test_sets_backend_fields(self, monkeypatch):
        monkeypatch.setattr(pres, "generate_json",
                            lambda prompt, model=None, response_schema=None: dict(_FAKE))
        data = pres.generate_presentation_data("控制系統", "navy", slide_count=3,
                                               density="detailed", typography="mono")
        assert isinstance(data, PresentationData)
        assert data.style == "navy"
        assert data.typography == "mono" and data.density == "detailed"
        assert data.presentationTheme == "navy"
        assert data.promptUsed and "控制系統" in data.promptUsed
        assert len(data.slides) == 3

    def test_themecolor_fallback_when_black(self, monkeypatch):
        bad = dict(_FAKE)
        bad["themeColor"] = "#000000"
        monkeypatch.setattr(pres, "generate_json",
                            lambda prompt, model=None, response_schema=None: bad)
        data = pres.generate_presentation_data("x", "forest")
        assert data.themeColor == get_theme_by_style("forest")["accent"]

    def test_coerce_bad_layout_and_chart_type(self, monkeypatch):
        bad = {
            "mainTitle": "T", "subtitle": "S", "themeColor": "#111", "style": "navy",
            "slides": [
                {"id": "s1", "layout": "wild", "title": "t", "content": "c", "speakerNotes": "n"},
                {"id": "s2", "layout": "chart_focus", "title": "t", "content": "c", "speakerNotes": "n",
                 "chartData": {"labels": ["a"], "values": [1.0], "type": "doughnut"}},
            ],
        }
        monkeypatch.setattr(pres, "generate_json",
                            lambda prompt, model=None, response_schema=None: bad)
        data = pres.generate_presentation_data("x", "navy")
        assert data.slides[0].layout == "bullet_list"
        assert data.slides[1].chartData.type == "bar"

    def test_image_policy_drops_imageprompt_on_native(self, monkeypatch):
        bad = {
            "mainTitle": "T", "subtitle": "S", "themeColor": "#111", "style": "navy",
            "slides": [
                {"id": "s1", "layout": "bullet_list", "title": "t", "content": "c",
                 "speakerNotes": "n", "imagePrompt": "AI 雞婆填的圖"},
            ],
        }
        monkeypatch.setattr(pres, "generate_json",
                            lambda prompt, model=None, response_schema=None: bad)
        data = pres.generate_presentation_data("x", "navy")
        assert data.slides[0].imagePrompt is None  # native 版型 imagePrompt 被丟棄

    def test_custom_style_uses_professional_theme(self, monkeypatch):
        seen = {}

        def fake(prompt, model=None, response_schema=None):
            seen["prompt"] = prompt
            return dict(_FAKE)

        monkeypatch.setattr(pres, "generate_json", fake)
        data = pres.generate_presentation_data("x", "custom", custom="霓虹賽博風")
        assert "THEME: 霓虹賽博風" in seen["prompt"]
        assert data.presentationTheme == "professional"


class TestGeneratePresentationImages:
    def test_only_allowed_layouts_get_images(self, monkeypatch):
        monkeypatch.setattr(pres, "generate_image_b64",
                            lambda prompt, model=None: f"data:image/png;base64,IMG({prompt})")
        data = PresentationData.model_validate(_FAKE)
        out = pres.generate_presentation_images(data, style="navy")
        # s1 title_cover 有 imagePrompt → 生圖；s2/s3 native → 不生
        assert out.slides[0].imageUrl == "data:image/png;base64,IMG(an engineering control room)"
        assert out.slides[1].imageUrl is None
        assert out.slides[2].imageUrl is None
