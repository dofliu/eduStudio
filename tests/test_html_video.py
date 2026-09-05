"""core.html_video + POST /upload/html + youtube_meta fallback 測試。

涵蓋:
- render_html_to_mp4 參數驗證 (duration / fps) 與 mock 渲染產出合法 MP4
- _resolve_source_url: 缺檔 raise / http(s) passthrough / 本機檔轉 file://
- _render_html_job: mock happy path → state DONE + mp4 artifact 註冊成功
- POST /upload/html: file/url 二擇一、duration 邊界、url scheme 驗證
- youtube_meta: 無 deck.json 的 html_animation 來源退化成檔名預填 (不 404)

mock=True 走 ffmpeg testsrc, 不需要瀏覽器; 沒 ffmpeg 的環境跳過相關案例。
"""
from __future__ import annotations

import asyncio
import shutil

import pytest

from core import html_video

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
_needs_ffmpeg = pytest.mark.skipif(not _HAS_FFMPEG, reason="需要 ffmpeg")


# ---------------- core.html_video ----------------

class TestRenderValidation:
    def test_duration_must_be_positive(self, tmp_path):
        with pytest.raises(ValueError):
            html_video.render_html_to_mp4("x.html", tmp_path / "o.mp4", duration=0)

    def test_fps_must_be_positive(self, tmp_path):
        with pytest.raises(ValueError):
            html_video.render_html_to_mp4("x.html", tmp_path / "o.mp4", duration=1, fps=0)


class TestResolveSourceUrl:
    def test_http_passthrough(self):
        assert html_video._resolve_source_url("https://e.com/a") == "https://e.com/a"

    def test_missing_local_file_raises(self):
        with pytest.raises(FileNotFoundError):
            html_video._resolve_source_url("/no/such/file.html")

    def test_local_file_to_file_uri(self, tmp_path):
        p = tmp_path / "a.html"
        p.write_text("<html></html>", encoding="utf-8")
        url = html_video._resolve_source_url(p)
        assert url.startswith("file://") and url.endswith("a.html")


@_needs_ffmpeg
class TestMockRender:
    def test_mock_produces_valid_mp4(self, tmp_path):
        out = tmp_path / "anim.mp4"
        html_video.render_html_to_mp4(
            "ignored.html", out, duration=1, fps=10, width=320, height=240, mock=True,
        )
        assert out.exists() and out.stat().st_size > 0
        # MP4 容器標誌 'ftyp' 應出現在檔頭附近
        assert b"ftyp" in out.read_bytes()[:64]


# ---------------- 背景 render job ----------------

@_needs_ffmpeg
class TestRenderHtmlJob:
    def test_mock_job_reaches_done_with_mp4_artifact(self, tmp_path, monkeypatch):
        import server.jobs as jobs_mod
        from server.jobs import JobStore
        from server.routes.uploads_html import _render_html_job
        from server.schemas import (
            CreateJobRequest, JobOptions, JobSource, JobState, SourceType,
        )

        # scan_artifacts 用 module-level JOBS_DIR 算相對路徑, root 須與之一致
        jobs_root = tmp_path / "jobs"
        monkeypatch.setattr(jobs_mod, "JOBS_DIR", jobs_root)
        store = JobStore(root=jobs_root)
        rec = store.create(CreateJobRequest(
            source_type=SourceType.HTML_ANIMATION,
            source=JobSource(url="https://e.com/a"),
            options=JobOptions(mock=True, require_review=False),
        ))
        mp4 = store.artifacts_dir(rec.id) / "anim.mp4"

        asyncio.run(_render_html_job(
            store, rec.id,
            source="https://e.com/a", mp4_path=mp4,
            duration=1, fps=10, width=320, height=240, mock=True,
        ))

        done = store.get(rec.id)
        assert done.state == JobState.DONE
        kinds = {(a.name, a.kind) for a in done.artifacts}
        assert ("anim.mp4", "mp4") in kinds


