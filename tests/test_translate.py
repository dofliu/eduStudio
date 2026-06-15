"""雙語字幕翻譯層測試 — core/translate.py。

2026-06-04 後端定案: 預設 Gemini,Ollama 退為 TRANSLATION_BACKEND=ollama fallback。
純 offline: Gemini 路徑用 sys.modules 注入 fake google.genai(不需實裝 SDK、不打真 API);
Ollama 路徑 monkeypatch _call_ollama / urlopen。
"""
from __future__ import annotations

import json
import sys
import types as pytypes
import urllib.error
from unittest.mock import MagicMock

import pytest

from core import ollama_client, translate


def _install_fake_genai(monkeypatch, *, resp_text="繁中譯文", exc=None):
    """注入假的 google.genai 到 sys.modules,回 capture dict(收 generate_content 參數)。"""
    capture: dict = {}

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            capture["model"] = model
            capture["contents"] = contents
            capture["config"] = config
            if exc is not None:
                raise exc
            r = MagicMock()
            r.text = resp_text
            return r

    class _FakeClient:
        def __init__(self, api_key=None):
            capture["api_key"] = api_key
            self.models = _FakeModels()

    fake_genai = pytypes.ModuleType("google.genai")
    fake_types = pytypes.ModuleType("google.genai.types")
    fake_types.GenerateContentConfig = lambda **kw: dict(kw)
    fake_genai.Client = _FakeClient
    fake_genai.types = fake_types

    google_pkg = sys.modules.get("google") or pytypes.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setattr(google_pkg, "genai", fake_genai, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)
    return capture


class TestBuildPrompt:
    def test_lang_code_maps_to_full_name(self):
        assert "English" in translate._build_prompt("文字", "en")
        assert "Japanese" in translate._build_prompt("文字", "ja")

    def test_zh_tw_canonical_maps_to_traditional(self):
        # canonical zh-TW(連字號)→ Traditional Chinese
        assert "Traditional Chinese" in translate._build_prompt("文字", "zh-TW")

    def test_unknown_lang_code_used_verbatim(self):
        assert "Klingon" in translate._build_prompt("文字", "Klingon")

    def test_prompt_contains_source_text(self):
        assert "材料力學" in translate._build_prompt("材料力學", "en")


class TestResolveBackend:
    def test_default_is_gemini(self, monkeypatch):
        monkeypatch.delenv("TRANSLATION_BACKEND", raising=False)
        assert translate._resolve_backend() == "gemini"

    def test_env_ollama(self, monkeypatch):
        monkeypatch.setenv("TRANSLATION_BACKEND", "Ollama")
        assert translate._resolve_backend() == "ollama"


