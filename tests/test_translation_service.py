"""core/translation/service.py 測試（eduStudio 合併 Phase B-2）。

純方法（detect/resolve/build_prompt）不打外部；LLM 方法 monkeypatch _gemini_complete
不打真 Gemini。重依賴方法（OCR/STT/TTS/PDF）走 importorskip 或驗 lazy-import 降級訊息。
"""
from __future__ import annotations

import core.translation.service as svc


# ---------- 純方法 ----------
class TestDetectAndResolve:
    def test_detect_languages(self):
        s = svc.translator
        assert s.detect_source_language("這是繁體中文") == "zh_TW"
        assert s.detect_source_language("これはテスト") == "ja_JP"
        assert s.detect_source_language("안녕하세요") == "ko_KR"
        assert s.detect_source_language("hello") == "en_US"
        assert s.detect_source_language("") == "en_US"

    def test_resolve_source(self):
        s = svc.translator
        assert s._resolve_source_code("hi", "en_US") == "en_US"
        assert s._resolve_source_code("hi", "bogus") == "en_US"  # 不在 LANGUAGES → en_US
        assert s._resolve_source_code("繁體中文字", "auto") == "zh_TW"


class TestBuildPrompt:
    def test_zh_tw_branch_has_traditional_rules(self):
        p = svc.translator._build_prompt("hello", "en_US", "zh_TW")
        assert "Traditional Chinese" in p and "Simplified" in p

    def test_other_branch(self):
        p = svc.translator._build_prompt("你好", "zh_TW", "en_US")
        assert "English" in p and "hello" not in p

    def test_glossary_and_style_injected(self):
        p = svc.translator._build_prompt(
            "x", "en_US", "ja_JP", glossary="API=介面", style="正式"
        )
        assert "API=介面" in p and "正式" in p


# ---------- LLM 方法（mock _gemini_complete）----------
class TestTranslate:
    def test_completion_routes_through_text_provider(self, monkeypatch):
        from core import providers
        seen = {}
        monkeypatch.setattr(
            providers, "generate_text_for_role",
            lambda role, prompt, **kwargs: seen.update(
                role=role, prompt=prompt, kwargs=kwargs) or "  LOCAL  ",
        )

        assert svc._gemini_complete("translate") == "LOCAL"
        assert seen["role"] == "text.fast"
        assert seen["kwargs"]["station"] == "language"

    def test_translate_returns_gemini_output(self, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda prompt: "MOCKED")
        assert svc.translator.translate("hello", "en_US", "zh_TW") == "MOCKED"

    def test_translate_empty_returns_blank_no_call(self, monkeypatch):
        called = []
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: called.append(1) or "x")
        assert svc.translator.translate("  ", "en_US", "zh_TW") == ""
        assert called == []

    def test_translate_exception_becomes_message(self, monkeypatch):
        def boom(p):
            raise RuntimeError("rate limit")
        monkeypatch.setattr(svc, "_gemini_complete", boom)
        out = svc.translator.translate("hello", "en_US", "zh_TW")
        assert out.startswith("翻譯失敗") and "rate limit" in out

    def test_translate_stream_yields_once(self, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: "STREAMED")
        chunks = list(svc.translator.translate_stream("hi", "en_US", "ja_JP"))
        assert chunks == ["STREAMED"]


class TestLearningMethods:
    def test_dictation_check_empty(self):
        assert "請提供" in svc.translator.dictation_check("", "", "zh_TW")

    def test_dictation_check_mocked(self, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: "FEEDBACK")
        assert svc.translator.dictation_check("原文", "聽寫", "zh_TW") == "FEEDBACK"

    def test_flashcards_mocked(self, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: "CARDS")
        assert list(svc.translator.generate_flashcards("text", "en_US", "zh_TW")) == ["CARDS"]

    def test_writing_correction_mocked(self, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: "CORRECTED")
        assert list(svc.translator.writing_correction("txt", "en_US", "zh_TW")) == ["CORRECTED"]

    def test_conversation_mocked(self, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: "REPLY")
        out = list(svc.translator.conversation_practice("café", "hi", "en_US", "zh_TW"))
        assert out == ["REPLY"]

    def test_learning_translate_mocked(self, monkeypatch):
        monkeypatch.setattr(svc, "_gemini_complete", lambda p: "LEARN")
        assert list(svc.translator.translate_learning("t", "en_US", "zh_TW")) == ["LEARN"]


# ---------- 重依賴方法的 lazy 降級（不裝套件時回友善訊息，不崩）----------
class TestLazyDegradation:
    def test_speech_to_text_graceful_when_missing(self, monkeypatch):
        # 模擬 faster_whisper 未裝：import 失敗回友善訊息
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *a, **k):
            if name == "faster_whisper":
                raise ImportError("no module")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        text, lang = svc.translator.speech_to_text("x.wav")
        assert "未安裝" in text
