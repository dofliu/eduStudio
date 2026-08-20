"""tools/check_models.py 測試 — 純 offline，不呼叫 Gemini（API 端全用 fake 注入）。

鎖契約：
1. collect_configured_models 蒐到角色登錄表全部 gemini 角色 + 設定頁下拉清單，依 id 去重排序，
   且設定頁覆寫（model_roles）會透過 resolve 進到蒐集結果。
2. tts 等非 gemini provider 不被蒐集（不是 models.list 能驗的東西）。
3. evaluate 正確分辨「在 API / 不在 API」，並正規化 ``models/`` 前綴。
4. fetch_available_model_ids 接受注入 client、解析 name/id、去前綴。
5. main 在缺金鑰時 exit 2、全綠 exit 0、有缺 exit 1。
"""
import sys
from pathlib import Path

import pytest

# tools/ 不是 package；比照 test_gen_icon_svgs.py 掛 tools 目錄上 path 當 top-level module。
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.append(str(_TOOLS_DIR))

import check_models as cm  # noqa: E402
from core import models  # noqa: E402


class _FakeModel:
    def __init__(self, name):
        self.name = name


class _FakeClient:
    def __init__(self, names):
        self._names = names

    class _Models:
        def __init__(self, names):
            self._names = names

        def list(self):
            return [_FakeModel(n) for n in self._names]

    @property
    def models(self):
        return self._Models(self._names)


class TestNormalize:
    def test_strips_models_prefix(self):
        assert cm._normalize("models/gemini-3.5-flash") == "gemini-3.5-flash"

    def test_bare_id_unchanged(self):
        assert cm._normalize("gemini-3.5-flash") == "gemini-3.5-flash"

    def test_whitespace_and_empty(self):
        assert cm._normalize("  gemini-x  ") == "gemini-x"
        assert cm._normalize("") == ""
        assert cm._normalize(None) == ""


class TestCollect:
    def test_covers_role_registry_gemini_defaults(self):
        ids = {e["id"] for e in cm.collect_configured_models()}
        # 角色登錄表預設的 gemini id 都要在。
        for role in models.all_roles():
            provider, mid = models.resolve(role)
            if provider == models.PROVIDER_GEMINI:
                assert mid in ids

    def test_excludes_tts_non_gemini(self):
        # tts 預設 provider 是 edge → 其 model_id（"edge"）不該被蒐集。
        ids = {e["id"] for e in cm.collect_configured_models()}
        assert "edge" not in ids

    def test_includes_dropdown_catalog(self):
        from core.infocards import models as im
        ids = {e["id"] for e in cm.collect_configured_models()}
        catalog = (
            list(im.TEXT_MODELS.values())
            + list(im.IMAGE_MODELS.values())
            + list(im.SPECIALIZED_MODELS.values())
        )
        for spec in catalog:
            assert spec["id"] in ids

    def test_sorted_and_deduped(self):
        entries = cm.collect_configured_models()
        out_ids = [e["id"] for e in entries]
        assert out_ids == sorted(out_ids)
        assert len(out_ids) == len(set(out_ids)), "id 應去重"

    def test_sources_aggregated_for_shared_id(self, tmp_path, monkeypatch):
        # gemini-3.6-flash 同時是多個角色（text.fast/vision）+ 下拉 flash → 多來源彙整。
        # 隔離使用者真實 settings.json；本測試鎖的是內建 registry，不應被本機選項覆寫。
        monkeypatch.setenv("ES_SETTINGS_PATH", str(tmp_path / "settings.json"))
        entries = {e["id"]: e for e in cm.collect_configured_models()}
        flash = entries.get("gemini-3.6-flash")
        assert flash is not None
        assert len(flash["sources"]) >= 2
        assert flash["sources"] == sorted(flash["sources"])

    def test_settings_override_flows_through_resolve(self, tmp_path, monkeypatch):
        # 設定頁 model_roles 覆寫某角色 → 蒐集結果應出現該覆寫 id。
        settings_file = tmp_path / "settings.json"
        monkeypatch.setenv("ES_SETTINGS_PATH", str(settings_file))
        from core.settings import update
        update({"model_roles": {"text.fast": "gemini-custom-override"}})
        ids = {e["id"] for e in cm.collect_configured_models()}
        assert "gemini-custom-override" in ids


class TestEvaluate:
    def test_marks_present_and_missing(self):
        configured = [
            {"id": "gemini-a", "sources": ["角色 text.fast"]},
            {"id": "gemini-missing", "sources": ["設定頁下拉 文字/flash"]},
        ]
        available = {"gemini-a", "gemini-b"}
        results = {r["id"]: r for r in cm.evaluate(configured, available)}
        assert results["gemini-a"]["ok"] is True
        assert results["gemini-missing"]["ok"] is False

    def test_normalizes_available_prefix(self):
        configured = [{"id": "gemini-a", "sources": ["s"]}]
        available = {"models/gemini-a"}  # API 帶前綴也算存在。
        assert cm.evaluate(configured, available)[0]["ok"] is True

    def test_preserves_order(self):
        configured = [
            {"id": "z", "sources": ["s"]},
            {"id": "a", "sources": ["s"]},
        ]
        assert [r["id"] for r in cm.evaluate(configured, {"z", "a"})] == ["z", "a"]


class TestFetch:
    def test_parses_injected_client(self):
        client = _FakeClient(["models/gemini-3.5-flash", "models/gemini-3-pro-image"])
        ids = cm.fetch_available_model_ids(client=client)
        assert ids == {"gemini-3.5-flash", "gemini-3-pro-image"}

    def test_no_key_raises(self, monkeypatch, tmp_path):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("ES_SETTINGS_PATH", str(tmp_path / "settings.json"))
        with pytest.raises(RuntimeError):
            cm.fetch_available_model_ids()


class TestMain:
    def test_exit_2_without_key(self, monkeypatch, tmp_path, capsys):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("ES_SETTINGS_PATH", str(tmp_path / "settings.json"))
        assert cm.main([]) == 2
        assert "model id" in capsys.readouterr().out

    def test_exit_0_all_present(self, monkeypatch):
        configured = cm.collect_configured_models()
        all_ids = {e["id"] for e in configured}
        monkeypatch.setattr(cm, "fetch_available_model_ids", lambda: set(all_ids))
        assert cm.main([]) == 0

    def test_exit_1_when_missing(self, monkeypatch):
        monkeypatch.setattr(cm, "fetch_available_model_ids", lambda: set())
        assert cm.main([]) == 1

    def test_json_output(self, monkeypatch, capsys):
        configured = cm.collect_configured_models()
        all_ids = {e["id"] for e in configured}
        monkeypatch.setattr(cm, "fetch_available_model_ids", lambda: set(all_ids))
        assert cm.main(["--json"]) == 0
        import json as _json
        parsed = _json.loads(capsys.readouterr().out)
        assert all("ok" in r for r in parsed)
