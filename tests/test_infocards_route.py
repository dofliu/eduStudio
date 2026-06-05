"""server/routes/infocards.py HTTP route 測試（Phase C-4）。

mock 生成服務（不打真 Gemini），share 用 tmp store。驗 /api/generate 三模式分流、
health、share round-trip。
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import server.routes.infocards as ic
from core.infocards.schemas import ComicData, InfographicData
from core.infocards.share_store import ShareStore
from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # share 用 tmp store
    monkeypatch.setattr(ic, "get_share_store", lambda: ShareStore(db_path=str(tmp_path / "s.db")))
    app = create_app()
    with TestClient(app) as c:
        yield c


_FAKE_COMIC = ComicData.model_validate({
    "title": "漫畫", "storySummary": "故事", "characterVisualBible": "角色", "style": "comic",
    "panels": [{"id": "panel_1", "panelNumber": 1, "description": "d", "dialogue": "hi",
                "cameraDetail": "特寫", "imagePrompt": "a cat"}],
})


class TestHealth:
    def test_health(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "comic" in body["implemented"] and "poster" in body["implemented"]
        assert "infographic" in body["implemented"]


class TestGenerate:
    def test_comic_mode(self, client, monkeypatch):
        monkeypatch.setattr(ic.comic_service, "generate_comic_script",
                            lambda text, style, custom="", panels=4, model=None: _FAKE_COMIC)
        monkeypatch.setattr(ic.comic_service, "generate_comic_images",
                            lambda data, model=None, custom="": data)
        r = client.post("/api/generate", json={"mode": "comic", "text": "向量", "style": "comic"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True and body["type"] == "comic"
        assert body["data"]["title"] == "漫畫"

    def test_poster_mode(self, client, monkeypatch):
        monkeypatch.setattr(
            ic.poster_service, "generate_poster",
            lambda text, style, **kw: {"imageUrl": "data:image/png;base64,X", "prompt": "P"})
        r = client.post("/api/generate", json={"mode": "poster", "text": "t", "style": "navy"})
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "poster" and body["imageUrl"] == "data:image/png;base64,X"

    def test_infographic_mode(self, client, monkeypatch):
        fake = InfographicData.model_validate({
            "mainTitle": "圖卡", "subtitle": "副標", "layout": "grid", "themeColor": "#111",
            "style": "academic", "conclusion": "結論",
            "sections": [{"id": "s1", "title": "t", "content": "c", "iconType": "info"}],
            "statistics": [{"id": "st1", "value": "1", "label": "x"}],
        })
        monkeypatch.setattr(ic.infographic_service, "generate_infographic_data",
                            lambda text, style, custom="", aspect_ratio="vertical", model=None: fake)
        monkeypatch.setattr(ic.infographic_service, "generate_infographic_images",
                            lambda data, model=None, custom="": data)
        r = client.post("/api/generate", json={"mode": "infographic", "text": "牛頓", "style": "academic"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True and body["type"] == "infographic"
        assert body["data"]["mainTitle"] == "圖卡"

    def test_presentation_not_implemented(self, client):
        r = client.post("/api/generate", json={"mode": "presentation", "text": "t"})
        assert r.status_code == 501

    def test_unknown_mode_400(self, client):
        r = client.post("/api/generate", json={"mode": "bogus", "text": "t"})
        assert r.status_code == 400


class TestShare:
    def test_share_round_trip(self, client):
        r = client.post("/api/share", json={"type": "poster", "title": "海報", "data": {"a": 1}})
        assert r.status_code == 201
        sid = r.json()["id"]
        assert r.json()["url"] == f"/api/share/{sid}"
        got = client.get(f"/api/share/{sid}")
        assert got.status_code == 200
        assert got.json()["data"] == {"a": 1}

    def test_share_missing_404(self, client):
        assert client.get("/api/share/nope").status_code == 404
