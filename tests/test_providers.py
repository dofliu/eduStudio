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
    OllamaProvider,
    Provider,
    generate_text_for_role,
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
        get_provider("claude")  # 尚未登記的 provider


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
    assert seen["model"] == "gemini-3.6-flash"   # text.fast 內建預設
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
        "model": "gemini-3.6-flash",
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
    assert model_id == "gemini-3.6-flash"


def test_provider_for_role_invalid_role_raises(settings_path):
    with pytest.raises(ValueError):
        provider_for_role("text.turbo")    # core.models.resolve type guard


def test_provider_for_role_tts_unregistered_raises(settings_path):
    # tts 角色 resolve 出 provider 'edge'，不在 LLM registry → ValueError（走 tts_backend）
    with pytest.raises(ValueError):
        provider_for_role("tts")


# ---------- OllamaProvider（F9-3b，本機可插拔，monkeypatch helper 不需真 ollama）----------

def test_ollama_provider_satisfies_protocol():
    assert isinstance(OllamaProvider(), Provider)


def test_ollama_provider_name():
    assert OllamaProvider().name == "ollama"


def test_ollama_provider_registered_singleton():
    # F9-3b 已在 module import 時 register → get_provider('ollama') 取得實作
    p = get_provider("ollama")
    assert isinstance(p, OllamaProvider)
    assert get_provider("ollama") is p


def test_ollama_generate_text_delegates_to_helper(monkeypatch):
    seen = {}

    def fake_generate(prompt, *, model, **kwargs):
        seen.update(prompt=prompt, model=model, kwargs=kwargs)
        return "  本機回應  "

    monkeypatch.setattr(providers, "ollama_generate", fake_generate)

    out = OllamaProvider().generate_text("翻譯這句", model="translategemma")
    assert out == "  本機回應  "          # provider 不再 strip（helper 已負責）
    assert seen["prompt"] == "翻譯這句"
    assert seen["model"] == "translategemma"
    assert "host" not in seen["kwargs"]    # 未指定 host → 不轉發，helper 走預設


def test_ollama_generate_text_forwards_host_when_set(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        providers, "ollama_generate",
        lambda prompt, *, model, **kwargs: seen.update(model=model, kwargs=kwargs) or "x",
    )

    OllamaProvider(host="http://gpu-box:11434").generate_text("hi", model="qwen2.5")
    assert seen["kwargs"]["host"] == "http://gpu-box:11434"


def test_ollama_generate_text_requires_model(monkeypatch):
    # 本機 provider 無雲端預設可退：model 未指定 → ValueError（type guard）
    monkeypatch.setattr(providers, "ollama_generate",
                        lambda *a, **k: pytest.fail("不該打 helper"))
    p = OllamaProvider()
    with pytest.raises(ValueError):
        p.generate_text("hi")
    with pytest.raises(ValueError):
        p.generate_text("hi", model="   ")   # 空白也算未指定


def test_ollama_does_not_record_cloud_usage(monkeypatch):
    # 本機 provider 不燒額度 → 不該碰 record_text_now（不汙染雲端成本帳）
    monkeypatch.setattr(providers, "ollama_generate",
                        lambda prompt, *, model, **k: "out")
    monkeypatch.setattr(providers, "record_text_now",
                        lambda *a, **k: pytest.fail("本機呼叫不該計雲端用量"))
    assert OllamaProvider().generate_text("hi", model="translategemma") == "out"


def test_ollama_image_and_tts_not_implemented(tmp_path):
    p = OllamaProvider()
    with pytest.raises(NotImplementedError):
        p.generate_image("draw")
    with pytest.raises(NotImplementedError):
        p.tts("hi", tmp_path / "out.mp3")


# ---------- generate_text_for_role：自動退雲端（F9-3d，mock 不打真 API）----------

def _point_role_to_ollama(settings_path, role="text.fast", model="translategemma"):
    """設定頁把某文字角色指到本機 ollama（巢狀 provider override）。"""
    _write_settings(settings_path,
                    {"model_roles": {role: {"provider": "ollama", "model": model}}})


def _stub_registered_gemini(monkeypatch):
    """把 registry 的 gemini 單例的 _ensure_client 換成 fake，避免建真 client；
    回傳一個 dict 記錄它被以哪個 model 呼叫。"""
    gemini = get_provider("gemini")
    monkeypatch.setattr(gemini, "_ensure_client", lambda: object())
    seen = {}
    monkeypatch.setattr(providers, "_gemini_text_call",
                        lambda c, m, p, *, temperature: seen.update(
                            model=m, prompt=p, temperature=temperature) or "雲端結果")
    monkeypatch.setattr(providers, "record_text_now",
                        lambda *a, **k: seen.update(recorded=True))
    return seen


