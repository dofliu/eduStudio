"""server.routes.jobs CRUD HTTP route 測試 (iter 119).

server/routes/jobs.py 內四個 CRUD endpoint 從 PR-3a 上線後一直沒對應
route-level 測試:
  - POST   /jobs                  (建立 + 排程, 含 source 早期驗證)
  - GET    /jobs                  (列出, created_at desc)
  - GET    /jobs/{id}             (單一狀態)
  - DELETE /jobs/{id}             (刪除 + 磁碟 cleanup)

接 iter 111-118 安全鎖補測思路 — 任何 refactor 不小心動 source_type
分支邏輯 (url scheme 檢查 / path 存在檢查) / created_at 排序 / cache
與磁碟同步邏輯 → 直接上線, route-level 是最後一道防線.

Mock 策略:
- schedule_job: monkeypatch 成 noop, 避免真跑 ingest / Gemini
- create_job 內走 Path(...).exists() 檢查, 用 tmp_path 真檔測試
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import server.routes.jobs as jobs_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    """乾淨 TestClient + 隔離 JobStore + schedule_job noop."""
    monkeypatch.setattr(jobs_mod, "schedule_job", lambda store, jid: None)

    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store, tmp_path


def _make_real_pdf(tmp_path, name: str = "doc.pdf") -> str:
    """create_job 內走 Path(...).exists(), 寫個真檔避開 400."""
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4 fake bytes for routing test")
    return str(p)


# ---------- POST /jobs ----------

class TestCreateJobEndpoint:
    """POST /jobs — 建立 + source_type 早期驗證 + schedule_job 觸發."""

    def test_document_valid_returns_201(self, client):
        c, store, tmp_path = client
        pdf = _make_real_pdf(tmp_path)
        r = c.post("/jobs", json={
            "source_type": "document",
            "source": {"path": pdf},
            "options": {},
        })
        assert r.status_code == 201
        body = r.json()
        assert "job_id" in body
        assert body["state"] == "pending"
        assert body["status_url"] == f"/jobs/{body['job_id']}"

    def test_exam_pdf_default_require_review_true(self, client):
        """硬規則 #1: exam_pdf 預設 require_review=True (學術誠信底線)."""
        c, store, tmp_path = client
        pdf = _make_real_pdf(tmp_path, "exam.pdf")
        r = c.post("/jobs", json={
            "source_type": "exam_pdf",
            "source": {"path": pdf},
        })
        assert r.status_code == 201
        rec = store.get(r.json()["job_id"])
        assert rec.options.require_review is True

    def test_slides_pdf_default_require_review_false(self, client):
        """slides_pdf 預設 require_review=False (簡報講解風險低)."""
        c, store, tmp_path = client
        pdf = _make_real_pdf(tmp_path, "slides.pdf")
        r = c.post("/jobs", json={
            "source_type": "slides_pdf",
            "source": {"path": pdf},
        })
        assert r.status_code == 201
        rec = store.get(r.json()["job_id"])
        assert rec.options.require_review is False

    def test_url_https_valid_returns_201(self, client):
        c, store, _ = client
        r = c.post("/jobs", json={
            "source_type": "url",
            "source": {"url": "https://example.com/article"},
        })
        assert r.status_code == 201

    def test_url_http_valid_returns_201(self, client):
        """http:// 跟 https:// 兩種都該接受 (route 內白名單)."""
        c, store, _ = client
        r = c.post("/jobs", json={
            "source_type": "url",
            "source": {"url": "http://blog.example.com/post"},
        })
        assert r.status_code == 201

    def test_url_invalid_scheme_rejected(self, client):
        """ftp:// / file:// / 等非 http(s) scheme 該 400."""
        c, store, _ = client
        r = c.post("/jobs", json={
            "source_type": "url",
            "source": {"url": "ftp://example.com/file"},
        })
        assert r.status_code == 400
        assert "http://" in r.json()["detail"]

    def test_url_empty_rejected(self, client):
        """source_type=url 但 url 空字串 → 400."""
        c, store, _ = client
        r = c.post("/jobs", json={
            "source_type": "url",
            "source": {"url": ""},
        })
        assert r.status_code == 400

    def test_url_whitespace_only_rejected(self, client):
        """純空白 url 走 .strip() 後該被當空 → 400 (不該 path traversal)."""
        c, store, _ = client
        r = c.post("/jobs", json={
            "source_type": "url",
            "source": {"url": "   "},
        })
        assert r.status_code == 400

    def test_document_missing_path_rejected(self, client):
        """source_type=document 但沒給 path → 400."""
        c, store, _ = client
        r = c.post("/jobs", json={
            "source_type": "document",
            "source": {},
        })
        assert r.status_code == 400
        assert "source.path" in r.json()["detail"]

    def test_document_nonexistent_path_rejected(self, client):
        """指定的 path 不存在 → 400 (避免 ingest 階段才炸)."""
        c, store, _ = client
        r = c.post("/jobs", json={
            "source_type": "document",
            "source": {"path": "/nonexistent/path/to/doc.pdf"},
        })
        assert r.status_code == 400
        assert "不存在" in r.json()["detail"]

    def test_schedule_job_called_with_new_id(self, client, monkeypatch):
        """schedule_job(store, job_id) 該被觸發 (背景排程, 不會等)."""
        c, store, tmp_path = client
        called = []
        monkeypatch.setattr(
            jobs_mod, "schedule_job",
            lambda s, jid: called.append(jid),
        )
        pdf = _make_real_pdf(tmp_path)
        r = c.post("/jobs", json={
            "source_type": "document",
            "source": {"path": pdf},
        })
        assert r.status_code == 201
        assert called == [r.json()["job_id"]]


