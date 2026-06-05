"""chart_suggester + slide_budget 純函式測試 + presentation 整合（Phase C presentation 精修）。

純函式零 API，可離線測。整合段驗 chart_focus 回填與教學 budget 經 generate_presentation_data 生效。
"""
from __future__ import annotations

import core.infocards.chart_suggester as cs
import core.infocards.presentation_service as pres
import core.infocards.slide_budget as sb
from core.infocards.schemas import PresentationData


class TestDetectSeries:
    def test_inline_label_value(self):
        s = cs.detect_data_series("蘋果 10、香蕉 20、橘子 30")
        assert s and s["labels"] == ["蘋果", "香蕉", "橘子"]
        assert s["values"] == [10.0, 20.0, 30.0]
        assert s["source"] == "inline"

    def test_table(self):
        text = "| 年份 | 銷售 |\n| --- | --- |\n| 2020 | 100 |\n| 2021 | 150 |"
        s = cs.detect_data_series(text)
        assert s and s["values"] == [100.0, 150.0]
        assert s["source"] == "table"
        assert s["is_time_series"] is True  # 2020/2021 年份

    def test_percentage(self):
        s = cs.detect_data_series("甲 50%\n乙 30%\n丙 20%")
        assert s and s["is_percentage"] is True

    def test_thousands_separator_protected(self):
        s = cs.detect_data_series("北區: 1,234\n南區: 2,500")
        assert s and s["values"] == [1234.0, 2500.0]

    def test_no_series_returns_none(self):
        assert cs.detect_data_series("這是一段沒有數據的純文字說明") is None
        assert cs.detect_data_series("") is None


class TestSuggestType:
    def test_time_series_to_line(self):
        sug = cs.suggest_chart_type("2020年 100\n2021年 150\n2022年 200")
        assert sug["type"] == "line"

    def test_percentage_to_pie(self):
        sug = cs.suggest_chart_type("A 40%、B 35%、C 25%")
        assert sug["type"] == "pie"

    def test_category_to_bar(self):
        sug = cs.suggest_chart_type("台北 500、台中 300、高雄 400")
        assert sug["type"] == "bar"


class TestChartDataHelpers:
    def test_is_renderable(self):
        assert cs.is_renderable_chart_data({"labels": ["a", "b"], "values": [1, 2]}) is True
        assert cs.is_renderable_chart_data({"labels": ["a"], "values": [1]}) is False
        assert cs.is_renderable_chart_data({"labels": ["a", "b"], "values": [1]}) is False
        assert cs.is_renderable_chart_data(None) is False

    def test_build_only_chart_focus(self):
        assert cs.build_chart_data_for_slide("bullet_list", "甲 10、乙 20") is None
        out = cs.build_chart_data_for_slide("chart_focus", "甲 10、乙 20、丙 30")
        assert out and out["type"] == "bar" and len(out["labels"]) == 3

    def test_build_line_collapses_to_bar(self):
        out = cs.build_chart_data_for_slide("chart_focus", "2020年 1\n2021年 2\n2022年 3")
        assert out and out["type"] == "bar"  # line renderer 不支援 → bar


class TestBudget:
    def test_trims_worked_example_over_6(self):
        sl = {"layout": "worked_example", "bulletPoints": [f"步驟{i}" for i in range(9)]}
        out = sb.enforce_teaching_layout_budget_dict(sl)
        assert len(out["bulletPoints"]) == 6

    def test_trims_exercise_over_4(self):
        sl = {"layout": "exercise", "bulletPoints": ["a", "b", "c", "d", "e", "f"]}
        sb.enforce_teaching_layout_budget_dict(sl)
        assert len(sl["bulletPoints"]) == 4

    def test_non_teaching_untouched(self):
        sl = {"layout": "bullet_list", "bulletPoints": ["a"] * 10}
        sb.enforce_teaching_layout_budget_dict(sl)
        assert len(sl["bulletPoints"]) == 10

    def test_under_limit_untouched(self):
        sl = {"layout": "code_block", "bulletPoints": ["a", "b"]}
        sb.enforce_teaching_layout_budget_dict(sl)
        assert len(sl["bulletPoints"]) == 2


class TestPresentationIntegration:
    def test_chart_focus_backfill_and_budget(self, monkeypatch):
        fake = {
            "mainTitle": "T", "subtitle": "S", "themeColor": "#111", "style": "navy",
            "slides": [
                # chart_focus 無 chartData → 應從文字回填
                {"id": "s1", "layout": "chart_focus", "title": "區域銷售",
                 "content": "台北 500、台中 300、高雄 400", "speakerNotes": "n"},
                # worked_example 超量 bulletPoints → 裁到 6
                {"id": "s2", "layout": "worked_example", "title": "解題", "content": "題目",
                 "speakerNotes": "n", "bulletPoints": [f"步驟{i}" for i in range(10)]},
            ],
        }
        monkeypatch.setattr(pres, "generate_json",
                            lambda prompt, model=None, response_schema=None: fake)
        data = pres.generate_presentation_data("x", "navy")
        assert isinstance(data, PresentationData)
        # chart 回填
        cd = data.slides[0].chartData
        assert cd is not None and len(cd.labels) == 3 and cd.type == "bar"
        # budget 裁切
        assert len(data.slides[1].bulletPoints) == 6

    def test_chart_focus_keeps_valid_ai_data(self, monkeypatch):
        fake = {
            "mainTitle": "T", "subtitle": "S", "themeColor": "#111", "style": "navy",
            "slides": [
                {"id": "s1", "layout": "chart_focus", "title": "已有數據", "content": "無關文字",
                 "speakerNotes": "n",
                 "chartData": {"labels": ["X", "Y"], "values": [9.0, 8.0], "type": "pie"}},
            ],
        }
        monkeypatch.setattr(pres, "generate_json",
                            lambda prompt, model=None, response_schema=None: fake)
        data = pres.generate_presentation_data("x", "navy")
        cd = data.slides[0].chartData
        assert cd.labels == ["X", "Y"] and cd.type == "pie"  # 不覆蓋 AI 有效數據
