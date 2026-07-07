"""core.google_photos — Photos Picker 薄層測試 (fake session, 不需真 OAuth)。"""
from __future__ import annotations

import pytest

from core import google_photos as gp


class _Resp:
    def __init__(self, payload=None, content=b""):
        self._payload = payload or {}
        self.content = content

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    """依 URL/params 回傳程式化 response, 並記錄呼叫。"""

    def __init__(self, *, session=None, media_pages=None, downloads=None):
        self._session = session or {"id": "sess1", "pickerUri": "https://photos.google.com/pick/x",
                                    "mediaItemsSet": False}
        self._media_pages = media_pages or []
        self._downloads = downloads or {}
        self.calls = []

    def post(self, url, json=None):
        self.calls.append(("POST", url))
        return _Resp(self._session)

    def get(self, url, params=None):
        self.calls.append(("GET", url, params))
        if url.endswith("/mediaItems"):
            token = (params or {}).get("pageToken")
            idx = 0 if not token else int(token)
            return _Resp(self._media_pages[idx])
        if "/sessions/" in url:
            return _Resp({**self._session, "mediaItemsSet": True})
        # 下載 (baseUrl=d)
        return _Resp(content=self._downloads.get(url, b"\xff\xd8imgbytes"))


class TestSession:
    def test_create_session_returns_picker_uri(self):
        s = _FakeSession()
        out = gp.create_session(session=s)
        assert out["pickerUri"].startswith("https://")
        assert ("POST", f"{gp._API_ROOT}/sessions") in s.calls

    def test_get_session(self):
        s = _FakeSession()
        assert gp.get_session("sess1", session=s)["mediaItemsSet"] is True


class TestListAndDownload:
    def test_list_media_items_paginates(self):
        pages = [
            {"mediaItems": [{"id": "a"}, {"id": "b"}], "nextPageToken": "1"},
            {"mediaItems": [{"id": "c"}]},
        ]
        s = _FakeSession(media_pages=pages)
        items = gp.list_media_items("sess1", session=s)
        assert [i["id"] for i in items] == ["a", "b", "c"]

    def test_download_selected_filters_video_and_saves_images(self, tmp_path):
        pages = [{
            "mediaItems": [
                {"id": "img1", "mediaFile": {"baseUrl": "https://b/img1", "mimeType": "image/jpeg"}},
                {"id": "vid1", "mediaFile": {"baseUrl": "https://b/vid1", "mimeType": "video/mp4"}},
                {"id": "img2", "mediaFile": {"baseUrl": "https://b/img2", "mimeType": "image/png"}},
            ],
        }]
        s = _FakeSession(media_pages=pages)
        paths = gp.download_selected("sess1", tmp_path, session=s)
        # 只下載 2 張圖 (影片跳過)
        assert len(paths) == 2
        assert all(p.exists() and p.stat().st_size > 0 for p in paths)
        assert paths[0].suffix == ".jpg" and paths[1].suffix == ".png"

    def test_download_url_appends_d(self):
        assert gp._download_url("https://b/img1").endswith("=d")


class TestOAuthGate:
    def test_missing_token_raises_bootstrap(self, tmp_path, monkeypatch):
        # token 檔不存在 + 非互動 → OAuthBootstrapRequired
        monkeypatch.setattr(gp, "PHOTOS_TOKEN_PATH", tmp_path / "nope.json")
        with pytest.raises(gp.OAuthBootstrapRequired):
            gp.get_photos_credentials(allow_interactive=False)
