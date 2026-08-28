"""FastAPI lifespan 啟動契約測試。"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi")
pytest.importorskip("multipart", reason="server upload routes 需要 python-multipart")

from fastapi.testclient import TestClient

from server import main as main_mod


def test_lifespan_runs_startup_checks_once(monkeypatch):
    """TestClient context 必須進入 lifespan，且啟動檢查只執行一次。"""
    calls: list[str] = []

    class _Store:
        def list(self):
            return []

        def resume_interrupted(self):
            calls.append("resume")
            return []

    monkeypatch.setattr(main_mod, "setup_utf8_stdout", lambda: calls.append("utf8"))
    monkeypatch.setattr(main_mod, "get_default_store", lambda: _Store())
    monkeypatch.setattr(main_mod, "print_startup_selfcheck", lambda: calls.append("selfcheck"))
    monkeypatch.setattr(main_mod, "warn_if_open", lambda: calls.append("auth_warning"))

    with TestClient(main_mod.create_app()) as client:
        assert client.get("/health").status_code == 200

    assert calls == ["utf8", "resume", "selfcheck", "auth_warning"]


def test_create_app_registers_lifespan_not_on_event():
    """避免未來又退回 deprecated @app.on_event startup handler。"""
    app = main_mod.create_app()
    # FastAPI 會把主 app 與 included routers 的 lifespan 包成 merged context，
    # 因此不以 function identity 判斷；第一個測試已直接證明主 lifespan 有執行。
    assert app.router.on_startup == []
    assert app.router.on_shutdown == []
