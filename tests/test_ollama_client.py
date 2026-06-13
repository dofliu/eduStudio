"""本機 Ollama 文字呼叫共用層測試 — core/ollama_client.py(F9-3a)。

純 offline: monkeypatch urllib.request.urlopen,不需真 ollama、不打任何網路。
驗證 translate.py 與未來 OllamaProvider 共用的單一真實來源行為:
成功解析 response、URLError/非 JSON 包成領域中立的 OllamaError(含修復指引)。
"""
from __future__ import annotations

import json
import urllib.error

import pytest

from core import ollama_client
from core.ollama_client import OllamaError, ollama_generate


class _Resp:
    """假的 urlopen context manager,回固定 JSON body。"""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def test_success_parses_and_strips(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Resp(json.dumps({"response": "  hello  "}).encode())

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", fake_urlopen)
    out = ollama_generate("翻我", model="translategemma", host="http://x:11434", timeout=7)
    assert out == "hello"  # strip 過
    assert captured["url"] == "http://x:11434/api/generate"
    assert captured["data"] == {
        "model": "translategemma",
        "prompt": "翻我",
        "stream": False,
    }
    assert captured["timeout"] == 7


def test_host_trailing_slash_trimmed(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        ollama_client.urllib.request,
        "urlopen",
        lambda req, timeout=None: seen.update(url=req.full_url) or _Resp(
            json.dumps({"response": "x"}).encode()
        ),
    )
    ollama_generate("p", model="m", host="http://h:11434/")
    assert seen["url"] == "http://h:11434/api/generate"  # 不重複斜線


def test_missing_response_key_returns_empty(monkeypatch):
    monkeypatch.setattr(
        ollama_client.urllib.request,
        "urlopen",
        lambda req, timeout=None: _Resp(json.dumps({}).encode()),
    )
    assert ollama_generate("p", model="m") == ""


def test_urlerror_becomes_ollama_error(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(ollama_client.urllib.request, "urlopen", boom)
    with pytest.raises(OllamaError) as ei:
        ollama_generate("p", model="translategemma")
    msg = str(ei.value)
    assert "ollama serve" in msg  # 修復指引
    assert "ollama pull translategemma" in msg  # 帶 model 名


def test_non_json_becomes_ollama_error(monkeypatch):
    monkeypatch.setattr(
        ollama_client.urllib.request,
        "urlopen",
        lambda req, timeout=None: _Resp(b"not json"),
    )
    with pytest.raises(OllamaError) as ei:
        ollama_generate("p", model="m")
    assert "非 JSON" in str(ei.value)


def test_defaults_present():
    # 預設 host / timeout 為單一真實來源,translate.py 沿用。
    assert ollama_client.DEFAULT_OLLAMA_HOST.startswith("http")
    assert ollama_client.DEFAULT_TIMEOUT > 0


def test_ollama_error_is_runtime_error():
    # 領域中立: 呼叫端可用 RuntimeError 寬鬆攔截。
    assert issubclass(OllamaError, RuntimeError)