# ---------- GET /jobs ----------

class TestListJobsEndpoint:
    """GET /jobs — 列 cache 全部, 依 created_at desc 排序."""

    def test_empty_store_returns_empty_list(self, client):
        c, store, _ = client
        r = c.get("/jobs")
        assert r.status_code == 200
        assert r.json() == {"jobs": []}

    def test_single_job_appears_in_list(self, client):
        c, store, _ = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        r = c.get("/jobs")
        assert r.status_code == 200
        body = r.json()
        assert len(body["jobs"]) == 1
        assert body["jobs"][0]["id"] == rec.id

    def test_multi_jobs_sorted_created_desc(self, client):
        """新建的 job 該排在前面 (created_at desc).

        Windows microsecond resolution 不夠分辨連續 3 個 store.create,
        改用 store.update 顯式設不同 created_at 避免 sort 退化成 stable
        order (等於沒測到排序邏輯).
        """
        from datetime import datetime, timezone, timedelta
        c, store, _ = client
        base = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)
        ids = []
        for i in range(3):
            rec = store.create(CreateJobRequest(
                source_type=SourceType.DOCUMENT,
                source=JobSource(path=f"/tmp/job{i}.pdf"),
                options=JobOptions(),
            ))
            # 顯式各差 1 分鐘, ids[-1] 最新
            store.update(rec.id, created_at=base + timedelta(minutes=i))
            ids.append(rec.id)
        r = c.get("/jobs")
        listed = [j["id"] for j in r.json()["jobs"]]
        # 最後 create 的最新, 該排第一
        assert listed[0] == ids[-1]
        assert listed[-1] == ids[0]

    def test_mixed_source_types_all_listed(self, client):
        """跨 source_type (document / url / slides_pdf) 都該出現."""
        c, store, _ = client
        store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/d.pdf"),
            options=JobOptions(),
        ))
        store.create(CreateJobRequest(
            source_type=SourceType.URL,
            source=JobSource(url="https://x.com/a"),
            options=JobOptions(),
        ))
        store.create(CreateJobRequest(
            source_type=SourceType.SLIDES_PDF,
            source=JobSource(path="/tmp/s.pdf"),
            options=JobOptions(),
        ))
        r = c.get("/jobs")
        listed_types = {j["source_type"] for j in r.json()["jobs"]}
        assert listed_types == {"document", "url", "slides_pdf"}


# ---------- GET /jobs/{id} ----------

class TestGetJobEndpoint:
    """GET /jobs/{id} — 純讀 cache, _require_job 攔 404."""

    def test_existing_job_returns_record(self, client):
        c, store, _ = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        r = c.get(f"/jobs/{rec.id}")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == rec.id
        assert body["state"] == "pending"
        assert body["source_type"] == "document"
        # JobRecord 必含的時間 / state 欄位
        assert "created_at" in body
        assert "updated_at" in body
        assert body["youtube_uploads"] == {}  # 預設空 dict, PR-3f

    def test_nonexistent_job_returns_404(self, client):
        c, store, _ = client
        r = c.get("/jobs/deadbeef0000")
        assert r.status_code == 404
        assert "不存在" in r.json()["detail"]


# ---------- DELETE /jobs/{id} ----------

class TestDeleteJobEndpoint:
    """DELETE /jobs/{id} — cache 跟磁碟同步 cleanup."""

    def test_existing_job_returns_204(self, client):
        c, store, _ = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        r = c.delete(f"/jobs/{rec.id}")
        assert r.status_code == 204
        assert r.content == b""

    def test_nonexistent_job_returns_404(self, client):
        c, store, _ = client
        r = c.delete("/jobs/deadbeef0000")
        assert r.status_code == 404

    def test_delete_then_get_returns_404(self, client):
        """delete 後 cache 該清乾淨, 同 id GET 該 404 不該回幽靈."""
        c, store, _ = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        c.delete(f"/jobs/{rec.id}")
        r = c.get(f"/jobs/{rec.id}")
        assert r.status_code == 404

    def test_delete_removes_from_list(self, client):
        """delete 後 list 該不再包含該 job."""
        c, store, _ = client
        keep = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/keep.pdf"),
            options=JobOptions(),
        ))
        gone = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/gone.pdf"),
            options=JobOptions(),
        ))
        c.delete(f"/jobs/{gone.id}")
        r = c.get("/jobs")
        listed = [j["id"] for j in r.json()["jobs"]]
        assert keep.id in listed
        assert gone.id not in listed

    def test_delete_removes_disk_dir(self, client):
        """delete 後 jobs/<id>/ 目錄該被 rmtree 清掉 (不留 state.json 殘骸)."""
        c, store, _ = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        job_dir = store.root / rec.id
        assert job_dir.exists()
        r = c.delete(f"/jobs/{rec.id}")
        assert r.status_code == 204
        assert not job_dir.exists()

    def test_double_delete_second_returns_404(self, client):
        """同 id delete 兩次, 第二次該 404 (cache + disk 都已清)."""
        c, store, _ = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/x.pdf"),
            options=JobOptions(),
        ))
        r1 = c.delete(f"/jobs/{rec.id}")
        assert r1.status_code == 204
        r2 = c.delete(f"/jobs/{rec.id}")
        assert r2.status_code == 404
