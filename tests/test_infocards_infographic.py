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


class TestRefineSection:
    """逐區 refine（區域選擇 → 重生單一 section，U-2）。全程 mock Gemini，不打真 API。"""

    def _data(self):
        return InfographicData.model_validate({**_FAKE, "style": "academic"})

    def test_prompt_builder_includes_instruction_and_section(self):
        p = info.build_refine_section_prompt(
            {"id": "s1", "title": "第一定律", "content": "慣性", "iconType": "bulb"},
            "講得更白話", main_title="牛頓定律")
        assert "講得更白話" in p and "第一定律" in p
        assert "牛頓定律" in p and "視覺風格：professional" in p

    def test_prompt_builder_custom_style(self):
        p = info.build_refine_section_prompt(
            {"id": "s1", "title": "t", "content": "c", "iconType": "info"},
            "x", style="custom", custom="水彩風")
        assert "絕對優先風格指令" in p and "水彩風" in p

    def test_merges_and_keeps_id(self, monkeypatch):
        # AI 只回 title/content，iconType/imagePrompt 應由原 section 補回。
        monkeypatch.setattr(info, "generate_json",
                            lambda prompt, model=None, response_schema=None: {
                                "id": "evil", "title": "新標題", "content": "新內容"})
        monkeypatch.setattr(info, "generate_image_b64",
                            lambda prompt, model=None: "data:image/png;base64,IMG")
        out = info.refine_infographic_section(self._data(), "s1", "改標題")
        sec = next(s for s in out.sections if s.id == "s1")
        assert sec.title == "新標題" and sec.content == "新內容"
        assert sec.id == "s1"  # AI 想改 id 被擋
        assert sec.iconType == "bulb"  # 原欄位保留
        # 其他 section 不受影響
        assert next(s for s in out.sections if s.id == "s2").title == "第二定律"

    def test_unknown_section_raises(self, monkeypatch):
        import pytest
        monkeypatch.setattr(info, "generate_json",
                            lambda prompt, model=None, response_schema=None: {})
        with pytest.raises(ValueError):
            info.refine_infographic_section(self._data(), "nope", "x")

    def test_coerce_bad_icontype(self, monkeypatch):
        monkeypatch.setattr(info, "generate_json",
                            lambda prompt, model=None, response_schema=None: {
                                "title": "t", "iconType": "rocket"})
        monkeypatch.setattr(info, "generate_image_b64",
                            lambda prompt, model=None: "data:image/png;base64,IMG")
        out = info.refine_infographic_section(self._data(), "s1", "x")
        assert next(s for s in out.sections if s.id == "s1").iconType == "info"

    def test_regenerates_image_when_prompt_changes(self, monkeypatch):
        monkeypatch.setattr(info, "generate_json",
                            lambda prompt, model=None, response_schema=None: {
                                "imagePrompt": "a falling apple"})
        monkeypatch.setattr(info, "generate_image_b64",
                            lambda prompt, model=None: f"data:image/png;base64,IMG({prompt})")
        out = info.refine_infographic_section(self._data(), "s1", "換圖")
        sec = next(s for s in out.sections if s.id == "s1")
        assert sec.imageUrl == "data:image/png;base64,IMG(a falling apple)"

    def test_skip_image_when_flag_false(self, monkeypatch):
        calls = []
        monkeypatch.setattr(info, "generate_json",
                            lambda prompt, model=None, response_schema=None: {
                                "imagePrompt": "new pic"})
        monkeypatch.setattr(info, "generate_image_b64",
                            lambda prompt, model=None: calls.append(prompt) or "X")
        out = info.refine_infographic_section(self._data(), "s1", "x", regenerate_image=False)
        assert calls == []  # 不生圖
        assert next(s for s in out.sections if s.id == "s1").imagePrompt == "new pic"

    def test_clearing_prompt_drops_image(self, monkeypatch):
        # 先給 s1 一張圖，refine 把 imagePrompt 清空 → imageUrl 應一併去除。
        data = self._data()
        next(s for s in data.sections if s.id == "s1").imageUrl = "data:image/png;base64,OLD"
        monkeypatch.setattr(info, "generate_json",
                            lambda prompt, model=None, response_schema=None: {"imagePrompt": ""})
        out = info.refine_infographic_section(data, "s1", "移除圖片")
        assert next(s for s in out.sections if s.id == "s1").imageUrl is None

    # 註：`POST /api/refine-section` 路由的端到端測試已由
    # tests/test_infocards_refine.py::TestRefineSectionRoute 涵蓋（現行契約＝收/回
    # 單一 section）。本檔原有的兩個路由測試送的是舊形狀 {infographic, sectionId}、
    # 讀 data.data，與 #81 落地的單一 section 契約不符（回 422），已移除以對齊現行
    # 路由；本類別其餘仍為 infographic_service.refine_infographic_section 的函式單元測試。
