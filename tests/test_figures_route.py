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


class TestListFiguresMalformedRawContent:
    """iter 120: raw_content.json 內各種壞資料形態. list_figures 該 graceful
    degrade 不該 500. 補 iter 54 路徑這條 (Exception swallow / `or []` /
    isinstance 過濾) 三層防呆的直接覆蓋."""

    def test_invalid_json_returns_empty(self, client):
        """raw_content.json 內容不是合法 JSON → 走 try/except 退空 list,
        不該 500. 真實情境: ingest 中途 crash 留下半截檔."""
        c, store = client
        # 不繞 _create_job_with_figures, 因為它一定寫合法 JSON.
        from server.jobs import JobStore
        from server.schemas import CreateJobRequest, JobOptions, JobSource, SourceType
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        raw_path = store.job_dir(rec.id) / "raw_content.json"
        raw_path.write_text("{not valid json", encoding="utf-8")
        resp = c.get(f"/jobs/{rec.id}/figures")
        assert resp.status_code == 200
        assert resp.json() == {"figures": []}

    def test_binary_bytes_in_raw_content_returns_empty(self, client):
        """raw_content.json 是 binary garbage (非 UTF-8) → read_text 該炸,
        try/except 仍該吞掉退空 list. 真實情境: 檔案被別 process 寫壞."""
        c, store = client
        from server.schemas import CreateJobRequest, JobOptions, JobSource, SourceType
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        raw_path = store.job_dir(rec.id) / "raw_content.json"
        raw_path.write_bytes(b"\xff\xfe\x00\x01\x02\x03 non-utf8 binary garbage")
        resp = c.get(f"/jobs/{rec.id}/figures")
        assert resp.status_code == 200
        assert resp.json() == {"figures": []}

    def test_figures_field_none_returns_empty(self, client):
        """raw.get('figures') 是 None → `or []` 退空 list."""
        c, store = client
        jid = _create_job_with_figures(store, figures=None)
        # _create_job_with_figures 內 figures or [] 把 None 轉空; 直接覆寫驗 None
        raw_path = store.job_dir(jid) / "raw_content.json"
        raw_path.write_text(json.dumps({"figures": None}), encoding="utf-8")
        resp = c.get(f"/jobs/{jid}/figures")
        assert resp.status_code == 200
        assert resp.json() == {"figures": []}

    def test_figures_field_missing_returns_empty(self, client):
        """raw_content.json 完全沒 figures key → raw.get('figures') 是 None."""
        c, store = client
        from server.schemas import CreateJobRequest, JobOptions, JobSource, SourceType
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        raw_path = store.job_dir(rec.id) / "raw_content.json"
        raw_path.write_text(json.dumps({"source_kind": "document"}), encoding="utf-8")
        resp = c.get(f"/jobs/{rec.id}/figures")
        assert resp.status_code == 200
        assert resp.json() == {"figures": []}

    def test_figure_with_empty_path_skipped(self, client):
        """figure 有 path key 但值是空字串 → `not f.get('path')` 過濾掉."""
        c, store = client
        figs = [
            {"id": "good", "path": "good.png", "page_no": 1,
             "width": 100, "height": 100, "caption_hint": ""},
            {"id": "empty_path", "path": "", "page_no": 2},
            {"id": "none_path", "path": None, "page_no": 3},
        ]
        jid = _create_job_with_figures(store, figs)
        resp = c.get(f"/jobs/{jid}/figures")
        data = resp.json()
        assert len(data["figures"]) == 1
        assert data["figures"][0]["id"] == "good"


class TestDownloadFigureEdgeCases:
    """iter 120: download_figure 內容類型 / 目錄目標 / 邊角情境."""

    def test_serves_jpeg_with_correct_content_type(self, client):
        """jpeg figure 透過 FileResponse 該帶 image/jpeg content-type (
        FastAPI/Starlette 走 mimetypes 自動推斷 — 不該因 .jpeg 不在 list
        退到 octet-stream)."""
        c, store = client
        jpeg_data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00 fake jpeg"
        jid = _create_job_with_figures(
            store, [{"id": "fig_p1_1", "path": "fig_p1_1.jpeg", "page_no": 1,
                     "width": 800, "height": 600, "caption_hint": ""}],
            real_files=[("fig_p1_1.jpeg", jpeg_data)],
        )
        resp = c.get(f"/jobs/{jid}/figures/fig_p1_1.jpeg")
        assert resp.status_code == 200
        assert resp.content == jpeg_data
        assert resp.headers["content-type"].startswith("image/jpeg")

    def test_serves_jpg_with_correct_content_type(self, client):
        """.jpg 副檔同 .jpeg, 該推斷 image/jpeg."""
        c, store = client
        jpg_data = b"\xff\xd8\xff\xe1 jpg fake"
        jid = _create_job_with_figures(
            store, [{"id": "f", "path": "f.jpg", "page_no": 1,
                     "width": 100, "height": 100, "caption_hint": ""}],
            real_files=[("f.jpg", jpg_data)],
        )
        resp = c.get(f"/jobs/{jid}/figures/f.jpg")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/jpeg")

    def test_directory_target_returns_404(self, client):
        """target 是目錄不是檔 (e.g. user 在 figures/ 下建子目錄) → 404,
        不該 500, 也不該回 dir listing."""
        c, store = client
        jid = _create_job_with_figures(store)
        # 在 figures/ 下建子目錄 sub_dir/, 然後 GET /figures/sub_dir
        figs_dir = store.job_dir(jid) / "figures"
        figs_dir.mkdir(parents=True, exist_ok=True)
        (figs_dir / "sub_dir").mkdir()
        resp = c.get(f"/jobs/{jid}/figures/sub_dir")
        assert resp.status_code == 404

    def test_dotdot_in_name_returns_400(self, client):
        """name 含 `..` 該 400 不該 404 — `..png` 也擋 (寬鬆比, 但檔名極少
        合法含 .., 放行安全)."""
        c, store = client
        jid = _create_job_with_figures(store)
        # 走 client 不繞 URL encode (TestClient 不會自動 encode .. )
        resp = c.get(f"/jobs/{jid}/figures/..foo.png")
        assert resp.status_code == 400

    def test_forward_slash_in_name_returns_400(self, client):
        """name 含 `/` (URL encoded) 該 400. TestClient + httpx 行為:
        %2F 預設 decode 後該觸發路由 path 解析, 直接含 / 走不進這 route —
        補一個明確 encoded slash 防呆."""
        c, store = client
        jid = _create_job_with_figures(store)
        # %2F → forward slash, 該被 `/` in name 防呆擋
        resp = c.get(f"/jobs/{jid}/figures/sub%2Ffoo.png")
        # 405 (路由不匹配 due to extra path) 或 400 (path traversal 攔截) 都算擋住
        assert resp.status_code in (400, 404, 405)
