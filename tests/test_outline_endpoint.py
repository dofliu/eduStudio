"""D1 v1 iter 81: GET /jobs/{id}/outline endpoint."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.jobs import JobStore


@pytest.fixture
def store_with_tmp(tmp_path):
    """JobStore 接 tmp_path, app inject 進 dependency_overrides."""
    from server.jobs import get_default_store
    store = JobStore(root=tmp_path / "jobs")
    app = create_app()
    app.dependency_overrides[get_default_store] = lambda: store
    return store, app


@pytest.fixture
def client(store_with_tmp):
    _, app = store_with_tmp
    return TestClient(app)


@pytest.fixture
def make_job_with_outline(store_with_tmp):
    """建立假 job, 寫 outline.json 進 store.root/<id>/."""
    store, _ = store_with_tmp

    def _make(job_id: str, outline: dict | None = None):
        job_dir = store.root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        if outline is not None:
            (job_dir / "outline.json").write_text(
                json.dumps(outline, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return job_dir
    return _make


class TestGetOutline:
    def test_outline_exists_returns_json(self, client, make_job_with_outline):
        sample_outline = {
            "deck_title": "材料力學",
            "summary": "固體在外力下的變形與內部應力",
            "sections": [
                {"id": "intro", "title": "概念", "intent": "介紹基本概念",
                 "topics": ["應力", "應變"]},
                {"id": "hooke", "title": "虎克定律", "intent": "推導 σ=Eε",
                 "topics": ["彈性模數"]},
            ],
        }
        make_job_with_outline("test123", outline=sample_outline)
        r = client.get("/jobs/test123/outline")
        assert r.status_code == 200
        assert r.json() == sample_outline

    def test_no_outline_returns_404(self, client, make_job_with_outline):
        """outline.json 不存在 (例: exam_pdf source 不產 outline) → 404."""
        make_job_with_outline("nooutline")  # 不寫 outline.json
        r = client.get("/jobs/nooutline/outline")
        assert r.status_code == 404

    def test_nonexistent_job_returns_404(self, client):
        r = client.get("/jobs/doesnotexist/outline")
        assert r.status_code == 404

    def test_outline_path_helper(self, tmp_path):
        """JobStore.outline_path 該指向 jobs/<id>/outline.json."""
        store = JobStore(root=tmp_path)
        p = store.outline_path("abc")
        assert p == tmp_path / "abc" / "outline.json"