def test_generate_text_for_role_gemini_goes_straight(settings_path, monkeypatch):
    # 角色 resolve 出 gemini（內建預設）→ 直接走雲端，不經退場包裝。
    seen = _stub_registered_gemini(monkeypatch)
    out = generate_text_for_role("text.fast", "hi", temperature=0.3, station="video")
    assert out == "雲端結果"
    assert seen["model"] == "gemini-3.6-flash"
    assert seen["temperature"] == 0.3
    assert seen.get("recorded") is True


def test_generate_text_for_role_local_success(settings_path, monkeypatch):
    # 角色指到 ollama 且本機成功 → 回本機結果，完全不碰雲端、不計帳。
    _point_role_to_ollama(settings_path)
    monkeypatch.setattr(providers, "ollama_generate",
                        lambda prompt, *, model, **k: f"本機:{model}")
    monkeypatch.setattr(providers, "_gemini_text_call",
                        lambda *a, **k: pytest.fail("本機成功不該打雲端"))
    monkeypatch.setattr(providers, "record_text_now",
                        lambda *a, **k: pytest.fail("本機成功不該計雲端帳"))
    out = generate_text_for_role("text.fast", "翻譯")
    assert out == "本機:translategemma"


def test_generate_text_for_role_falls_back_to_cloud_on_local_failure(
        settings_path, monkeypatch):
    # 本機失敗 + fallback 開（預設）+ 有金鑰 → 退回雲端、用該角色雲端預設 model。
    _point_role_to_ollama(settings_path)
    monkeypatch.setattr(providers, "ollama_generate",
                        lambda prompt, *, model, **k: (_ for _ in ()).throw(
                            RuntimeError("ollama 沒開")))
    monkeypatch.setattr(providers, "get_gemini_api_key", lambda: "key-123")
    monkeypatch.setattr(providers, "get_local_model_fallback", lambda: True)
    seen = _stub_registered_gemini(monkeypatch)

    out = generate_text_for_role("text.fast", "翻譯")
    assert out == "雲端結果"
    # 退場用雲端預設 model（gemini），不是本機 id
    assert seen["model"] == "gemini-3.6-flash"
    assert seen.get("recorded") is True   # 退雲端真燒額度 → 如實計帳


def test_generate_text_for_role_strict_local_reraises(settings_path, monkeypatch):
    # 本機失敗 + fallback 關（嚴格本機）→ 原樣拋，絕不上雲。
    _point_role_to_ollama(settings_path)
    monkeypatch.setattr(providers, "ollama_generate",
                        lambda prompt, *, model, **k: (_ for _ in ()).throw(
                            RuntimeError("ollama 沒開")))
    monkeypatch.setattr(providers, "get_gemini_api_key", lambda: "key-123")
    monkeypatch.setattr(providers, "get_local_model_fallback", lambda: False)
    monkeypatch.setattr(providers, "_gemini_text_call",
                        lambda *a, **k: pytest.fail("嚴格本機不該退雲端"))

    with pytest.raises(RuntimeError, match="ollama 沒開"):
        generate_text_for_role("text.fast", "翻譯")


def test_generate_text_for_role_no_key_reraises(settings_path, monkeypatch):
    # 本機失敗 + fallback 開但沒金鑰可退 → 原樣拋（不靜默吞錯）。
    _point_role_to_ollama(settings_path)
    monkeypatch.setattr(providers, "ollama_generate",
                        lambda prompt, *, model, **k: (_ for _ in ()).throw(
                            RuntimeError("ollama 沒開")))
    monkeypatch.setattr(providers, "get_gemini_api_key", lambda: None)
    monkeypatch.setattr(providers, "get_local_model_fallback", lambda: True)
    monkeypatch.setattr(providers, "_gemini_text_call",
                        lambda *a, **k: pytest.fail("沒金鑰不該打雲端"))

    with pytest.raises(RuntimeError, match="ollama 沒開"):
        generate_text_for_role("text.fast", "翻譯")


def test_generate_text_for_role_invalid_role_raises(settings_path):
    with pytest.raises(ValueError):
        generate_text_for_role("text.turbo", "hi")
