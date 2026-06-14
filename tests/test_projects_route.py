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

    def test_create_job_records_project_id(self, client):
        """F9-2 Option A：經 Project 端點建立的 job 反向記下所屬課程 project_id。"""
        c, project_store, job_store, tmp_path = client
        c.post("/projects", json={"project_id": "matsci", "title": "材料力學"})
        pdf = _make_real_pdf(tmp_path, "doc.pdf")
        r = c.post("/projects/matsci/jobs", json={
            "source_type": "document",
            "source": {"path": pdf},
            "options": {},
        })
        assert r.status_code == 201
        rec = job_store.get(r.json()["job_id"])
        # 存 canonical project.project_id (= safe_id 後)；render 旁白據此現讀 glossary。
        assert rec.project_id == project_store.get("matsci").project_id

    def test_direct_create_job_has_no_project_id(self, client):
        """直接 POST /jobs（不經課程）的 job project_id 為 None（無主之 job 無 glossary）。"""
        c, project_store, job_store, tmp_path = client
        pdf = _make_real_pdf(tmp_path, "doc.pdf")
        r = c.post("/jobs", json={
            "source_type": "document",
            "source": {"path": pdf},
            "options": {},
        })
        assert r.status_code == 201
        rec = job_store.get(r.json()["job_id"])
        assert rec.project_id is None

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

    def test_add_source_and_notebook(self, client):
        c, project_store, job_store, tmp_path = client
        c.post("/projects", json={"project_id": "p", "title": "T"})
        r = c.post("/projects/p/sources", json={
            "type": "exam_pdf", "path_or_url": "/data/exam.pdf", "lang": "zh-TW",
        })
        assert r.status_code == 201
        assert r.json()["type"] == "exam_pdf"
        # 落盤 + notebook 聚合看得到
        assert len(project_store.get("p").sources) == 1
        nb = c.get("/projects/p/notebook").json()
        assert nb["counts"]["sources"] == 1

    def test_add_source_missing_project_404(self, client):
        c, *_ = client
        r = c.post("/projects/ghost/sources", json={
            "type": "url", "path_or_url": "http://x",
        })
        assert r.status_code == 404

    def test_remove_source(self, client):
        c, project_store, job_store, tmp_path = client
        c.post("/projects", json={"project_id": "p", "title": "T"})
        sid = c.post("/projects/p/sources", json={
            "type": "url", "path_or_url": "http://x",
        }).json()["source_id"]
        # 刪除 → 204，notebook 看不到
        r = c.delete(f"/projects/p/sources/{sid}")
        assert r.status_code == 204
        assert len(project_store.get("p").sources) == 0
        # 再刪同一個 → 404
        assert c.delete(f"/projects/p/sources/{sid}").status_code == 404

    def test_remove_source_missing_project_404(self, client):
        c, *_ = client
        assert c.delete("/projects/ghost/sources/src_x").status_code == 404


# ---------- 課程術語表 glossary（F9-2 GET/PUT）----------
class TestGlossary:
    _GLOSSARY = {
        "course": "材料力學",
        "entries": [
            {
                "term": "ω_n",
                "reading": "自然頻率",
                "translations": {"en": "natural frequency"},
                "aliases": ["wn", "ωn"],
            },
            {"term": "PID", "expansion": "比例-積分-微分"},
        ],
    }

    def test_get_before_create_returns_404_distinct_from_missing_project(self, client):
        """課在但尚未建 glossary → 404，detail 與『project 不存在』可區分。"""
        c, *_ = client
        c.post("/projects", json={"project_id": "p", "title": "材力 2026"})
        r = c.get("/projects/p/glossary")
        assert r.status_code == 404
        assert "尚未建立" in r.json()["detail"]
        # project 本身不存在 → 也是 404，但 detail 不同
        r2 = c.get("/projects/ghost/glossary")
        assert r2.status_code == 404
        assert "project 不存在" in r2.json()["detail"]

    def test_put_then_get_roundtrip_and_persist(self, client):
        c, project_store, job_store, tmp_path = client
        c.post("/projects", json={"project_id": "p", "title": "材力 2026"})
        r = c.put("/projects/p/glossary", json=self._GLOSSARY)
        assert r.status_code == 200
        assert r.json()["course"] == "材料力學"
        # 落盤後重抓一致
        got = c.get("/projects/p/glossary")
        assert got.status_code == 200
        body = got.json()
        assert body["course"] == "材料力學"
        assert [e["term"] for e in body["entries"]] == ["ω_n", "PID"]
        # 跨 store reload 確認真持久化（非僅記憶體）
        reloaded = project_store.get_glossary("p")
        assert reloaded is not None
        assert reloaded.entries[0].reading == "自然頻率"

    def test_put_overwrites_whole_glossary(self, client):
        c, *_ = client
        c.post("/projects", json={"project_id": "p", "title": "T"})
        c.put("/projects/p/glossary", json=self._GLOSSARY)
        # 整張覆寫成單條
        r = c.put("/projects/p/glossary", json={
            "course": "材料力學", "entries": [{"term": "σ", "reading": "應力"}],
        })
        assert r.status_code == 200
        body = c.get("/projects/p/glossary").json()
        assert [e["term"] for e in body["entries"]] == ["σ"]

    def test_put_missing_project_returns_404(self, client):
        c, *_ = client
        r = c.put("/projects/ghost/glossary", json=self._GLOSSARY)
        assert r.status_code == 404

    def test_put_empty_term_rejected_422(self, client):
        """core.glossary 的 term 非空 validator 在 HTTP 層生效（pydantic 422）。"""
        c, *_ = client
        c.post("/projects", json={"project_id": "p", "title": "T"})
        r = c.put("/projects/p/glossary", json={
            "course": "材力", "entries": [{"term": "   "}],
        })
        assert r.status_code == 422

    def test_glossary_isolated_per_project(self, client):
        c, *_ = client
        c.post("/projects", json={"project_id": "p1", "title": "材力"})
        c.post("/projects", json={"project_id": "p2", "title": "自控"})
        c.put("/projects/p1/glossary", json=self._GLOSSARY)
        # p2 未建 → 仍 404，不串課
        assert c.get("/projects/p2/glossary").status_code == 404
        assert c.get("/projects/p1/glossary").status_code == 200
