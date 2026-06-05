"""server.routes.projects HTTP route 測試（eduStudio 合併 PR-M1）。

驗收 Phase A 的 in-process Project 薄層：
- POST/GET /projects、GET /projects/{pid}
- POST /projects/{pid}/jobs：in-process 建 job（reuse jobs.create_job），job_id 掛進 jobs[]
- **review gate 延續性（硬規則 #1）**：exam_pdf 經 Project 端點建立、未顯式傳 require_review，
  仍預設 require_review=True（走的就是 jobs.create_job → _resolve_default_review 原路）
- POST /projects/{pid}/artifacts write-back + GET /projects/{pid}/notebook 聚合

Mock 策略同 test_jobs_crud_route：schedule_job noop（不真跑 ingest/Gemini），
ProjectStore / JobStore 都注入 tmp_path 隔離。
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import server.routes.jobs as jobs_mod
import server.routes.projects as projects_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    """乾淨 TestClient + 隔離 ProjectStore/JobStore + schedule_job noop。"""
    # jobs.create_job 內呼叫 schedule_job（背景排程）→ noop 掉避免真跑 pipeline。
    monkeypatch.setattr(jobs_mod, "schedule_job", lambda store, jid: None)

    app = create_app()
    job_store = JobStore(root=tmp_path / "jobs")
    project_store = projects_mod.ProjectStore(root=tmp_path / "projects")
    app.dependency_overrides[get_default_store] = lambda: job_store
    app.dependency_overrides[projects_mod.get_default_project_store] = lambda: project_store
    with TestClient(app) as c:
        yield c, project_store, job_store, tmp_path


def _make_real_pdf(tmp_path, name: str = "exam.pdf") -> str:
    p = tmp_path / name
    p.write_bytes(b"%PDF-1.4 fake bytes for routing test")
    return str(p)


# ---------- POST / GET /projects ----------
class TestProjectCrud:
    def test_create_returns_201(self, client):
        c, *_ = client
        r = c.post("/projects", json={
            "project_id": "course_statics_2026",
            "title": "靜力學 2026",
            "target_languages": ["zh-TW", "en-US"],
        })
        assert r.status_code == 201
        body = r.json()
        assert body["project_id"] == "course_statics_2026"
        assert body["target_languages"] == ["zh-TW", "en-US"]
        assert body["jobs"] == [] and body["sources"] == [] and body["artifacts"] == []

    def test_create_duplicate_returns_409(self, client):
        c, *_ = client
        c.post("/projects", json={"project_id": "dup", "title": "T"})
        r = c.post("/projects", json={"project_id": "dup", "title": "T2"})
        assert r.status_code == 409

    def test_list_and_get(self, client):
        c, *_ = client
        c.post("/projects", json={"project_id": "b", "title": "B"})
        c.post("/projects", json={"project_id": "a", "title": "A"})
        r = c.get("/projects")
        assert r.status_code == 200
        assert [p["project_id"] for p in r.json()] == ["a", "b"]  # 排序穩定
        r2 = c.get("/projects/a")
        assert r2.status_code == 200 and r2.json()["title"] == "A"

    def test_get_missing_returns_404(self, client):
        c, *_ = client
        assert c.get("/projects/nope").status_code == 404


# ---------- POST /projects/{pid}/jobs（in-process + review gate）----------
class TestProjectJobs:
    def test_create_job_in_process_attaches_to_project(self, client):
        c, project_store, job_store, tmp_path = client
        c.post("/projects", json={"project_id": "p", "title": "T"})
        pdf = _make_real_pdf(tmp_path, "doc.pdf")
        r = c.post("/projects/p/jobs", json={
            "source_type": "document",
            "source": {"path": pdf},
            "options": {},
        })
        assert r.status_code == 201
        job_id = r.json()["job_id"]
        # job 真的建在 JobStore，且 id 掛進 project.jobs[]。
        assert job_store.get(job_id) is not None
        assert project_store.get("p").jobs == [job_id]

    def test_exam_pdf_review_gate_preserved(self, client):
        """硬規則 #1：exam_pdf 經 Project 端點建立、未傳 require_review，仍預設 True。"""
        c, project_store, job_store, tmp_path = client
        c.post("/projects", json={"project_id": "p", "title": "T"})
        pdf = _make_real_pdf(tmp_path, "exam.pdf")
        r = c.post("/projects/p/jobs", json={
            "source_type": "exam_pdf",
            "source": {"path": pdf},
        })
        assert r.status_code == 201
        rec = job_store.get(r.json()["job_id"])
        # review gate 延續：走的是 jobs.create_job → _resolve_default_review 原路。
        assert rec.options.require_review is True

    def test_create_job_missing_project_returns_404(self, client):
        c, project_store, job_store, tmp_path = client
        pdf = _make_real_pdf(tmp_path, "doc.pdf")
        r = c.post("/projects/ghost/jobs", json={
            "source_type": "document",
            "source": {"path": pdf},
        })
        assert r.status_code == 404

    def test_create_job_invalid_source_still_validated(self, client):
        """reuse jobs.create_job → 其 source 驗證仍生效（ftp scheme 該 400）。"""
        c, *_ = client
        c.post("/projects", json={"project_id": "p", "title": "T"})
        r = c.post("/projects/p/jobs", json={
            "source_type": "url",
            "source": {"url": "ftp://bad/x"},
        })
        assert r.status_code == 400


# ---------- artifacts write-back + notebook 聚合 ----------
class TestArtifactsAndNotebook:
    def test_add_artifact_and_notebook(self, client):
        c, project_store, job_store, tmp_path = client
        c.post("/projects", json={"project_id": "p", "title": "T"})
        r = c.post("/projects/p/artifacts", json={
            "kind": "deck",
            "produced_by": "infoCard",
            "state": "awaiting_review",
        })
        assert r.status_code == 201
        # 落盤 reload 確認持久化。
        assert len(project_store.get("p").artifacts) == 1
        nb = c.get("/projects/p/notebook")
        assert nb.status_code == 200
        body = nb.json()
        assert body["counts"]["artifacts"] == 1
        assert body["artifacts"][0]["produced_by"] == "infoCard"

    def test_add_artifact_missing_project_404(self, client):
        c, *_ = client
        r = c.post("/projects/ghost/artifacts", json={
            "kind": "image", "produced_by": "infoCard",
        })
        assert r.status_code == 404
