"""U-1 / U-5: legacy UI 退場測試。

U-1（2026-06）：`/studio`（原 client-side 直連 Gemini、繞過後端計費 + review gate）
退場 → 一律 307 轉址到 `/app/`。
U-5（2026-08-30）：`/ui`（原 autoSolver React 前端）退場 — web/ 原始碼專案與
build 產物移除、U-3 的退場 banner 機制一併移除，`/ui` 與 `/studio` 同樣
一律 307 轉址到 `/app/`（舊書籤/deep-link 不 404）。

轉址不依賴 build 產物（無條件註冊），用 TestClient 驗。
"""
from fastapi.testclient import TestClient

from server.main import create_app


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


def test_ui_root_redirects_to_app():
    """U-5: `/ui` 退場 → 307 轉址到 `/app/`。"""
    client = TestClient(create_app(), follow_redirects=False)
    resp = client.get("/ui")
    assert resp.status_code == 307
    assert resp.headers["location"] == "/app/"


def test_ui_deeplink_redirects_to_app():
    """任何 `/ui/*` 子路徑（舊書籤 /ui/jobs/xxx、asset）一律導回 `/app/`，不 404。"""
    client = TestClient(create_app(), follow_redirects=False)
    for path in ("/ui/", "/ui/jobs/abc123", "/ui/proposals", "/ui/assets/index.js"):
        resp = client.get(path)
        assert resp.status_code == 307, path
        assert resp.headers["location"] == "/app/", path


def test_banner_helpers_removed():
    """U-5: U-3 的 banner 注入 helper 已隨 `/ui` 退場移除，不該再存在。"""
    import server.main as main_mod
    assert not hasattr(main_mod, "_legacy_banner_html")
    assert not hasattr(main_mod, "_inject_legacy_banner")
    assert not hasattr(main_mod, "_serve_legacy_spa")
