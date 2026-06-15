"""U-3 / U-1: legacy UI 退場測試。

U-3：`/ui` 頂部注入「即將退場、改用 /app」banner（非破壞性過渡提示）。
U-1：`/studio`（原 client-side 直連 Gemini、繞過後端計費 + review gate）退場 →
一律 307 轉址到 `/app/`。

`/ui` build 產物在測試環境通常不存在（route 不註冊），故 banner 直接單元測注入
helper；`/studio` 轉址不依賴 build 產物（無條件註冊），用 TestClient 驗。
"""
from fastapi.testclient import TestClient

from server.main import (
    _inject_legacy_banner,
    _legacy_banner_html,
    create_app,
)


def test_banner_links_to_app():
    html = _legacy_banner_html()
    assert 'href="/app/"' in html
    assert "legacy" in html


def test_inject_after_body_tag():
    html = "<html><body class=\"x\"><div id=\"root\"></div></body></html>"
    out = _inject_legacy_banner(html)
    # banner 在 <body ...> 之後、#root 之前
    body_close = out.find(">", out.find("<body"))
    assert out.index("/app/") > body_close
    assert out.index("/app/") < out.index('id="root"')
    # 原內容保留
    assert '<div id="root"></div>' in out


def test_inject_without_body_prepends():
    html = "<div id=\"root\"></div>"
    out = _inject_legacy_banner(html)
    assert out.startswith("<div role=\"alert\"")
    assert html in out


def test_inject_handles_uppercase_body():
    html = "<HTML><BODY><main></main></BODY></HTML>"
    out = _inject_legacy_banner(html)
    assert "/app/" in out
    assert "<main></main>" in out


def test_studio_root_redirects_to_app():
    """U-1: `/studio` 退場 → 307 轉址到 `/app/`，不再 serve 直連 Gemini 的 SPA。"""
    client = TestClient(create_app(), follow_redirects=False)
    resp = client.get("/studio")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/app/"


def test_studio_deeplink_redirects_to_app():
    """任何 `/studio/*` 子路徑（含舊書籤/asset）一律導回 `/app/`，不 404。"""
    client = TestClient(create_app(), follow_redirects=False)
    for path in ("/studio/", "/studio/poster", "/studio/assets/index.js"):
        resp = client.get(path)
        assert resp.status_code == 307, path
        assert resp.headers["location"] == "/app/", path
