"""GET /jobs/{id}/figures (list) + /jobs/{id}/figures/{name} (file).

iter 54: 給 SlideEditor 換圖 picker 用. 純 fastapi route 測, 不打 Gemini / 不真渲染.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

from server.jobs import JobStore, get_default_store
from server.main import create_app
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    SourceType,
)


@pytest.fixture
def client(tmp_path):
    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def _create_job_with_figures(
    store: JobStore, figures: list[dict] | None = None,
    real_files: list[tuple[str, bytes]] | None = None,
) -> str:
    """建 job + 寫 raw_content.json + 寫 figures/ 內檔."""
    rec = store.create(CreateJobRequest(
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/tmp/fake.pdf"),
        options=JobOptions(),
    ))
    raw = {"source_kind": "document", "figures": figures or []}
    raw_path = store.job_dir(rec.id) / "raw_content.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")

    if real_files:
        figs_dir = store.job_dir(rec.id) / "figures"
        figs_dir.mkdir(parents=True, exist_ok=True)
        for name, content in real_files:
            (figs_dir / name).write_bytes(content)
    return rec.id


class TestListFigures:
    def test_empty_job_returns_empty(self, client):
        c, store = client
        jid = _create_job_with_figures(store)
        resp = c.get(f"/jobs/{jid}/figures")
        assert resp.status_code == 200
        assert resp.json() == {"figures": []}

    def test_missing_raw_content_returns_empty(self, client):
        """raw_content.json 不存在 (e.g. ingest 還沒完) → 空 list."""
        c, store = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        resp = c.get(f"/jobs/{rec.id}/figures")
        assert resp.status_code == 200
        assert resp.json() == {"figures": []}

    def test_lists_with_url_added(self, client):
        """有 figures → 每張回 metadata + url 欄位."""
        c, store = client
        figs = [
            {"id": "fig_p3_1", "page_no": 3, "path": "fig_p3_1.png",
             "width": 400, "height": 300, "caption_hint": "Figure 1: arch"},
            {"id": "fig_p7_2", "page_no": 7, "path": "fig_p7_2.jpeg",
             "width": 800, "height": 600, "caption_hint": ""},
        ]
        jid = _create_job_with_figures(store, figs)
        resp = c.get(f"/jobs/{jid}/figures")
        data = resp.json()
        assert len(data["figures"]) == 2
        f0 = data["figures"][0]
        assert f0["id"] == "fig_p3_1"
        assert f0["url"] == f"/jobs/{jid}/figures/fig_p3_1.png"
        assert f0["caption_hint"] == "Figure 1: arch"

    def test_skips_malformed_entries(self, client):
        """raw_content figures 含壞欄位 (沒 path / 非 dict) 該被略過."""
        c, store = client
        figs = [
            {"id": "good", "path": "good.png", "page_no": 1,
             "width": 100, "height": 100, "caption_hint": ""},
            {"id": "no_path"},                # 缺 path, skip
            "not a dict",                      # 非 dict, skip
            None,                              # None, skip
        ]
        jid = _create_job_with_figures(store, figs)
        resp = c.get(f"/jobs/{jid}/figures")
        data = resp.json()
        assert len(data["figures"]) == 1
        assert data["figures"][0]["id"] == "good"

    def test_404_for_missing_job(self, client):
        c, _ = client
        resp = c.get("/jobs/nonexistent/figures")
        assert resp.status_code == 404


class TestDownloadFigure:
    def test_serves_png(self, client):
        c, store = client
        png_data = b"\x89PNG\r\n\x1a\n test png content"
        jid = _create_job_with_figures(
            store, [{"id": "fig_p3_1", "path": "fig_p3_1.png", "page_no": 3,
                     "width": 400, "height": 300, "caption_hint": ""}],
            real_files=[("fig_p3_1.png", png_data)],
        )
        resp = c.get(f"/jobs/{jid}/figures/fig_p3_1.png")
        assert resp.status_code == 200
        assert resp.content == png_data

    def test_404_for_missing_figure_file(self, client):
        """figure 檔不存在 → 404 (即使 raw_content 內列了它)."""
        c, store = client
        jid = _create_job_with_figures(store)
        resp = c.get(f"/jobs/{jid}/figures/nonexistent.png")
        assert resp.status_code == 404

    def test_path_traversal_rejected(self, client):
        c, store = client
        jid = _create_job_with_figures(store)
        # 含 .. / / \ 的 name 該被擋
        for bad in ["..%2Fetc%2Fpasswd", "..%5C..%5Cevil.png"]:
            resp = c.get(f"/jobs/{jid}/figures/{bad}")
            # 400 (非法) 或 404 (找不到) 都算擋住, 不該 200
            assert resp.status_code in (400, 404)

    def test_404_for_missing_job(self, client):
        c, _ = client
        resp = c.get("/jobs/nonexistent/figures/x.png")
        assert resp.status_code == 404
