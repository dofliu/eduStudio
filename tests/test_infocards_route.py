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
from core.infocards.schemas import ComicData, InfographicData, PresentationData
from core.infocards.share_store import ShareStore
from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    # share 用 tmp store
    monkeypatch.setattr(ic, "get_share_store", lambda: ShareStore(db_path=str(tmp_path / "s.db")))
    # 視覺素材庫用 tmp db（避免自動保存污染真實 db）
    import core.infocards.visual_library as vl
    store = vl.VisualLibraryStore(db_path=str(tmp_path / "vlib.db"))
    monkeypatch.setattr(vl, "get_visual_library", lambda: store)
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
        assert "presentation" in body["implemented"]


class TestGenerate:
    def test_comic_mode(self, client, monkeypatch):
        monkeypatch.setattr(ic.comic_service, "generate_comic_script",
                            lambda text, style, custom="", panels=4, model=None, files=None: _FAKE_COMIC)
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
                            lambda text, style, custom="", aspect_ratio="vertical", model=None, files=None: fake)
        monkeypatch.setattr(ic.infographic_service, "generate_infographic_images",
                            lambda data, model=None, custom="": data)
        r = client.post("/api/generate", json={"mode": "infographic", "text": "牛頓", "style": "academic"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True and body["type"] == "infographic"
        assert body["data"]["mainTitle"] == "圖卡"

    def test_outline_mode(self, client, monkeypatch):
        from core.infocards.schemas import PresentationOutline

        fake = [PresentationOutline.model_validate({
            "id": "outline_0", "label": "方案 A", "approach": "故事線",
            "suggestedTheme": "navy", "suggestedTypography": "modern",
            "mainTitle": "簡報", "subtitle": "副標", "estimatedImageCount": 2,
            "slides": [{"layout": "title_cover", "title": "封面", "summary": "x"}],
        })]
        monkeypatch.setattr(ic.presentation_service, "generate_presentation_outlines",
                            lambda text, style, **kw: fake)
        r = client.post("/api/generate", json={"mode": "outline", "text": "t", "style": "navy"})
        assert r.status_code == 200
        body = r.json()
        assert body["type"] == "outline"
        assert body["data"]["outlines"][0]["label"] == "方案 A"

    def test_presentation_mode(self, client, monkeypatch):
        fake = PresentationData.model_validate({
            "mainTitle": "簡報", "subtitle": "副標", "themeColor": "#1e3a5f", "style": "navy",
            "slides": [{"id": "s1", "layout": "title_cover", "title": "封面", "content": "",
                        "speakerNotes": "開場"}],
        })
        monkeypatch.setattr(ic.presentation_service, "generate_presentation_data",
                            lambda text, style, **kw: fake)
        monkeypatch.setattr(ic.presentation_service, "generate_presentation_images",
                            lambda data, **kw: data)
        r = client.post("/api/generate", json={"mode": "presentation", "text": "t", "style": "navy"})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True and body["type"] == "presentation"
        assert body["data"]["mainTitle"] == "簡報"

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


class TestVisualLibrary:
    """成功生成自動存入素材庫 + 清單/取單筆/刪除（#6）。"""

    def test_poster_autosaves_and_round_trip(self, client, monkeypatch):
        monkeypatch.setattr(
            ic.poster_service, "generate_poster",
            lambda text, style, **kw: {"imageUrl": "data:image/png;base64,POSTER", "prompt": "P"})
        # 生成前素材庫空
        assert client.get("/api/visual-library").json()["items"] == []
        client.post("/api/generate", json={"mode": "poster", "text": "牛頓定律\n第二行", "style": "navy"})
        items = client.get("/api/visual-library").json()["items"]
        assert len(items) == 1
        it = items[0]
        assert it["type"] == "poster"
        assert it["title"] == "牛頓定律"          # 取內容第一行
        assert it["thumb"] == "data:image/png;base64,POSTER"
        # 取單筆含完整 data
        full = client.get(f"/api/visual-library/{it['id']}").json()
        assert full["data"]["imageUrl"] == "data:image/png;base64,POSTER"
        # 刪除
        assert client.delete(f"/api/visual-library/{it['id']}").json()["deleted"] is True
        assert client.get("/api/visual-library").json()["items"] == []

    def test_blank_poster_not_saved(self, client, monkeypatch):
        monkeypatch.setattr(ic.poster_service, "generate_poster",
                            lambda text, style, **kw: {"imageUrl": "", "prompt": "P"})
        client.post("/api/generate", json={"mode": "poster", "text": "t", "style": "navy"})
        assert client.get("/api/visual-library").json()["items"] == []

    def test_presentation_autosaves_with_title(self, client, monkeypatch):
        fake = PresentationData.model_validate({
            "mainTitle": "動量守恆", "subtitle": "副標", "themeColor": "#1e3a5f", "style": "navy",
            "slides": [{"id": "s1", "layout": "title_cover", "title": "封面", "content": "",
                        "speakerNotes": "開場", "imageUrl": "data:image/png;base64,SLIDE"}],
        })
        monkeypatch.setattr(ic.presentation_service, "generate_presentation_data",
                            lambda text, style, **kw: fake)
        monkeypatch.setattr(ic.presentation_service, "generate_presentation_images",
                            lambda data, **kw: data)
        client.post("/api/generate", json={"mode": "presentation", "text": "x", "style": "navy"})
        items = client.get("/api/visual-library").json()["items"]
        assert len(items) == 1
        assert items[0]["type"] == "presentation" and items[0]["title"] == "動量守恆"
        assert items[0]["thumb"] == "data:image/png;base64,SLIDE"   # 首張有圖 slide

    def test_get_missing_404(self, client):
        assert client.get("/api/visual-library/nope").status_code == 404
