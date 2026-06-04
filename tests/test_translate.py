"""雙語字幕翻譯層測試 — core/translate.py (Ollama translategemma).

純 offline: monkeypatch _call_ollama / urlopen, 不真打 Ollama HTTP。
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from core import translate


class TestBuildPrompt:
    def test_lang_code_maps_to_full_name(self):
        assert "English" in translate._build_prompt("文字", "en")
        assert "Japanese" in translate._build_prompt("文字", "ja")

    def test_unknown_lang_code_used_verbatim(self):
        # 沒在 _LANG_NAMES 的 code 原樣用 (不炸)
        assert "Klingon" in translate._build_prompt("文字", "Klingon")

    def test_prompt_contains_source_text(self):
        assert "材料力學" in translate._build_prompt("材料力學", "en")


class TestTranslateText:
    def test_empty_returns_empty_no_call(self, monkeypatch):
        called = []
        monkeypatch.setattr(translate, "_call_ollama", lambda *a, **k: called.append(1) or "x")
        assert translate.translate_text("") == ""
        assert translate.translate_text(None) == ""
        assert translate.translate_text("   ") == ""
        assert called == []  # 空字串不該觸發呼叫

    def test_nonempty_calls_ollama(self, monkeypatch):
        monkeypatch.setattr(translate, "_call_ollama", lambda prompt, **k: "Hello world.")
        assert translate.translate_text("你好世界。") == "Hello world."

    def test_target_lang_passed_into_prompt(self, monkeypatch):
        seen = {}
        def fake(prompt, **k):
            seen["prompt"] = prompt
            return "x"
        monkeypatch.setattr(translate, "_call_ollama", fake)
        translate.translate_text("文字", target_lang="ja")
        assert "Japanese" in seen["prompt"]


class TestTranslateSteps:
    def _fake(self, monkeypatch):
        # 翻譯 = 在原文前加 [EN]
        monkeypatch.setattr(
            translate, "translate_text",
            lambda text, **k: f"[EN]{text}",
        )

    def test_fills_out_field(self, monkeypatch):
        self._fake(monkeypatch)
        steps = [{"narration": "一。"}, {"narration": "二。"}]
        out = translate.translate_steps(steps)
        assert out[0]["narration_secondary"] == "[EN]一。"
        assert out[1]["narration_secondary"] == "[EN]二。"

    def test_empty_narration_skipped(self, monkeypatch):
        self._fake(monkeypatch)
        out = translate.translate_steps([{"narration": ""}, {"narration": None}, {}])
        # 都沒寫 out_field
        assert all("narration_secondary" not in s for s in out)

    def test_existing_out_field_not_overwritten(self, monkeypatch):
        self._fake(monkeypatch)
        steps = [{"narration": "一。", "narration_secondary": "人工修過的"}]
        out = translate.translate_steps(steps)
        assert out[0]["narration_secondary"] == "人工修過的"  # idempotent

    def test_does_not_mutate_input(self, monkeypatch):
        self._fake(monkeypatch)
        steps = [{"narration": "一。"}]
        translate.translate_steps(steps)
        assert "narration_secondary" not in steps[0]  # 原 dict 不變

    def test_custom_field_names(self, monkeypatch):
        self._fake(monkeypatch)
        steps = [{"zh": "中文。"}]
        out = translate.translate_steps(steps, field="zh", out_field="ja_text")
        assert out[0]["ja_text"] == "[EN]中文。"


class TestCallOllamaErrors:
    def test_urlerror_becomes_translate_error(self, monkeypatch):
        def boom(req, timeout=None):
            raise urllib.error.URLError("connection refused")
        monkeypatch.setattr(translate.urllib.request, "urlopen", boom)
        with pytest.raises(translate.TranslateError) as ei:
            translate._call_ollama("p", model="translategemma", host="http://localhost:11434", timeout=5)
        assert "ollama serve" in str(ei.value)  # 訊息含修復指引

    def test_response_parsed(self, monkeypatch):
        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"response": "  translated  "}).encode()
        monkeypatch.setattr(translate.urllib.request, "urlopen", lambda req, timeout=None: _Resp())
        out = translate._call_ollama("p", model="m", host="http://x", timeout=5)
        assert out == "translated"  # strip 過
