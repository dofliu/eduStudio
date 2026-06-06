"""兩階段大綱：layout_rules + outline_normalizer + generate_presentation_outlines 測試。

純函式零 API；生成段 mock Gemini。對齊 layoutSelector.ts / outlineNormalizer.ts /
presentationService.ts:generatePresentationOutlines 行為。
"""
from __future__ import annotations

import core.infocards.layout_rules as lr
import core.infocards.outline_normalizer as nz
import core.infocards.presentation_service as pres
from core.infocards.schemas import PresentationData, PresentationOutline


class TestLayoutRules:
    def test_structural_positions(self):
        assert lr.pick_layout(slide_index=1, total_slides=10, title="封面") == "title_cover"
        assert lr.pick_layout(slide_index=10, total_slides=10, title="總結") == "conclusion"

    def test_keyword_picks_process_steps(self):
        out = lr.pick_layout(slide_index=3, total_slides=10, title="安裝步驟", content="依序操作")
        assert out == "process_steps"

    def test_code_signal_picks_code_block(self):
        out = lr.pick_layout(slide_index=4, total_slides=10, title="範例", content="def f():", is_code=True)
        assert out == "code_block"

    def test_reconcile_respects_ai_hint_when_rule_weak(self):
        # 無明確規則訊號 → 尊重 AI 的 quote
        out = lr.reconcile_layout(slide_index=3, total_slides=10, title="心得", content="一段話", ai_hint="quote")
        assert out == "quote"

    def test_reconcile_overrides_when_rule_strong(self):
        # 內容強烈指向 process_steps（命中關鍵字 ≥10），覆蓋 AI 的 bullet_list
        out = lr.reconcile_layout(slide_index=3, total_slides=10, title="流程",
                                  content="步驟 依序 操作", ai_hint="bullet_list")
        assert out == "process_steps"

    def test_analyze_outline_signals(self):
        sig = lr.analyze_outline_slide("成長率", "2020 至 2023 成長 35%")
        assert sig["has_numbers"] is True
        sig2 = lr.analyze_outline_slide("程式", "```python code```")
        assert sig2["is_code"] is True

    def test_is_valid_layout(self):
        assert lr.is_valid_layout("bullet_list") is True
        assert lr.is_valid_layout("nope") is False


class TestOutlineNormalizer:
    def test_normalize_theme(self):
        assert nz.normalize_theme("navy") == "navy"
        assert nz.normalize_theme("bogus") == "professional"

    def test_normalize_typography(self):
        assert nz.normalize_typography("mono") == "mono"
        assert nz.normalize_typography("fancy") == "modern"

    def test_normalize_estimated_image_count_clamps(self):
        assert nz.normalize_estimated_image_count(99, 10) == 10
        assert nz.normalize_estimated_image_count(-3, 10) == 0
        assert nz.normalize_estimated_image_count(3.7, 10) == 3

    def test_apply_selected_theme_unifies(self):
        outs = [{"suggestedTheme": "a"}, {"suggestedTheme": "b"}]
        nz.apply_selected_theme(outs, "forest")
        assert all(o["suggestedTheme"] == "forest" for o in outs)

    def test_custom_style_preserved(self):
        outs = [{"suggestedTheme": "a"}]
        nz.apply_selected_theme(outs, "custom")
        assert outs[0]["suggestedTheme"] == "custom"


_FAKE_OUTLINES = {
    "outlines": [
        {
            "label": "方案 A：敘事型", "approach": "故事線", "recommendedAudience": "大學生",
            "suggestedTheme": "vibrant", "suggestedTypography": "fancy",  # 無效字型 → 校正 modern
            "mainTitle": "控制系統", "subtitle": "導論", "estimatedImageCount": 99,  # 超量 → 夾到頁數
            "slides": [
                {"layout": "title_cover", "title": "封面頁", "summary": "標題"},       # AI 已對 → 保留
                {"layout": "bullet_list", "title": "安裝步驟", "summary": "依序 操作 步驟"},  # 強訊號 → process_steps
                {"layout": "conclusion", "title": "結語", "summary": "總結"},          # AI 已對 → 保留
            ],
        },
        {
            "label": "方案 B：分析型", "approach": "數據", "suggestedTheme": "digital",
            "suggestedTypography": "mono", "mainTitle": "控制系統", "subtitle": "分析",
            "estimatedImageCount": 2,
            "slides": [
                {"layout": "title_cover", "title": "封面", "summary": "x"},
                {"layout": "chart_focus", "title": "數據", "summary": "成長率 35%"},
            ],
        },
    ]
}


class TestGenerateOutlines:
    def test_outlines_reconciled_and_normalized(self, monkeypatch):
        monkeypatch.setattr(pres, "generate_json",
                            lambda prompt, model=None, response_schema=None, files=None: {
                                "outlines": [dict(o, slides=[dict(s) for s in o["slides"]])
                                             for o in _FAKE_OUTLINES["outlines"]]})
        outs = pres.generate_presentation_outlines("控制系統", "navy", slide_count=3)
        assert len(outs) == 2
        assert all(isinstance(o, PresentationOutline) for o in outs)
        a = outs[0]
        # 主題統一為使用者選定 navy
        assert a.suggestedTheme == "navy"
        # 無效字型校正
        assert a.suggestedTypography == "modern"
        # estimatedImageCount 夾到頁數
        assert a.estimatedImageCount == 3
        # 版型校正：首頁 title_cover、含「步驟」→ process_steps、末頁 conclusion
        assert a.slides[0].layout == "title_cover"
        assert a.slides[1].layout == "process_steps"
        assert a.slides[2].layout == "conclusion"


class TestSelectedOutlineGeneration:
    def test_selected_outline_uses_its_theme_typography(self, monkeypatch):
        captured = {}

        def fake_json(prompt, model=None, response_schema=None, files=None):
            captured["prompt"] = prompt
            return {"mainTitle": "T", "subtitle": "S", "themeColor": "#111", "style": "forest",
                    "slides": [{"id": "s1", "layout": "title_cover", "title": "封面",
                                "content": "", "speakerNotes": "n"}]}

        monkeypatch.setattr(pres, "generate_json", fake_json)
        outline = {"label": "方案 A", "approach": "故事", "mainTitle": "T", "subtitle": "S",
                   "suggestedTheme": "forest", "suggestedTypography": "classic",
                   "slides": [{"layout": "title_cover", "title": "封面", "summary": "x"}]}
        data = pres.generate_presentation_data("內容", "navy", selected_outline=outline)
        assert isinstance(data, PresentationData)
        assert data.presentationTheme == "forest"   # 沿用大綱主題而非傳入的 navy
        assert data.typography == "classic"          # 沿用大綱字型
        assert "必須嚴格遵守此架構" in captured["prompt"]  # 大綱指令注入
