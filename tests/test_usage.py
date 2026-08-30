"""core/usage UsageStore + /api/usage 端點測試（成本面板真實統計）。

tmp db 隔離,不打真 Gemini。驗成本換算、彙總、各站分組、近期紀錄、端點形狀。
"""
from __future__ import annotations

import pytest

from core.usage import UsageStore, _image_cost, _text_cost
from core.infocards.models import IMAGE_MODELS


class TestCostCalc:
    def test_text_cost_scales_with_chars(self):
        c1 = _text_cost(1000, 1000)
        c2 = _text_cost(2000, 2000)
        assert c1 > 0 and abs(c2 - 2 * c1) < 1e-9

    def test_image_cost_by_model(self):
        assert _image_cost(IMAGE_MODELS["flash"]["id"]) == 0.003
        assert _image_cost(IMAGE_MODELS["pro"]["id"]) == 0.04
        # 2026-08-30: 未知 model 走 "default"(中等階價), 不再記 $0 造成假便宜
        assert _image_cost("unknown-model") == 0.003


class TestUsageStore:
    @pytest.fixture
    def store(self, tmp_path):
        return UsageStore(db_path=str(tmp_path / "u.db"))

    def test_record_and_summary(self, store):
        store.record_text("visual", 1000, 500, model="gemini-2.5-flash", ts="2026-06-06T00:00:00Z")
        store.record_text("language", 2000, 0, model="gemini-2.5-flash", ts="2026-06-06T00:01:00Z")
        store.record_image("visual", IMAGE_MODELS["flash"]["id"], ts="2026-06-06T00:02:00Z")
        s = store.summary()
        assert s["count"] == 3
        assert s["used"] > 0
        # 各站分組：visual 與 language 都有
        keys = {b["key"] for b in s["byStation"]}
        assert keys == {"visual", "language"}
        # visual = 文字 + 圖片成本
        visual = next(b for b in s["byStation"] if b["key"] == "visual")
        expected = _text_cost(1000, 500) + _image_cost(IMAGE_MODELS["flash"]["id"])
        assert abs(visual["amount"] - round(expected, 4)) < 1e-4

    def test_recent_newest_first(self, store):
        store.record_text("visual", 10, 10, ts="t1", label="first")
        store.record_text("visual", 10, 10, ts="t2", label="second")
        s = store.summary()
        assert s["recent"][0]["label"] == "second"  # 最新在前

    def test_empty_summary(self, store):
        s = store.summary()
        assert s["used"] == 0 and s["count"] == 0 and s["byStation"] == [] and s["recent"] == []

    def test_station_label_mapped(self, store):
        store.record_text("visual", 10, 10, ts="t")
        s = store.summary()
        assert s["byStation"][0]["label"] == "視覺"


class TestUsageEndpoint:
    def test_endpoint(self, tmp_path, monkeypatch):
        pytest.importorskip("fastapi.testclient")
        pytest.importorskip("multipart")
        from fastapi.testclient import TestClient

        import core.usage as usage_mod
        from server.main import create_app

        store = UsageStore(db_path=str(tmp_path / "u.db"))
        store.record_text("visual", 1000, 500, ts="t")
        monkeypatch.setattr(usage_mod, "get_usage_store", lambda: store)
        app = create_app()
        with TestClient(app) as c:
            r = c.get("/api/usage")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1 and body["used"] > 0
        assert body["budget"] == 30.0      # 預設月預算
        assert "byStation" in body and "recent" in body

    def test_budget_env_override(self, tmp_path, monkeypatch):
        pytest.importorskip("fastapi.testclient")
        pytest.importorskip("multipart")
        from fastapi.testclient import TestClient

        import core.usage as usage_mod
        from server.main import create_app

        store = UsageStore(db_path=str(tmp_path / "u.db"))
        monkeypatch.setattr(usage_mod, "get_usage_store", lambda: store)
        monkeypatch.setenv("EDUSTUDIO_MONTHLY_BUDGET", "75")
        app = create_app()
        with TestClient(app) as c:
            r = c.get("/api/usage")
        assert r.status_code == 200
        assert r.json()["budget"] == 75.0
