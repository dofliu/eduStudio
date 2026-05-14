"""GET /library 測試 (PR-3m library page + iter 47 final.mp4 優先).

不真打 Gemini / 不真 render, 用 fake JobRecord + scan_artifacts 注入測試.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

from server.jobs import JobStore, get_default_store
from server.main import create_app
from server.schemas import (
    Artifact,
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)


@pytest.fixture
def client(tmp_path):
    """乾淨 TestClient + 空 JobStore."""
    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def _make_done_job(store: JobStore, artifact_names: list[str]) -> str:
    """建一個 state=done 的 job, 注入指定 artifact 名稱."""
    rec = store.create(CreateJobRequest(
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/tmp/fake.pdf"),
        options=JobOptions(require_review=False),
    ))
    artifacts = [
        Artifact(name=name, path=f"jobs/{rec.id}/artifacts/{name}",
                 size_bytes=1024 * 1024, kind="mp4")
        for name in artifact_names
    ]
    store.update(rec.id, state=JobState.DONE, artifacts=artifacts)
    return rec.id


class TestLibraryFinalMp4Priority:
    """iter 47: 有 final.mp4 時 library 只列 final.mp4, 不列各章."""

    def test_job_with_final_mp4_lists_only_final(self, client):
        c, store = client
        _make_done_job(store, ["ch1.mp4", "ch2.mp4", "ch3.mp4", "final.mp4"])
        resp = c.get("/library")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["artifact_name"] == "final.mp4"

    def test_job_without_final_mp4_lists_all(self, client):
        """沒 final.mp4 (例: 單章 deck / exam_pdf 逐題) 走原 logic 全列."""
        c, store = client
        _make_done_job(store, ["q1.mp4", "q2.mp4", "q3.mp4"])
        resp = c.get("/library")
        items = resp.json()["items"]
        names = sorted(i["artifact_name"] for i in items)
        assert names == ["q1.mp4", "q2.mp4", "q3.mp4"]

    def test_single_mp4_job_lists_it(self, client):
        """單一 mp4 (不叫 final.mp4) 也要列出."""
        c, store = client
        _make_done_job(store, ["q1.mp4"])
        resp = c.get("/library")
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["artifact_name"] == "q1.mp4"

    def test_only_final_mp4_lists_it(self, client):
        """只有 final.mp4 (理論上不會發生但防呆)."""
        c, store = client
        _make_done_job(store, ["final.mp4"])
        resp = c.get("/library")
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["artifact_name"] == "final.mp4"

    def test_no_mp4_job_skipped(self, client):
        """沒任何 mp4 的 job (失敗 / ingesting) 不該出現在 library."""
        c, store = client
        rec = store.create(CreateJobRequest(
            source_type=SourceType.DOCUMENT,
            source=JobSource(path="/tmp/fake.pdf"),
            options=JobOptions(require_review=False),
        ))
        store.update(rec.id, state=JobState.DONE, artifacts=[])
        resp = c.get("/library")
        assert resp.json()["items"] == []

    def test_multiple_jobs_mixed(self, client):
        """多 job: 有 final 的列 final, 沒 final 的列全部."""
        c, store = client
        _make_done_job(store, ["ch1.mp4", "final.mp4"])
        _make_done_job(store, ["q1.mp4", "q2.mp4"])
        resp = c.get("/library")
        items = resp.json()["items"]
        names = sorted(i["artifact_name"] for i in items)
        # final + q1 + q2 = 3 個 (ch1 被 final 取代)
        assert names == ["final.mp4", "q1.mp4", "q2.mp4"]
