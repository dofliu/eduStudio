"""server/mcp_tools.py 測試（eduStudio 合併 B-2 收尾）。

mock 底層服務 + history/learning，驗 tool 可呼叫、語言碼 canonical→底線邊界轉換、
history 記錄。不打真 Gemini / db。
"""
from __future__ import annotations

import pytest

pytest.importorskip("mcp", reason="需要 mcp 套件")

import server.mcp_tools as mt


class _FakeHistory:
    def __init__(self):
        self.calls = []

    def add_history(self, **kw):
        self.calls.append(kw)


def test_list_languages_canonical_hyphen():
    rows = mt.list_languages()
    codes = [r["code"] for r in rows]
    assert "zh-TW" in codes
    assert all("_" not in c for c in codes)  # canonical 連字號
    assert all({"code", "name_zh", "name_en"} <= set(r) for r in rows)


def test_translate_text_boundary_and_history(monkeypatch):
    seen = {}
    monkeypatch.setattr(mt.translator, "translate",
                        lambda text, s, t: seen.update(s=s, t=t) or "譯文")
    fake_hist = _FakeHistory()
    monkeypatch.setattr(mt, "get_history_manager", lambda: fake_hist)

    out = mt.translate_text("hello", source_lang="en-US", target_lang="zh-TW")
    assert out == "譯文"
    # 邊界轉底線後才進服務
    assert seen["s"] == "en_US" and seen["t"] == "zh_TW"
    # history 記一筆（記 canonical 連字號）
    assert len(fake_hist.calls) == 1
    assert fake_hist.calls[0]["type"] == "text"
    assert fake_hist.calls[0]["target_lang"] == "zh-TW"


def test_batch_translate(monkeypatch):
    monkeypatch.setattr(mt.translator, "translate", lambda text, s, t: f"<{text}>")
    monkeypatch.setattr(mt, "get_history_manager", lambda: _FakeHistory())
    out = mt.translate_batch_text(["a", "b"], target_lang="ja-JP")
    assert out == ["<a>", "<b>"]


def test_add_vocabulary_boundary(monkeypatch):
    seen = {}

    class _FakeLM:
        def add_vocabulary(self, **kw):
            seen.update(kw)
            return 7

    monkeypatch.setattr(mt, "get_learning_manager", lambda: _FakeLM())
    res = mt.add_vocabulary("apple", "蘋果", source_lang="en-US", target_lang="zh-TW")
    assert res == {"id": 7, "word": "apple"}
    assert seen["source_lang"] == "en_US" and seen["target_lang"] == "zh_TW"


def test_translate_with_learning_drains_generator(monkeypatch):
    monkeypatch.setattr(mt.translator, "translate_learning",
                        lambda text, s, t: iter(["partial", "FINAL"]))
    assert mt.translate_with_learning("x") == "FINAL"  # 取最後一個


def test_image_missing_file_returns_error():
    out = mt.translate_image("/no/such/file.png")
    assert "not found" in out


def test_mcp_object_is_fastmcp():
    from mcp.server.fastmcp import FastMCP
    assert isinstance(mt.mcp, FastMCP)
