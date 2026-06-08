"""影片/解析 render pipeline 的 Gemini 用量計帳（C-1）。

純 offline：Gemini 路徑用 sys.modules 注入 fake google.genai（不裝 SDK、不打真 API），
usage 寫入用 tmp UsageStore 隔離。驗 record_text_now 字元/成本/站別，以及 pipeline
chokepoint（outliner）確實把一筆用量接進成本面板。
"""
from __future__ import annotations

import sys
import types as pytypes
from unittest.mock import MagicMock

import pytest

import core.usage as usage_mod
from core.usage import UsageStore, _text_cost


@pytest.fixture
def store(tmp_path, monkeypatch):
    """把模組級單例換成 tmp store，讓 record_text_now / pipeline 寫入可被檢查。"""
    s = UsageStore(db_path=str(tmp_path / "u.db"))
    monkeypatch.setattr(usage_mod, "_default_store", s)
    return s


def _install_fake_genai(monkeypatch, *, resp_text: str):
    """注入假的 google.genai 到 sys.modules，generate_content 回固定文字。"""
    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            r = MagicMock()
            r.text = resp_text
            return r

    class _FakeClient:
        def __init__(self, api_key=None):
            self.models = _FakeModels()

    fake_genai = pytypes.ModuleType("google.genai")
    fake_types = pytypes.ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = lambda **kw: dict(kw)
    fake_types.ThinkingConfig = lambda **kw: dict(kw)
    fake_genai.Client = _FakeClient
    fake_genai.types = fake_types

    google_pkg = sys.modules.get("google") or pytypes.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setattr(google_pkg, "genai", fake_genai, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)


class TestRecordTextNow:
    def test_records_chars_cost_and_ts(self, store):
        usage_mod.record_text_now("video", "gemini-x", "prompt..", "response!",
                                  label="outline")
        s = store.summary()
        assert s["count"] == 1
        rec = s["recent"][0]
        assert rec["station"] == "影片"
        assert rec["model"] == "gemini-x"
        assert rec["label"] == "outline"
        assert rec["time"]  # ts 自動以當前 UTC 填入（非空）
        # 成本依字元數換算（input=len("prompt.."), output=len("response!")）
        assert abs(rec["amount"] - round(_text_cost(8, 9), 5)) < 1e-6

    def test_material_station_label(self, store):
        usage_mod.record_text_now("material", "gemini-x", "p", "r", label="solve")
        s = store.summary()
        assert s["byStation"][0]["key"] == "material"
        assert s["byStation"][0]["label"] == "解析"

    def test_none_inputs_swallowed(self, store):
        # response 為 None 不應炸（pipeline 計帳不可拖垮主流程）
        usage_mod.record_text_now("video", "m", None, None)  # type: ignore[arg-type]
        assert store.summary()["count"] == 1

    def test_separates_video_and_material(self, store):
        usage_mod.record_text_now("video", "m", "aa", "bb", label="narration")
        usage_mod.record_text_now("material", "m", "aa", "bb", label="identify")
        keys = {b["key"] for b in store.summary()["byStation"]}
        assert keys == {"video", "material"}


class TestOutlinerInstrumented:
    def test_outline_call_records_usage(self, store, monkeypatch):
        """outliner._call_outline_gemini 走完後，成本面板多一筆 video/outline。"""
        from core import outliner

        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        _install_fake_genai(monkeypatch, resp_text='{"deck_title":"測試","sections":[]}')

        out = outliner._call_outline_gemini("做一份大綱")
        assert out["deck_title"] == "測試"

        s = store.summary()
        assert s["count"] == 1
        rec = s["recent"][0]
        assert rec["station"] == "影片" and rec["label"] == "outline"
        # prompt 進得去（input_chars 來自 prompt 長度，非空）→ 計帳確實接上
        assert s["byStation"][0]["key"] == "video"
