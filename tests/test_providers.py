"""M-4 Provider adapter 介面（B-ready stub）— core/providers.py。

全程不打真 API、不需裝 google-genai：``_gemini_text_call`` 與 ``generate_image_b64``
都被 monkeypatch，client 用 fake 注入。settings 指 tmp 隔離，resolve 走內建預設。
"""
from __future__ import annotations

import json

import pytest

from core import providers
from core.providers import (
    GeminiProvider,
    Provider,
    get_provider,
    provider_for_role,
    register_provider,
)


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    monkeypatch.setenv("ES_SETTINGS_PATH", str(p))
    return p


def _write_settings(path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ---------- 協定 / registry ----------

def test_gemini_provider_satisfies_protocol():
    assert isinstance(GeminiProvider(), Provider)


def test_gemini_provider_name():
    assert GeminiProvider().name == "gemini"


def test_get_provider_returns_registered_gemini_singleton():
    p = get_provider("gemini")
    assert isinstance(p, GeminiProvider)
    # registry 是單例：兩次取同一個
    assert get_provider("gemini") is p


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("ollama")  # B 階段才登記


def test_register_provider_roundtrip():
    class Dummy:
        name = "dummy-test-provider"

        def generate_text(self, prompt, *, model=None, temperature=0.4, station="text"):
            return ""

        def generate_image(self, prompt, *, model=None, station="visual", files=None, api_key=None):
            return ""

        def tts(self, text, out_path):
            return False

    d = Dummy()
    register_provider(d)
    try:
        assert get_provider("dummy-test-provider") is d
    finally:
        providers._REGISTRY.pop("dummy-test-provider", None)


# ---------- generate_text（注入 fake client + monkeypatch genai 呼叫）----------

def test_generate_text_resolves_text_fast_by_default(settings_path, monkeypatch):
    seen = {}

    def fake_call(client, model, prompt, *, temperature):
        seen.update(client=client, model=model, prompt=prompt, temperature=temperature)
        return "hello world"

    monkeypatch.setattr(providers, "_gemini_text_call", fake_call)
    monkeypatch.setattr(providers, "record_text_now", lambda *a, **k: None)

    fake_client = object()
    out = GeminiProvider(client=fake_client).generate_text("hi", temperature=0.2)

    assert out == "hello world"
    assert seen["client"] is fake_client
    assert seen["model"] == "gemini-3.5-flash"   # text.fast 內建預設
    assert seen["prompt"] == "hi"
    assert seen["temperature"] == 0.2


def test_generate_text_explicit_model_overrides_role(settings_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(providers, "_gemini_text_call",
                        lambda c, m, p, *, temperature: seen.update(model=m) or "x")
    monkeypatch.setattr(providers, "record_text_now", lambda *a, **k: None)

    GeminiProvider(client=object()).generate_text("hi", model="gemini-9.9-custom")
    assert seen["model"] == "gemini-9.9-custom"


def test_generate_text_honours_settings_override(settings_path, monkeypatch):
    _write_settings(settings_path, {"model_roles": {"text.fast": "gemini-from-settings"}})
    seen = {}
    monkeypatch.setattr(providers, "_gemini_text_call",
                        lambda c, m, p, *, temperature: seen.update(model=m) or "x")
    monkeypatch.setattr(providers, "record_text_now", lambda *a, **k: None)

    GeminiProvider(client=object()).generate_text("hi")
    assert seen["model"] == "gemini-from-settings"


def test_generate_text_records_usage(settings_path, monkeypatch):
    recorded = {}
    monkeypatch.setattr(providers, "_gemini_text_call",
                        lambda c, m, p, *, temperature: "the-response")
    monkeypatch.setattr(providers, "record_text_now",
                        lambda station, model, prompt, response, **k:
                        recorded.update(station=station, model=model,
                                        prompt=prompt, response=response))

    GeminiProvider(client=object()).generate_text("the-prompt", station="video")
    assert recorded == {
        "station": "video",
        "model": "gemini-3.5-flash",
        "prompt": "the-prompt",
        "response": "the-response",
    }


# ---------- generate_image（委派既有 generate_image_b64）----------

def test_generate_image_delegates_to_existing_helper(monkeypatch):
    from core.infocards import gemini as ic_gemini

    seen = {}

    def fake_b64(prompt, *, model=None, api_key=None, files=None):
        seen.update(prompt=prompt, model=model, api_key=api_key, files=files)
        return "data:image/png;base64,AAAA"

    monkeypatch.setattr(ic_gemini, "generate_image_b64", fake_b64)

    out = GeminiProvider(api_key="k").generate_image("draw a cat", files=[{"x": 1}])
    assert out == "data:image/png;base64,AAAA"
    assert seen["prompt"] == "draw a cat"
    assert seen["model"] is None          # 未指定 → 由 helper 走 image.fast
    assert seen["api_key"] == "k"
    assert seen["files"] == [{"x": 1}]


# ---------- tts 非 gemini 職責 ----------

def test_gemini_tts_raises_not_implemented(tmp_path):
    with pytest.raises(NotImplementedError):
        GeminiProvider().tts("hi", tmp_path / "out.mp3")


# ---------- provider_for_role（B-ready 座位）----------

def test_provider_for_role_text_returns_gemini_and_model(settings_path):
    provider, model_id = provider_for_role("text.fast")
    assert provider is get_provider("gemini")
    assert model_id == "gemini-3.5-flash"


def test_provider_for_role_invalid_role_raises(settings_path):
    with pytest.raises(ValueError):
        provider_for_role("text.turbo")    # core.models.resolve type guard


def test_provider_for_role_tts_unregistered_raises(settings_path):
    # tts 角色 resolve 出 provider 'edge'，不在 LLM registry → ValueError（走 tts_backend）
    with pytest.raises(ValueError):
        provider_for_role("tts")
