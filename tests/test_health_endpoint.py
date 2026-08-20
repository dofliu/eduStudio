"""GET /health 加強版 (iter 36) — 鎖 response shape 給 monitoring + onboarding 用。

擔心未來改 endpoint 不小心拿掉某個 key, 監控工具 / docker healthcheck 會 silent
fail. 這支 lock 住目前 response 結構。
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server 內 upload route 需要")

from fastapi.testclient import TestClient

from server.jobs import JobStore, get_default_store
from server.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c


class TestHealthShape:
    """鎖 /health response keys — 拿掉任一個都該 fail 提醒 monitoring."""

    def test_basic_status_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "autoSolverVideo"
        assert isinstance(data["ui_built"], bool)

    def test_diagnostic_keys_present(self, client):
        """iter 36 新增的 setup diagnostic keys 都該回。"""
        resp = client.get("/health")
        data = resp.json()

        expected_keys = {
            "gemini_api_key_set",
            "tts_config_exists",
            "pipeline_config_exists",
            "proposals_json_exists",
            "jobs_count",
            "font_main_exists",
            "font_fallback_exists",
            "font_mono_exists",
            "whisper",
        }
        missing = expected_keys - set(data.keys())
        assert not missing, f"/health 缺診斷欄位: {missing}"
        assert set(data["whisper"]) >= {"model", "cached", "device_preference"}

    def test_jobs_count_is_int(self, client):
        resp = client.get("/health")
        assert isinstance(resp.json()["jobs_count"], int)

    def test_bool_diagnostics_are_bool(self, client):
        """所有「_exists / _set」結尾的 key 都該是 bool, 不是 truthy/falsy 雜訊."""
        resp = client.get("/health")
        data = resp.json()
        bool_keys = [
            "ui_built", "gemini_api_key_set",
            "tts_config_exists", "pipeline_config_exists", "proposals_json_exists",
            "font_main_exists", "font_fallback_exists", "font_mono_exists",
        ]
        for k in bool_keys:
            assert isinstance(data[k], bool), f"{k} 不是 bool: {type(data[k])}"

    def test_gemini_key_reflects_env(self, client, monkeypatch):
        """GEMINI_API_KEY 設了 → True, 沒設 → False."""
        monkeypatch.setenv("GEMINI_API_KEY", "AIzaTest")
        assert client.get("/health").json()["gemini_api_key_set"] is True

        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert client.get("/health").json()["gemini_api_key_set"] is False

    def test_jobs_count_reflects_store(self, client, tmp_path):
        """jobs_count 該對應 dependency-overridden store, 不是 default."""
        # fixture 的 store 是空 tmp_path, 應該 0
        data = client.get("/health").json()
        assert data["jobs_count"] == 0
