"""iter 72: /themes 主題預覽 endpoint tests."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def clear_preview_cache():
    """iter 122: 確保 cache 隔離 — 測試前後都清空 _PREVIEW_CACHE.

    _PREVIEW_CACHE 是 module-level dict, 跨 test 會累積 (前面
    TestAllThemesPreview 已塞滿 15 主題 × 2 kind = 30 entry). 對 cache hit /
    miss / failure 行為的精準測試需先確保乾淨初始狀態.
    """
    from server.routes.themes import _PREVIEW_CACHE
    _PREVIEW_CACHE.clear()
    yield
    _PREVIEW_CACHE.clear()


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


class TestCacheIsolation:
    """iter 122: 鎖 _PREVIEW_CACHE 命中行為 — 同 (theme, kind) 二次不重算,
    跨 theme/kind 不互污染, cache 活 module lifecycle (跨 TestClient).
    """

    def test_second_call_skips_render(self, client, monkeypatch, clear_preview_cache):
        """同 theme+kind 第二次 call 該回 cache, 不再 call render_frame.

        既有 test_repeat_request_same_bytes 只驗 bytes 一致 (render_frame
        determinism 也會過). 這條用 call counter 真正鎖 cache short-circuit.
        """
        import pipeline
        call_count = {"n": 0}
        real_render = pipeline.render_frame

        def counting_render(*args, **kwargs):
            call_count["n"] += 1
            return real_render(*args, **kwargs)

        monkeypatch.setattr(pipeline, "render_frame", counting_render)

        r1 = client.get("/themes/preview/forest")
        assert r1.status_code == 200
        assert call_count["n"] == 1

        r2 = client.get("/themes/preview/forest")
        assert r2.status_code == 200
        # cache 命中, render_frame 不該再被叫
        assert call_count["n"] == 1
        assert r1.content == r2.content

    def test_cache_keyed_by_theme(self, client, clear_preview_cache):
        """不同 theme 的 cache 互不污染 (key tuple 含 theme)."""
        r1 = client.get("/themes/preview/forest")
        r2 = client.get("/themes/preview/navy")
        assert r1.status_code == 200
        assert r2.status_code == 200
        # forest vs navy layout 不同 → bytes 該不同
        assert r1.content != r2.content

        from server.routes.themes import _PREVIEW_CACHE
        assert ("forest", "slide") in _PREVIEW_CACHE
        assert ("navy", "slide") in _PREVIEW_CACHE

    def test_cache_keyed_by_kind(self, client, clear_preview_cache):
        """同 theme 的 slide vs cover cache 分開存 (key tuple 含 kind)."""
        r_slide = client.get("/themes/preview/forest")
        r_cover = client.get("/themes/preview/forest/cover")
        assert r_slide.status_code == 200
        assert r_cover.status_code == 200
        # cover layout 跟 slide layout 不同 → bytes 該不同
        assert r_slide.content != r_cover.content

        from server.routes.themes import _PREVIEW_CACHE
        assert ("forest", "slide") in _PREVIEW_CACHE
        assert ("forest", "cover") in _PREVIEW_CACHE

    def test_cache_persists_across_clients(self, clear_preview_cache):
        """cache 活在 module-level, 不同 TestClient (新 create_app) 該共用.

        確保 cache 不會被「每 request 重起 app」誤判 — 反例如果有人把
        cache 改成 app.state.* 就會破這條.
        """
        from server.routes.themes import _PREVIEW_CACHE

        c1 = TestClient(create_app())
        r1 = c1.get("/themes/preview/forest")
        assert r1.status_code == 200
        assert ("forest", "slide") in _PREVIEW_CACHE
        cache_size = len(_PREVIEW_CACHE)

        c2 = TestClient(create_app())
        r2 = c2.get("/themes/preview/forest")
        assert r2.status_code == 200
        # c2 該命中 cache, 不該多塞 entry
        assert len(_PREVIEW_CACHE) == cache_size
        assert r2.content == r1.content


class TestRenderFailureHandling:
    """iter 122: render_frame raise → HTTPException 500 + 失敗不污染 cache."""

    def test_render_exception_returns_500(self, client, monkeypatch, clear_preview_cache):
        """pipeline.render_frame raise → endpoint 該回 500 不該炸 unhandled."""
        import pipeline

        def failing_render(*args, **kwargs):
            raise RuntimeError("intentional render failure")

        monkeypatch.setattr(pipeline, "render_frame", failing_render)

        r = client.get("/themes/preview/forest")
        assert r.status_code == 500
        assert "render failed" in r.json()["detail"]

    def test_render_failure_not_cached(self, client, monkeypatch, clear_preview_cache):
        """失敗的 render 不該塞 cache → 下次 retry 該重試, 不該回 cached 500."""
        from server.routes.themes import _PREVIEW_CACHE
        import pipeline

        call_count = {"n": 0}
        real_render = pipeline.render_frame

        def flaky_render(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("first attempt fails")
            return real_render(*args, **kwargs)

        monkeypatch.setattr(pipeline, "render_frame", flaky_render)

        r1 = client.get("/themes/preview/forest")
        assert r1.status_code == 500
        # 失敗該不污染 cache
        assert ("forest", "slide") not in _PREVIEW_CACHE

        # 第二次 retry 該過 (re-enter _render_preview, miss cache, 真叫 render)
        r2 = client.get("/themes/preview/forest")
        assert r2.status_code == 200
        assert ("forest", "slide") in _PREVIEW_CACHE


class TestRenderPreviewUnit:
    """iter 122: _render_preview private helper 邊角."""

    def test_unknown_kind_raises_value_error(self, clear_preview_cache):
        """defensive: 未來呼叫者傳怪 kind 該 ValueError 不該 silently 失敗.

        type hint 是 Literal["slide", "cover"] 擋編譯期, runtime 仍可繞
        (Literal 不檢驗); else branch 是最後一道防線, 鎖住才不會被無聲拿掉.
        """
        from server.routes.themes import _render_preview
        with pytest.raises(ValueError, match="unknown kind"):
            _render_preview("forest", "invalid")  # type: ignore[arg-type]

    def test_thumbnail_dimensions(self, client, clear_preview_cache):
        """PNG 真的縮到 640×360 (LANCZOS resize 寫死值, 確保不被改掉)."""
        from io import BytesIO
        from PIL import Image
        r = client.get("/themes/preview/forest")
        assert r.status_code == 200
        img = Image.open(BytesIO(r.content))
        assert img.size == (640, 360)


class TestListThemesContract:
    """iter 123: GET /themes 契約鎖 — order / unique / URL slug / 跨來源同源.

    THEME_LIST 在 backend 寫死 15 主題順序, frontend ProposalsList.tsx
    THEME_OPTIONS 寫死同樣順序 (lines 24-38). 兩處對應的 theme idx 該一致 —
    若有人偷改 backend 順序忘改 frontend, gallery 顯示會跟用戶選擇的 idx
    錯位, 結果是「我選的是 forest, render 出來是 navy」這類靜默 bug.
    """

    EXPECTED_THEME_ID_ORDER = [
        "forest", "navy", "frieren", "naruto", "journal",
        "dof-editorial", "dof-podium", "dof-notebook", "dof-shinobi", "dof-elven",
        "dof-zine", "dof-arcade", "dof-risograph", "dof-supergraphic", "dof-brutalist",
    ]

    def test_full_id_order_locked(self, client):
        """完整 15 id 順序寫死鎖 — 跟 frontend ProposalsList.tsx 對齊."""
        r = client.get("/themes")
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()["themes"]]
        assert ids == self.EXPECTED_THEME_ID_ORDER

    def test_no_duplicate_ids(self, client):
        """ID 唯一性 — 複製貼上 typo 會造成 theme dispatch 拿到第一個命中, 不是預期的."""
        r = client.get("/themes")
        ids = [t["id"] for t in r.json()["themes"]]
        assert len(ids) == len(set(ids))

    def test_ids_are_url_safe_slugs(self, client):
        """ID 必須是 URL-safe slug — 只 [a-z0-9-], 不含空白 / 大寫 / dot.

        ID 直接拼進 /themes/preview/{theme} path segment, 含空白或 dot 會被
        URL encode / 觸發 path traversal 防護 / 跟其他 endpoint route 衝突.
        """
        import re
        slug_pattern = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
        r = client.get("/themes")
        for t in r.json()["themes"]:
            tid = t["id"]
            assert slug_pattern.match(tid), f"{tid!r} 不是合法 URL slug"

    def test_labels_are_non_empty_strings(self, client):
        """label 該是 non-empty str — None / 空字串 / 純空白都該擋下.

        前端 gallery 顯示 label, 空 label 會出現空白格子, UX 異常.
        """
        r = client.get("/themes")
        for t in r.json()["themes"]:
            label = t["label"]
            assert isinstance(label, str)
            assert label
            assert label.strip()

    def test_list_matches_all_themes_preview_param(self, client):
        """list_themes 回的 id 集合 == TestAllThemesPreview.ALL_THEME_IDS.

        兩處 hardcode 列表 (THEME_LIST 跟 ALL_THEME_IDS) 是 backend 內部
        兩個來源, 改一邊忘改另一邊會讓「list endpoint 列了但 preview 跑不了」
        或「preview 跑得了但 list 沒列」這種裂縫上線. 這條鎖兩處同源.
        """
        r = client.get("/themes")
        list_ids = sorted(t["id"] for t in r.json()["themes"])
        param_ids = sorted(TestAllThemesPreview.ALL_THEME_IDS)
        assert list_ids == param_ids

    def test_theme_list_module_constant_matches_endpoint(self, client):
        """THEME_LIST module-level constant 跟 list_themes endpoint 該對齊.

        鎖 list_themes() 沒被某個 refactor 改成從別處讀 (例改用 settings.toml
        或硬 hardcode 在 handler 內), 確保 THEME_LIST 仍是 single source of truth.
        """
        from server.routes.themes import THEME_LIST
        r = client.get("/themes")
        endpoint_ids = [t["id"] for t in r.json()["themes"]]
        endpoint_labels = [t["label"] for t in r.json()["themes"]]
        const_ids = [tid for tid, _ in THEME_LIST]
        const_labels = [label for _, label in THEME_LIST]
        assert endpoint_ids == const_ids
        assert endpoint_labels == const_labels
