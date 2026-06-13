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


class TestModelRoles:
    """M-3：逐角色 model 覆寫（model_roles）持久化 + 清洗 + 對 resolve() 生效。"""

    def test_roundtrip_and_resolve(self, settings_path):
        from core import models
        from core import settings as st
        st.update({"model_roles": {"text.fast": "gemini-x", "image.pro": "img-y"}})
        assert st.get_setting("model_roles") == {"text.fast": "gemini-x", "image.pro": "img-y"}
        # 對 resolve() 最高優先生效
        assert models.resolve_id("text.fast") == "gemini-x"
        assert models.resolve_id("image.pro") == "img-y"
        # 未覆寫的角色仍回預設
        assert models.resolve_id("text.pro") == models.DEFAULTS["text.pro"][1]

    def test_unknown_role_and_empty_value_dropped(self, settings_path):
        from core import settings as st
        st.update({"model_roles": {"text.fast": "ok", "bogus.role": "x", "image.fast": "  "}})
        assert st.get_setting("model_roles") == {"text.fast": "ok"}

    def test_empty_dict_clears(self, settings_path):
        from core import settings as st
        st.update({"model_roles": {"text.fast": "ok"}})
        st.update({"model_roles": {}})
        assert st.get_setting("model_roles") is None

    def test_non_dict_ignored(self, settings_path):
        from core import settings as st
        st.update({"model_roles": "not-a-dict"})
        assert st.get_setting("model_roles") is None

    def test_public_view_exposes_model_roles(self, settings_path):
        from core import settings as st
        assert st.public_view()["model_roles"] == {}
        st.update({"model_roles": {"text.fast": "m"}})
        assert st.public_view()["model_roles"] == {"text.fast": "m"}

    # ---- F9-3c：巢狀 provider 覆寫（本機可插拔 ollama）持久化 + 清洗 ----

    def test_nested_provider_override_roundtrip_and_resolve(self, settings_path):
        from core import models
        from core import settings as st
        st.update({"model_roles": {"text.fast": {"provider": "ollama", "model": "translategemma"}}})
        # 非預設 provider → 保留巢狀形儲存
        assert st.get_setting("model_roles") == {
            "text.fast": {"provider": "ollama", "model": "translategemma"}
        }
        # 對 resolve() 生效（回 provider + model）
        assert models.resolve("text.fast") == ("ollama", "translategemma")

    def test_nested_default_provider_collapses_to_flat(self, settings_path):
        from core import settings as st
        # provider==預設 gemini → 收斂回扁平字串（與 legacy 儲存一致）
        st.update({"model_roles": {"text.pro": {"provider": "gemini", "model": "gemini-x"}}})
        assert st.get_setting("model_roles") == {"text.pro": "gemini-x"}

    def test_nested_unknown_provider_and_incomplete_dropped(self, settings_path):
        from core import settings as st
        st.update({"model_roles": {
            "text.fast": {"provider": "bogus", "model": "kept"},   # 未知 provider 忽略→扁平
            "text.pro": {"provider": "ollama"},                    # 缺 model → 丟棄
            "vision": {"provider": "ollama", "model": "  "},       # 空 model → 丟棄
        }})
        assert st.get_setting("model_roles") == {"text.fast": "kept"}


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


class TestModelOverride:
    def test_default_when_unset(self, settings_path):
        assert config.get_gemini_model() == config.GEMINI_MODEL

    def test_settings_overrides_model(self, settings_path):
        from core import settings as st
        st.update({"text_model": "gemini-2.5-pro"})
        assert config.get_gemini_model() == "gemini-2.5-pro"


class TestBrandOverride:
    def test_cover_speaker_org_url_from_settings(self, settings_path, monkeypatch):
        from core import settings as st
        # 無設定 → 預設
        monkeypatch.delenv("CLAUDE_COVER_SPEAKER", raising=False)
        assert config.get_cover_speaker() == config.DEFAULT_COVER_SPEAKER
        # 設定頁覆寫
        st.update({"brand_speaker": "劉瑞弘 教授", "brand_org": "NCUT", "brand_url": "doflab.cc"})
        assert config.get_cover_speaker() == "劉瑞弘 教授"
        assert config.get_cover_org() == "NCUT"
        assert config.get_outro_url() == "doflab.cc"

    def test_settings_beats_env(self, settings_path, monkeypatch):
        from core import settings as st
        monkeypatch.setenv("CLAUDE_COVER_SPEAKER", "from-env")
        assert config.get_cover_speaker() == "from-env"
        st.update({"brand_speaker": "from-settings"})
        assert config.get_cover_speaker() == "from-settings"   # 設定頁優先


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

    def test_roles_catalog_and_model_roles_write(self, client):
        # GET 回逐角色 catalog（單一真實來源 core.models.role_catalog）
        body = client.get("/settings").json()
        roles = {r["role"] for r in body["roles"]}
        assert {"text.fast", "text.pro", "vision", "image.fast", "image.pro"} == roles
        assert "tts" not in roles                  # tts 走獨立子系統，不在逐角色管理
        cat = next(r for r in body["roles"] if r["role"] == "image.pro")
        assert cat["kind"] == "image" and cat["default"] and cat["provider"] == "gemini"
        # provider 下拉清單（F9-3e）：可指派 provider，gemini 在前、tts 不在此
        prov_ids = [p["id"] for p in body["providers"]]
        assert prov_ids == ["gemini", "ollama"]
        assert all(p["label"] for p in body["providers"])
        # POST 寫入逐角色覆寫；未知角色被清洗掉
        r2 = client.post("/settings", json={"model_roles": {"text.fast": "gemini-z", "nope": "x"}})
        assert r2.status_code == 200
        assert r2.json()["model_roles"] == {"text.fast": "gemini-z"}
        # 巢狀 provider 覆寫（指本機）roundtrip 保留巢狀（F9-3c 收斂、F9-3e 前端寫入形）
        r3 = client.post("/settings", json={"model_roles": {"text.fast": {"provider": "ollama", "model": "translategemma"}}})
        assert r3.status_code == 200
        assert r3.json()["model_roles"] == {"text.fast": {"provider": "ollama", "model": "translategemma"}}
