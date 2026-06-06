"""core/settings + /settings 端點 + get_gemini_api_key 覆寫測試（設定頁）。

每測試把 ES_SETTINGS_PATH 指 tmp 隔離，不碰真實 settings.json。
"""
from __future__ import annotations

import pytest

from core import config


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    p = tmp_path / "settings.json"
    monkeypatch.setenv("ES_SETTINGS_PATH", str(p))
    return p


class TestSettingsStore:
    def test_update_get_roundtrip(self, settings_path):
        from core import settings as st
        st.update({"text_model": "gemini-2.5-pro", "brand_speaker": "劉老師"})
        assert st.get_setting("text_model") == "gemini-2.5-pro"
        assert st.get_setting("brand_speaker") == "劉老師"
        assert st.get_setting("missing") is None

    def test_empty_string_clears(self, settings_path):
        from core import settings as st
        st.update({"brand_org": "NCUT"})
        st.update({"brand_org": ""})
        assert st.get_setting("brand_org") is None

    def test_unknown_field_ignored(self, settings_path):
        from core import settings as st
        st.update({"evil": "x", "text_model": "m"})
        assert st.get_setting("evil") is None and st.get_setting("text_model") == "m"

    def test_public_view_masks_api_key(self, settings_path):
        from core import settings as st
        st.update({"gemini_api_key": "secret-key-123"})
        view = st.public_view()
        assert view["has_gemini_api_key"] is True
        assert "secret-key-123" not in str(view)   # 明文不外洩


class TestApiKeyOverride:
    def test_settings_overrides_env(self, settings_path, monkeypatch):
        from core import settings as st
        monkeypatch.setenv("GEMINI_API_KEY", "from-env")
        assert config.get_gemini_api_key() == "from-env"
        st.update({"gemini_api_key": "from-settings"})
        assert config.get_gemini_api_key() == "from-settings"   # 設定頁優先

    def test_falls_back_to_env(self, settings_path, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "only-env")
        assert config.get_gemini_api_key() == "only-env"


class TestSettingsRoute:
    @pytest.fixture
    def client(self, settings_path):
        pytest.importorskip("fastapi.testclient")
        pytest.importorskip("multipart")
        from fastapi.testclient import TestClient
        from server.main import create_app
        with TestClient(create_app()) as c:
            yield c

    def test_get_then_post(self, client):
        r = client.get("/settings")
        assert r.status_code == 200
        body = r.json()
        assert body["has_gemini_api_key"] is False
        assert isinstance(body["text_models"], list) and body["text_models"]
        # 寫入
        r2 = client.post("/settings", json={"text_model": "gemini-2.5-pro", "brand_speaker": "劉老師", "gemini_api_key": "SECRET_XYZ_789"})
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2["text_model"] == "gemini-2.5-pro"
        assert b2["brand_speaker"] == "劉老師"
        assert b2["has_gemini_api_key"] is True
        assert "gemini_api_key" not in b2          # 不回明文欄位
        assert "SECRET_XYZ_789" not in str(b2)     # 金鑰值不外洩
