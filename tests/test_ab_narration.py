"""tools/ab_narration 的離線測試（C-3 旁白 A/B 比對工具）。

全程用 fake narrate_fn / fake client，**不打真 Gemini、不渲染真 PDF**。驗收：
- 頁碼解析（逗號 / 範圍 / 去重排序 / 夾邊界）。
- run_ab 對每頁 × 每模型各呼叫一次、把 model 正確透傳。
- 報告並排呈現兩模型輸出 + 字元用量小結。
- _build_client 缺 key 直接 SystemExit（不靜默）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tools/ 不是 package；比照 test_check_models.py 掛 tools 目錄上 path 當 top-level module。
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.append(str(_TOOLS_DIR))

import ab_narration as ab  # noqa: E402


class TestParsePages:
    def test_comma(self):
        assert ab.parse_pages("1,3,5", 10) == [1, 3, 5]

    def test_range(self):
        assert ab.parse_pages("2-4", 10) == [2, 3, 4]

    def test_mixed_dedup_sorted(self):
        assert ab.parse_pages("5,1-3,3", 10) == [1, 2, 3, 5]

    def test_clamps_to_total(self):
        assert ab.parse_pages("1,8,99", 5) == [1]

    def test_blank_chunks_ignored(self):
        assert ab.parse_pages("1,,2,", 5) == [1, 2]


class TestRunAb:
    def test_each_page_each_model_called_with_model(self):
        calls = []

        def fake_narrate(client, png, title, ch_pages, p_in_ch, prev,
                         *, brief=False, model=None):
            calls.append((png, model, brief))
            return f"[{model}] 旁白 for {png.decode()}"

        pages = {1: b"p1", 2: b"p2"}
        models = ["gemini-2.5-flash", "gemini-3.5-flash"]
        results = ab.run_ab(object(), fake_narrate, pages, models)

        # 2 頁 × 2 模型 = 4 次呼叫，model 各自正確透傳
        assert len(calls) == 4
        assert {c[1] for c in calls} == set(models)
        assert results[0]["page"] == 1 and results[1]["page"] == 2
        cell = results[0]["models"]["gemini-3.5-flash"]
        assert cell["text"] == "[gemini-3.5-flash] 旁白 for p1"
        assert cell["chars"] == len(cell["text"])

    def test_pages_sorted(self):
        def fake_narrate(c, png, *a, model=None, **k):
            return "x"

        results = ab.run_ab(object(), fake_narrate, {3: b"c", 1: b"a"},
                            ["m1", "m2"])
        assert [r["page"] for r in results] == [1, 3]

    def test_brief_flag_forwarded(self):
        seen = {}

        def fake_narrate(c, png, *a, brief=False, model=None, **k):
            seen["brief"] = brief
            return "y"

        ab.run_ab(object(), fake_narrate, {1: b"a"}, ["m1"], brief=True)
        assert seen["brief"] is True


class TestReport:
    def test_report_has_both_models_and_usage(self):
        results = [
            {"page": 1, "models": {
                "m-old": {"text": "舊版旁白", "chars": 4},
                "m-new": {"text": "新版旁白較長一點", "chars": 8},
            }},
        ]
        out = ab.render_report(results, ["m-old", "m-new"], "deck.pdf")
        assert "deck.pdf" in out
        assert "第 1 頁" in out
        assert "舊版旁白" in out and "新版旁白較長一點" in out
        assert "`m-old`" in out and "`m-new`" in out
        # 用量小結含兩模型字元總數
        assert "字元用量小結" in out
        assert "輸出共 4 字" in out and "輸出共 8 字" in out


class TestBuildClient:
    def test_missing_key_exits(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(SystemExit):
            ab._build_client()


class TestNarrateOnePage:
    def test_passes_model_and_context(self):
        captured = {}

        def fake_narrate(client, png, title, ch_pages, p_in_ch, prev,
                         *, brief=False, model=None):
            captured.update(model=model, page_in_chapter=p_in_ch, png=png)
            return "ok"

        out = ab.narrate_one_page(object(), fake_narrate, b"png", "gemini-3.5-flash",
                                  page_in_chapter=7)
        assert out == "ok"
        assert captured["model"] == "gemini-3.5-flash"
        assert captured["page_in_chapter"] == 7