class TestTranslateWithGemini:
    def test_empty_returns_blank(self):
        assert translate.translate_with_gemini("") == ""
        assert translate.translate_with_gemini(None) == ""

    def test_missing_key_raises(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(translate.TranslateError) as ei:
            translate.translate_with_gemini("文字", target_lang="en")
        assert "GEMINI_API_KEY" in str(ei.value)

    def test_success_strips_and_passes_canonical_lang(self, monkeypatch):
        cap = _install_fake_genai(monkeypatch, resp_text="  Moment  ")
        out = translate.translate_with_gemini("力矩", target_lang="en", api_key="fake")
        assert out == "Moment"  # 前後空白被 strip
        assert cap["api_key"] == "fake"
        from core import config
        assert cap["model"] == config.GEMINI_MODEL   # 無設定頁覆寫時 = 預設
        assert "English" in cap["contents"][0]

    def test_api_error_wrapped(self, monkeypatch):
        _install_fake_genai(monkeypatch, exc=RuntimeError("rate limit"))
        with pytest.raises(translate.TranslateError) as ei:
            translate.translate_with_gemini("文字", target_lang="en", api_key="fake")
        assert "rate limit" in str(ei.value)

    def test_key_not_in_error_message(self, monkeypatch):
        # 金鑰不得反射進錯誤訊息(防外洩)
        _install_fake_genai(monkeypatch, exc=RuntimeError("boom"))
        with pytest.raises(translate.TranslateError) as ei:
            translate.translate_with_gemini("文字", target_lang="en", api_key="SECRET123")
        assert "SECRET123" not in str(ei.value)


class TestTranslateText:
    def test_empty_returns_empty_no_call(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            translate, "translate_with_gemini",
            lambda *a, **k: called.append(1) or "x",
        )
        assert translate.translate_text("") == ""
        assert translate.translate_text(None) == ""
        assert translate.translate_text("   ") == ""
        assert called == []  # 空字串不該觸發呼叫

    def test_default_routes_to_gemini_with_zh_tw(self, monkeypatch):
        monkeypatch.delenv("TRANSLATION_BACKEND", raising=False)
        seen = {}

        def fake_gemini(text, *, target_lang, api_key=None):
            seen["lang"] = target_lang
            return "G"

        monkeypatch.setattr(translate, "translate_with_gemini", fake_gemini)
        # 預設 target_lang 已由 'en' 改為 canonical 'zh-TW'
        assert translate.translate_text("你好世界。") == "G"
        assert seen["lang"] == "zh-TW"

    def test_backend_ollama_routes_to_call_ollama(self, monkeypatch):
        monkeypatch.setattr(
            translate, "_call_ollama",
            lambda prompt, **k: "Hello world.",
        )
        assert translate.translate_text("你好世界。", backend="ollama") == "Hello world."

    def test_env_backend_ollama(self, monkeypatch):
        monkeypatch.setenv("TRANSLATION_BACKEND", "ollama")
        monkeypatch.setattr(translate, "_call_ollama", lambda prompt, **k: "O")
        assert translate.translate_text("你好。") == "O"

    def test_target_lang_passed_into_prompt_ollama(self, monkeypatch):
        seen = {}

        def fake(prompt, **k):
            seen["prompt"] = prompt
            return "x"

        monkeypatch.setattr(translate, "_call_ollama", fake)
        translate.translate_text("文字", target_lang="ja", backend="ollama")
        assert "Japanese" in seen["prompt"]


class TestTranslateSteps:
    def _fake(self, monkeypatch):
        # 翻譯 = 在原文前加 [T]（backend 無關，直接替換 translate_text）
        monkeypatch.setattr(
            translate, "translate_text",
            lambda text, **k: f"[T]{text}",
        )

    def test_fills_out_field(self, monkeypatch):
        self._fake(monkeypatch)
        steps = [{"narration": "一。"}, {"narration": "二。"}]
        out = translate.translate_steps(steps)
        assert out[0]["narration_secondary"] == "[T]一。"
        assert out[1]["narration_secondary"] == "[T]二。"

    def test_default_target_lang_is_zh_tw(self, monkeypatch):
        seen = {}

        def fake(text, **k):
            seen["lang"] = k.get("target_lang")
            return "x"

        monkeypatch.setattr(translate, "translate_text", fake)
        translate.translate_steps([{"narration": "一。"}])
        assert seen["lang"] == "zh-TW"

    def test_empty_narration_skipped(self, monkeypatch):
        self._fake(monkeypatch)
        out = translate.translate_steps([{"narration": ""}, {"narration": None}, {}])
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
        assert out[0]["ja_text"] == "[T]中文。"


class TestCallOllamaErrors:
    """Ollama fallback 路徑(TRANSLATION_BACKEND=ollama 時才走)仍可用。

    urllib 呼叫已抽到 core.ollama_client(F9-3a),故 monkeypatch 該模組的 urlopen;
    驗 translate._call_ollama 仍把 OllamaError 包成 TranslateError(行為不變)。
    """

    def test_urlerror_becomes_translate_error(self, monkeypatch):
        def boom(req, timeout=None):
            raise urllib.error.URLError("connection refused")
        monkeypatch.setattr(ollama_client.urllib.request, "urlopen", boom)
        with pytest.raises(translate.TranslateError) as ei:
            translate._call_ollama("p", model="translategemma", host="http://localhost:11434", timeout=5)
        assert "ollama serve" in str(ei.value)  # 訊息含修復指引

    def test_response_parsed(self, monkeypatch):
        class _Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"response": "  translated  "}).encode()
        monkeypatch.setattr(ollama_client.urllib.request, "urlopen", lambda req, timeout=None: _Resp())
        out = translate._call_ollama("p", model="m", host="http://x", timeout=5)
        assert out == "translated"  # strip 過
