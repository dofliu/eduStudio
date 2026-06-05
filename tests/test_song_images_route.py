"""GET /jobs/{id}/images/{name} — song 逐段生圖預覽 (SONG M3e-3a).

ingest_song (M3b) 把逐段圖複製到 jobs/<id>/images/, segment.image_path 改寫成
"images/<name>". SongReviewPane (M3e-3) 預覽圖時剝掉前綴傳 basename 給這條 route。
純 fastapi route 測, 不打 Gemini / 不真渲染。鏡像 test_figures_route 的 download 段。
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

from server.jobs import JobStore, get_default_store
from server.main import create_app
from server.schemas import CreateJobRequest, JobOptions, JobSource, SourceType


@pytest.fixture
def client(tmp_path):
    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def _create_song_job(store: JobStore, images: list[tuple[str, bytes]] | None = None) -> str:
    """建 song job + 寫 images/ 內逐段圖檔."""
    rec = store.create(CreateJobRequest(
        source_type=SourceType.SONG,
        source=JobSource(path="/tmp/fake_song.json"),
        options=JobOptions(),
    ))
    if images:
        img_dir = store.job_dir(rec.id) / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        for name, content in images:
            (img_dir / name).write_bytes(content)
    return rec.id


class TestDownloadSongImage:
    def test_serves_png(self, client):
        c, store = client
        png_data = b"\x89PNG\r\n\x1a\n seg image content"
        jid = _create_song_job(store, images=[("seg_s1.png", png_data)])
        resp = c.get(f"/jobs/{jid}/images/seg_s1.png")
        assert resp.status_code == 200
        assert resp.content == png_data
        assert resp.headers["content-type"].startswith("image/png")

    def test_404_for_missing_image_file(self, client):
        """檔不存在 (e.g. 該段尚未生圖) → 404, 前端據此退純色提示."""
        c, store = client
        jid = _create_song_job(store)
        resp = c.get(f"/jobs/{jid}/images/seg_nope.png")
        assert resp.status_code == 404

    def test_404_for_missing_job(self, client):
        c, _ = client
        resp = c.get("/jobs/nonexistent/images/seg_s1.png")
        assert resp.status_code == 404

    def test_dotdot_in_name_returns_400(self, client):
        """name 含 `..` 該 400 — 跟 figures endpoint 同 path-traversal 防呆."""
        c, store = client
        jid = _create_song_job(store)
        resp = c.get(f"/jobs/{jid}/images/..foo.png")
        assert resp.status_code == 400

    def test_forward_slash_in_name_returns_400(self, client):
        """name 含 `/` (URL encoded) 該被擋, 不該洩漏 images/ 外的檔."""
        c, store = client
        jid = _create_song_job(store)
        resp = c.get(f"/jobs/{jid}/images/sub%2Ffoo.png")
        assert resp.status_code in (400, 404, 405)

    def test_directory_target_returns_404(self, client):
        """target 是目錄不是檔 → 404, 不該 500 也不該回 dir listing."""
        c, store = client
        jid = _create_song_job(store)
        img_dir = store.job_dir(jid) / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "sub_dir").mkdir()
        resp = c.get(f"/jobs/{jid}/images/sub_dir")
        assert resp.status_code == 404