# ---------------- POST /upload/html ----------------

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="需要 python-multipart 才能測 Form/File 路由")

from fastapi.testclient import TestClient  # noqa: E402

from server.jobs import JobStore, get_default_store  # noqa: E402
from server.main import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    import server.jobs as jobs_mod
    # scan_artifacts 用 module-level JOBS_DIR 算相對路徑, root 須與之一致
    jobs_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", jobs_root)
    app = create_app()
    store = JobStore(root=jobs_root)
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


class TestUploadHtmlValidation:
    def test_both_file_and_url_rejected(self, client):
        c, _ = client
        resp = c.post(
            "/upload/html",
            files={"file": ("a.html", b"<html></html>", "text/html")},
            data={"url": "https://e.com", "duration": "1"},
        )
        assert resp.status_code == 400

    def test_neither_file_nor_url_rejected(self, client):
        c, _ = client
        resp = c.post("/upload/html", data={"duration": "1"})
        assert resp.status_code == 400

    def test_duration_out_of_range_rejected(self, client):
        c, _ = client
        resp = c.post(
            "/upload/html",
            data={"url": "https://e.com/a", "duration": "99999"},
        )
        assert resp.status_code == 400

    def test_bad_url_scheme_rejected(self, client):
        c, _ = client
        resp = c.post(
            "/upload/html",
            data={"url": "ftp://e.com/a", "duration": "1"},
        )
        assert resp.status_code == 400

    def test_non_html_file_rejected(self, client):
        c, _ = client
        resp = c.post(
            "/upload/html",
            files={"file": ("a.txt", b"hi", "text/plain")},
            data={"duration": "1"},
        )
        assert resp.status_code == 400

    def test_url_happy_path_creates_job(self, client):
        c, store = client
        resp = c.post(
            "/upload/html",
            data={"url": "https://e.com/a", "duration": "1",
                  "options_json": '{"mock": true}'},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["job_id"]
        assert store.get(body["job_id"]).source_type.value == "html_animation"


# ---------------- youtube_meta fallback ----------------

class TestYoutubeMetaFallback:
    def test_no_deck_falls_back_to_filename(self, client):
        c, store = client
        from server.schemas import (
            CreateJobRequest, JobOptions, JobSource, SourceType,
        )

        rec = store.create(CreateJobRequest(
            source_type=SourceType.HTML_ANIMATION,
            source=JobSource(url="https://e.com/a"),
            options=JobOptions(require_review=False),
        ))
        # 放一支假 mp4 進 artifacts/ 並註冊 (不需真的可播)
        mp4 = store.artifacts_dir(rec.id) / "my-animation.mp4"
        mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42fake")
        store.refresh_artifacts(rec.id)

        resp = c.get(f"/jobs/{rec.id}/artifacts/my-animation.mp4/youtube_meta")
        assert resp.status_code == 200, resp.text
        meta = resp.json()
        assert meta["title"] == "my-animation"
        assert meta["privacy"] == "unlisted"


# ---------------- rasterize_svg (需瀏覽器; 無 playwright/Chromium 跳過) ----------------

def _chromium_ok() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    import os
    return bool(os.environ.get("EDUSTUDIO_CHROMIUM_PATH")) or shutil.which("chromium") is not None


@pytest.mark.skipif(not _chromium_ok(), reason="需要 playwright + Chromium")
def test_rasterize_svg_writes_png_of_requested_size(tmp_path):
    from core.html_video import rasterize_svg
    from PIL import Image

    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="200"><rect width="320" height="200" fill="#123456"/><circle cx="160" cy="100" r="60" fill="#f28c28"/></svg>'
    out = rasterize_svg(svg, tmp_path / "s.png", width=320, height=200)
    with Image.open(out) as im:
        assert im.size == (320, 200)
        assert im.convert("RGB").getpixel((160, 100)) == (0xf2, 0x8c, 0x28)
