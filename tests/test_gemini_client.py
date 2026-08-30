"""core/gemini_client.py 統一 client 工廠測試（T3-2 / T1-2）。

不打真 Gemini：以假 SDK（sys.modules patch，沿用全 repo 既有手法）驗證
金鑰解析、timeout 預設/覆寫、與窄簽名測試替身的降級相容。
"""
from __future__ import annotations

import sys
import types as _pytypes

import pytest

import core.gemini_client as gc


class _FakeHttpOptions:
    def __init__(self, timeout=None):
        self.timeout = timeout


def _install_fake_genai(monkeypatch, client_cls):
    fake_genai = _pytypes.ModuleType("google.genai")
    fake_genai.Client = client_cls
    fake_types = _pytypes.ModuleType("google.genai.types")
    fake_types.HttpOptions = _FakeHttpOptions
    fake_genai.types = fake_types
    import google as google_pkg
    monkeypatch.setattr(google_pkg, "genai", fake_genai, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_types)


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(gc.config, "get_gemini_api_key", lambda: None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gc.make_client()


def test_explicit_key_wins_and_timeout_passed(monkeypatch):
    captured = {}

    class _Client:
        def __init__(self, api_key=None, http_options=None):
            captured["api_key"] = api_key
            captured["http_options"] = http_options

    _install_fake_genai(monkeypatch, _Client)
    monkeypatch.setattr(gc.config, "get_gemini_api_key", lambda: "from-settings")
    gc.make_client("explicit-key", timeout_ms=5000)
    assert captured["api_key"] == "explicit-key"
    assert captured["http_options"].timeout == 5000


def test_settings_key_used_when_not_explicit(monkeypatch):
    captured = {}

    class _Client:
        def __init__(self, api_key=None, http_options=None):
            captured["api_key"] = api_key

    _install_fake_genai(monkeypatch, _Client)
    monkeypatch.setattr(gc.config, "get_gemini_api_key", lambda: "from-settings")
    gc.make_client()
    assert captured["api_key"] == "from-settings"


def test_narrow_fake_client_falls_back_without_http_options(monkeypatch):
    # 既有測試常用 lambda api_key: ... 當假 Client；工廠必須降級相容
    captured = {}

    def _client(api_key):  # 窄簽名：不收 http_options
        captured["api_key"] = api_key
        return "fake-client"

    _install_fake_genai(monkeypatch, _client)
    assert gc.make_client("k") == "fake-client"
    assert captured["api_key"] == "k"


def test_default_timeout_env_override(monkeypatch):
    monkeypatch.setenv(gc.GEMINI_TIMEOUT_MS_ENV, "45000")
    assert gc.default_timeout_ms() == 45000
    monkeypatch.setenv(gc.GEMINI_TIMEOUT_MS_ENV, "not-a-number")
    assert gc.default_timeout_ms() == gc.DEFAULT_TIMEOUT_MS
    monkeypatch.setenv(gc.GEMINI_TIMEOUT_MS_ENV, "-1")
    assert gc.default_timeout_ms() == gc.DEFAULT_TIMEOUT_MS
    monkeypatch.delenv(gc.GEMINI_TIMEOUT_MS_ENV)
    assert gc.default_timeout_ms() == gc.DEFAULT_TIMEOUT_MS
