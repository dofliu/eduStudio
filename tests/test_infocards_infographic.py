"""core/infocards infographic_service 測試（Phase C-2 延伸：圖卡 card 模式）。

mock Gemini，不打真 API。重點覆蓋：style/aspectRatio/promptUsed 後端補、逐 section 生圖、
以及 Literal 越界值（iconType/layout/chart.type）的 _coerce 防禦（避免單欄毀掉整張圖卡）。
"""
from __future__ import annotations

import core.infocards.infographic_service as info
from core.infocards.schemas import InfographicData

_FAKE = {
    "mainTitle": "牛頓三大運動定律",
    "subtitle": "古典力學的基石",
    "layout": "grid",
    "sections": [
        {"id": "s1", "title": "第一定律", "content": "慣性", "iconType": "bulb",
         "imagePrompt": "an apple at rest"},
        {"id": "s2", "title": "第二定律", "content": "F=ma", "iconType": "chart",
         "imagePrompt": "force vectors"},
    ],
    "statistics": [{"id": "st1", "value": "3", "label": "定律數"}],
    "charts": [{"id": "c1", "title": "力與加速度", "type": "bar",
                "data": [{"label": "F1", "value": 10.0}, {"label": "F2", "value": 20.0}]}],
    "conclusion": "三大定律奠定古典力學",
    "themeColor": "#2563eb",
}


class TestInfographicService:
    def test_generate_data_sets_style_aspect_prompt(self, monkeypatch):
        monkeypatch.setattr(info, "generate_json",
                            lambda prompt, model=None, response_schema=None, files=None: dict(_FAKE))
        data = info.generate_infographic_data("牛頓定律", "academic", aspect_ratio="square")
        assert isinstance(data, InfographicData)
        assert data.style == "academic"
        assert data.aspectRatio == "square"
        assert data.mainTitle == "牛頓三大運動定律"
        assert len(data.sections) == 2 and len(data.charts) == 1
        assert data.promptUsed and "牛頓定律" in data.promptUsed

    def test_custom_style_in_prompt(self, monkeypatch):
        seen = {}

        def fake_json(prompt, model=None, response_schema=None, files=None):
            seen["prompt"] = prompt
            return dict(_FAKE)

        monkeypatch.setattr(info, "generate_json", fake_json)
        info.generate_infographic_data("t", "custom", custom="水彩風 watercolor")
        assert "水彩風 watercolor" in seen["prompt"]
        assert "絕對優先風格指令" in seen["prompt"]

    def test_coerce_out_of_range_literals(self, monkeypatch):
        """Gemini 回越界 iconType/layout/chart.type → 退安全預設，不炸 validate。"""
        bad = dict(_FAKE)
        bad["layout"] = "wild_layout"
        bad["sections"] = [{"id": "s1", "title": "t", "content": "c", "iconType": "rocket"}]
        bad["charts"] = [{"id": "c1", "title": "x", "type": "doughnut",
                          "data": [{"label": "a", "value": 1.0}]}]
        monkeypatch.setattr(info, "generate_json",
                            lambda prompt, model=None, response_schema=None, files=None: bad)
        data = info.generate_infographic_data("x", "professional")
        assert data.layout == "grid"
        assert data.sections[0].iconType == "info"
        assert data.charts[0].type == "bar"

    def test_generate_images_fills_section_urls(self, monkeypatch):
        monkeypatch.setattr(info, "generate_image_b64",
                            lambda prompt, model=None: f"data:image/png;base64,IMG({prompt})")
        data = InfographicData.model_validate({**_FAKE, "style": "academic"})
        out = info.generate_infographic_images(data)
        assert out.sections[0].imageUrl == "data:image/png;base64,IMG(an apple at rest)"
        assert out.sections[1].imageUrl.startswith("data:image/png;base64,")

    def test_generate_images_skips_sections_without_prompt(self, monkeypatch):
        monkeypatch.setattr(info, "generate_image_b64",
                            lambda prompt, model=None: "data:image/png;base64,X")
        payload = {**_FAKE, "style": "academic",
                   "sections": [{"id": "s1", "title": "t", "content": "c", "iconType": "info"}]}
        data = InfographicData.model_validate(payload)
        out = info.generate_infographic_images(data)
        assert out.sections[0].imageUrl is None  # 無 imagePrompt → 不生圖
