"""S-2 CORS 收緊 — 測 get_allowed_origins() 與 CORSMiddleware 實際行為。

預設只放行本機 origin；環境變數 EDUSTUDIO_ALLOWED_ORIGINS 可覆寫；
跨 origin 的非白名單來源不會拿到 access-control-allow-origin。
"""
from __future__ import annotations

import pytest

from core.config import DEFAULT_ALLOWED_ORIGINS, get_allowed_origins

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")

from fastapi.testclient import TestClient  # noqa: E402

from server.main import create_app  # noqa: E402


# ---------- 單元: get_allowed_origins() ----------

def test_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("EDUSTUDIO_ALLOWED_ORIGINS", raising=False)
    assert get_allowed_origins() == DEFAULT_ALLOWED_ORIGINS


def test_default_when_env_blank(monkeypatch):
    monkeypatch.setenv("EDUSTUDIO_ALLOWED_ORIGINS", "   ")
    assert get_allowed_origins() == DEFAULT_ALLOWED_ORIGINS


def test_parses_comma_separated(monkeypatch):
    monkeypatch.setenv(
        "EDUSTUDIO_ALLOWED_ORIGINS",
        "https://a.example, https://b.example ,https://c.example",
    )
    assert get_allowed_origins() == [
        "https://a.example",
        "https://b.example",
        "https://c.example",
    ]


def test_wildcard_passthrough(monkeypatch):
    monkeypatch.setenv("EDUSTUDIO_ALLOWED_ORIGINS", "*")
    assert get_allowed_origins() == ["*"]


# ---------- 整合: CORSMiddleware 行為 ----------

def test_allowed_origin_gets_cors_header(monkeypatch):
    monkeypatch.setenv("EDUSTUDIO_ALLOWED_ORIGINS", "http://127.0.0.1:8000")
    client = TestClient(create_app())
    resp = client.get("/openapi.json", headers={"Origin": "http://127.0.0.1:8000"})
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"


def test_disallowed_origin_no_cors_header(monkeypatch):
    monkeypatch.setenv("EDUSTUDIO_ALLOWED_ORIGINS", "http://127.0.0.1:8000")
    client = TestClient(create_app())
    resp = client.get("/openapi.json", headers={"Origin": "http://evil.example"})
    # 端點本身照常回應, 但不會 echo 非白名單 origin → 瀏覽器擋下跨站讀取
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") != "http://evil.example"
