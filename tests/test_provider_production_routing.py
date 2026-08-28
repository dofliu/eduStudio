"""Production text callers 必須遵守 model role provider，不可只解析 model id。"""
from __future__ import annotations

import json

from core import outliner, providers, scriptor


def _ollama_settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "model_roles": {
            "text.fast": {"provider": "ollama", "model": "qwen3:4b"},
        },
    }), encoding="utf-8")
    monkeypatch.setenv("ES_SETTINGS_PATH", str(path))


def test_outliner_ollama_does_not_require_gemini_key(tmp_path, monkeypatch):
    _ollama_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(
        outliner, "get_gemini_api_key", lambda: (_ for _ in ()).throw(
            AssertionError("Ollama outline 不應讀 Gemini key")),
    )
    monkeypatch.setattr(
        providers, "generate_text_for_role",
        lambda *a, **k: '{"deck_title":"Local","summary":"ok","sections":[]}',
    )

    result = outliner._call_outline_gemini("outline")
    assert result["deck_title"] == "Local"


def test_scriptor_ollama_does_not_create_gemini_client(tmp_path, monkeypatch):
    _ollama_settings(tmp_path, monkeypatch)
    monkeypatch.setattr(
        scriptor, "get_gemini_api_key", lambda: (_ for _ in ()).throw(
            AssertionError("Ollama scriptor 不應讀 Gemini key")),
    )
    client, types = scriptor._provider_client()
    assert client is None and types is None

    monkeypatch.setattr(
        providers, "generate_text_for_role",
        lambda *a, **k: '{"id":"s1","title":"Local","slides":[]}',
    )
    section = scriptor._call_with_retry(
        None, None, "script", "s1", {"id": "s1", "title": "Local"},
    )
    assert section["id"] == "s1"
