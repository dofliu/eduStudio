"""S-1 單一共享 token 驗證層測試。

涵蓋:
- 沒設 token → 完全放行(既有行為不變)
- 設了 token → API 無憑證 401 / Bearer 通過 / cookie 通過 / 錯憑證 401
- /auth 登入種 cookie(HttpOnly + SameSite=Strict) 後可存取
- 媒體/受保護端點無憑證被擋
- 瀏覽器 HTML 請求未授權 → 回登入框(200) 而非 401
- /auth 與 /health 豁免
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")

from fastapi.testclient import TestClient  # noqa: E402

from server.auth import COOKIE_NAME, TOKEN_ENV  # noqa: E402
from server.main import create_app  # noqa: E402

TOKEN = "s3cr3t-test-token"


def _client() -> TestClient:
    # follow_redirects=False 讓我們能檢查 /auth 的 303 + Set-Cookie
    return TestClient(create_app())


# ---------- 沒設 token: 全開 ----------

def test_open_when_token_unset(monkeypatch):
    monkeypatch.delenv(TOKEN_ENV, raising=False)
    c = _client()
    assert c.get("/health").status_code == 200
    # 受保護的 API 在無驗證模式照常運作(這裡 list jobs 應 200)
    assert c.get("/jobs").status_code in (200, 404)


# ---------- 設了 token: 擋 ----------

def test_api_rejected_without_credentials(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = _client()
    r = c.get("/jobs", headers={"accept": "application/json"})
    assert r.status_code == 401


def test_bearer_passes(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = _client()
    r = c.get("/jobs", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code in (200, 404)  # 通過驗證(非 401)


def test_wrong_bearer_rejected(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = _client()
    r = c.get("/jobs", headers={"Authorization": "Bearer wrong", "accept": "application/json"})
    assert r.status_code == 401


def test_health_exempt_even_with_token(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = _client()
    assert c.get("/health").status_code == 200


def test_openapi_protected_with_token(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = _client()
    r = c.get("/openapi.json", headers={"accept": "application/json"})
    assert r.status_code == 401


# ---------- /auth 登入流程 ----------

def test_auth_sets_secure_cookie_and_grants_access(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = TestClient(create_app(), follow_redirects=False)
    r = c.post("/auth", data={"token": TOKEN, "next": "/app/"})
    assert r.status_code == 303
    assert r.headers["location"] == "/app/"
    set_cookie = r.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=strict" in set_cookie.lower()

    # 登入後 client 帶著 cookie → 受保護端點可達
    r2 = c.get("/jobs")
    assert r2.status_code in (200, 404)


def test_auth_wrong_token_no_cookie(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = TestClient(create_app(), follow_redirects=False)
    r = c.post("/auth", data={"token": "nope", "next": "/app/"})
    assert r.status_code == 401
    assert COOKIE_NAME not in r.headers.get("set-cookie", "")


def test_auth_json_body_accepted(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = TestClient(create_app(), follow_redirects=False)
    r = c.post("/auth", json={"token": TOKEN})
    assert r.status_code == 303
    assert COOKIE_NAME in r.headers.get("set-cookie", "")


def test_auth_rejects_open_redirect(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = TestClient(create_app(), follow_redirects=False)
    r = c.post("/auth", data={"token": TOKEN, "next": "//evil.example/"})
    assert r.status_code == 303
    assert r.headers["location"] == "/app/"  # 外部 next 被擋回預設


# ---------- 瀏覽器 HTML: 回登入框而非 401 ----------

def test_html_navigation_returns_login_page(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = _client()
    r = c.get("/app/", headers={"accept": "text/html"})
    assert r.status_code == 200
    assert "登入" in r.text
    assert 'action="/auth"' in r.text


def test_auth_endpoint_reachable_without_credentials(monkeypatch):
    monkeypatch.setenv(TOKEN_ENV, TOKEN)
    c = TestClient(create_app(), follow_redirects=False)
    # 即使沒登入, POST /auth 本身不可被 middleware 擋(否則無法登入)
    r = c.post("/auth", data={"token": "whatever"})
    assert r.status_code in (303, 401)  # 被 auth 端點處理(非 middleware 401 JSON)
