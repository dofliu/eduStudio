"""iter 72: /themes 主題預覽 endpoint tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


class TestListThemes:
    def test_list_returns_15_themes(self, client):
        r = client.get("/themes")
        assert r.status_code == 200
        body = r.json()
        assert "themes" in body
        assert len(body["themes"]) == 15

    def test_themes_have_id_and_label(self, client):
        r = client.get("/themes")
        for theme in r.json()["themes"]:
            assert "id" in theme
            assert "label" in theme
            assert theme["id"]
            assert theme["label"]

    def test_forest_first(self, client):
        """forest 是預設主題, 該排第一."""
        r = client.get("/themes")
        assert r.json()["themes"][0]["id"] == "forest"


class TestSlidePreview:
    def test_forest_slide_preview(self, client):
        r = client.get("/themes/preview/forest")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        # PNG magic header
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        # 不該太小 (640x360 PNG 至少 ~10KB)
        assert len(r.content) > 5000

    def test_brutalist_slide_preview(self, client):
        """野獸派主題 layout 跟 forest 截然不同, 也該能 render."""
        r = client.get("/themes/preview/dof-brutalist")
        assert r.status_code == 200
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_unknown_theme_404(self, client):
        r = client.get("/themes/preview/nonexistent")
        assert r.status_code == 404

    def test_cache_control_header(self, client):
        r = client.get("/themes/preview/forest")
        assert "Cache-Control" in r.headers


class TestCoverPreview:
    def test_forest_cover_preview(self, client):
        r = client.get("/themes/preview/forest/cover")
        assert r.status_code == 200
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_unknown_theme_cover_404(self, client):
        r = client.get("/themes/preview/nonexistent/cover")
        assert r.status_code == 404


class TestPreviewCache:
    """同一 theme 第二次請求該命中 cache (回相同 bytes)."""

    def test_repeat_request_same_bytes(self, client):
        r1 = client.get("/themes/preview/forest")
        r2 = client.get("/themes/preview/forest")
        assert r1.content == r2.content


class TestAllThemesPreview:
    """確認 15 個主題每個都能 render 不 raise (上下游 dispatch 都對齊)."""

    ALL_THEME_IDS = [
        "forest", "navy", "frieren", "naruto", "journal",
        "dof-editorial", "dof-podium", "dof-notebook", "dof-shinobi", "dof-elven",
        "dof-zine", "dof-arcade", "dof-risograph", "dof-supergraphic", "dof-brutalist",
    ]

    @pytest.mark.parametrize("theme_id", ALL_THEME_IDS)
    def test_slide_preview_works(self, client, theme_id):
        r = client.get(f"/themes/preview/{theme_id}")
        assert r.status_code == 200, f"{theme_id} slide preview failed"
        assert len(r.content) > 5000

    @pytest.mark.parametrize("theme_id", ALL_THEME_IDS)
    def test_cover_preview_works(self, client, theme_id):
        r = client.get(f"/themes/preview/{theme_id}/cover")
        assert r.status_code == 200, f"{theme_id} cover preview failed"
        assert len(r.content) > 5000
