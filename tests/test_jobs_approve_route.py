"""POST /jobs/{id}/approve — iter 55 加 done 狀態白名單.

mock schedule_render / schedule_job 避免真跑 ingest / Gemini 呼叫.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main upload route 依賴")

from fastapi.testclient import TestClient

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
    """乾淨 client + mock schedule_render / schedule_job 不真跑."""
    import server.routes.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "schedule_render", lambda store, jid: None)
    monkeypatch.setattr(jobs_mod, "schedule_job", lambda store, jid: None)

    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def _new_job(store: JobStore, state: JobState) -> str:
    rec = store.create(CreateJobRequest(
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/tmp/x.pdf"),
        options=JobOptions(),
    ))
    store.update(rec.id, state=state)
    return rec.id


class TestApproveJobStates:
    def test_awaiting_review_allowed(self, client):
        c, store = client
        jid = _new_job(store, JobState.AWAITING_REVIEW)
        resp = c.post(f"/jobs/{jid}/approve")
        assert resp.status_code == 200

    def test_failed_allowed(self, client):
        c, store = client
        jid = _new_job(store, JobState.FAILED)
        # 寫個 deck.json 讓 failed 路徑走 schedule_render
        (store.deck_path(jid)).write_text('{"sections": []}', encoding="utf-8")
        resp = c.post(f"/jobs/{jid}/approve")
        assert resp.status_code == 200

    def test_done_allowed_iter55(self, client):
        """iter 55: done 狀態允許重新渲染整支."""
        c, store = client
        jid = _new_job(store, JobState.DONE)
        resp = c.post(f"/jobs/{jid}/approve")
        assert resp.status_code == 200

    def test_pending_rejected(self, client):
        c, store = client
        jid = _new_job(store, JobState.PENDING)
        resp = c.post(f"/jobs/{jid}/approve")
        assert resp.status_code == 409

    def test_ingesting_rejected(self, client):
        c, store = client
        jid = _new_job(store, JobState.INGESTING)
        resp = c.post(f"/jobs/{jid}/approve")
        assert resp.status_code == 409

    def test_rendering_rejected(self, client):
        c, store = client
        jid = _new_job(store, JobState.RENDERING)
        resp = c.post(f"/jobs/{jid}/approve")
        assert resp.status_code == 409

    def test_missing_job_returns_404(self, client):
        c, _ = client
        resp = c.post("/jobs/nope/approve")
        assert resp.status_code == 404

    def test_done_approve_calls_schedule_render(self, client, monkeypatch):
        """iter 55: done state approve 該走 schedule_render (不重 ingest)."""
        c, store = client
        called: dict = {}
        import server.routes.jobs as jobs_mod
        monkeypatch.setattr(
            jobs_mod, "schedule_render",
            lambda store, jid: called.setdefault("render", jid),
        )
        monkeypatch.setattr(
            jobs_mod, "schedule_job",
            lambda store, jid: called.setdefault("job", jid),
        )
        jid = _new_job(store, JobState.DONE)
        # done 有 deck.json (理應, 因為已 render 完才會 done)
        store.deck_path(jid).write_text('{"sections":[]}', encoding="utf-8")
        resp = c.post(f"/jobs/{jid}/approve")
        assert resp.status_code == 200
        # done state 應呼叫 schedule_render, 不重 ingest
        assert called.get("render") == jid
        assert "job" not in called
