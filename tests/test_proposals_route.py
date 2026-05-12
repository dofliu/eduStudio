"""POST /proposals routes 測試 (v4 階段 2 B iter 14 server route).

跟 test_upload.py 同 pattern: FastAPI TestClient + JobStore dependency override
+ PROPOSALS_PATH 指到 tmp_path. 不真打 Gemini / 不真跑 schedule_job 重型 task。
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi.testclient", reason="需要 fastapi 安裝")
pytest.importorskip("multipart", reason="server.main 內 upload route 需要")

from fastapi.testclient import TestClient

import core.config as core_config
import server.routes.proposals as proposals_mod
from server.jobs import JobStore, get_default_store
from server.main import create_app


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def proposals_file(tmp_path, monkeypatch):
    """PROPOSALS_PATH 指到 tmp, 不污染真實 jobs/。"""
    pp = tmp_path / "proposals.json"
    monkeypatch.setattr(core_config, "PROPOSALS_PATH", pp)
    monkeypatch.setattr(proposals_mod, "PROPOSALS_PATH", pp)
    return pp


@pytest.fixture
def client(tmp_path, proposals_file, monkeypatch):
    """乾淨 TestClient + 空 JobStore."""
    # schedule_job 在 approve 流程會被 call, mock 成 noop 避免真跑 background task
    monkeypatch.setattr(
        proposals_mod, "schedule_job",
        lambda store, job_id: None,
    )

    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c


def _write_proposals(path, items):
    """Helper: 直接寫測試 proposals.json (跳過 ideate 真實流程)."""
    payload = {"generated_at": "2026-05-13T00:00:00+00:00", "proposals": items}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _sample_proposal(id_="prop_001", source_file="/tmp/a.pdf",
                      status_val="pending", job_id=None):
    return {
        "id": id_,
        "generated_at": "2026-05-13T00:00:00+00:00",
        "source_file": source_file,
        "source_type": "exam_pdf",
        "suggested_title": "材料力學 第3題",
        "suggested_chapters": [],
        "reason": "計算多步, 學生易錯",
        "estimated_duration_min": 5,
        "status": status_val,
        "job_id": job_id,
    }


# ============================================================
# Tests
# ============================================================


class TestList:
    def test_empty_when_no_file(self, client):
        # proposals_file fixture 已建路徑但沒寫檔
        resp = client.get("/proposals")
        assert resp.status_code == 200
        assert resp.json() == {"proposals": []}

    def test_lists_pending_proposals(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1"),
            _sample_proposal(id_="p2", source_file="/tmp/b.pdf"),
        ])
        resp = client.get("/proposals")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["proposals"]) == 2
        ids = [p["id"] for p in data["proposals"]]
        assert ids == ["p1", "p2"]

    def test_excludes_non_pending_by_default(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="pending"),
            _sample_proposal(id_="p2", status_val="approved"),
            _sample_proposal(id_="p3", status_val="ignored"),
            _sample_proposal(id_="p4", status_val="expired"),
        ])
        resp = client.get("/proposals")
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["proposals"]]
        assert ids == ["p1"]

    def test_only_pending_false_returns_all(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="pending"),
            _sample_proposal(id_="p2", status_val="approved"),
        ])
        resp = client.get("/proposals?only_pending=false")
        assert resp.status_code == 200
        ids = sorted(p["id"] for p in resp.json()["proposals"])
        assert ids == ["p1", "p2"]


class TestApprove:
    def test_approve_creates_job_and_marks_approved(self, client, proposals_file):
        _write_proposals(proposals_file, [_sample_proposal(id_="p1")])

        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 201
        data = resp.json()
        # 回 proposal (已 approved) + job
        assert data["proposal"]["status"] == "approved"
        assert data["proposal"]["job_id"] == data["job"]["job_id"]
        assert data["job"]["state"] in ("pending", "ingesting")  # state 可能因 schedule timing 不同

        # proposals.json 已 persist
        raw = json.loads(proposals_file.read_text(encoding="utf-8"))
        assert raw["proposals"][0]["status"] == "approved"
        assert raw["proposals"][0]["job_id"] is not None

    def test_approve_missing_id_returns_404(self, client, proposals_file):
        _write_proposals(proposals_file, [])
        resp = client.post("/proposals/nope/approve")
        assert resp.status_code == 404

    def test_approve_already_approved_returns_409(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="approved", job_id="job_xxx"),
        ])
        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 409

    def test_approve_already_ignored_returns_409(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="ignored"),
        ])
        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 409

    def test_approve_bad_source_type_returns_400(self, client, proposals_file):
        bad = _sample_proposal(id_="p1")
        bad["source_type"] = "definitely_not_a_real_type"
        _write_proposals(proposals_file, [bad])
        resp = client.post("/proposals/p1/approve")
        assert resp.status_code == 400


class TestIgnore:
    def test_ignore_marks_status(self, client, proposals_file):
        _write_proposals(proposals_file, [_sample_proposal(id_="p1")])

        resp = client.patch("/proposals/p1/ignore")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

        raw = json.loads(proposals_file.read_text(encoding="utf-8"))
        assert raw["proposals"][0]["status"] == "ignored"

    def test_ignore_missing_id_returns_404(self, client, proposals_file):
        _write_proposals(proposals_file, [])
        resp = client.patch("/proposals/nope/ignore")
        assert resp.status_code == 404

    def test_ignore_already_decided_returns_409(self, client, proposals_file):
        _write_proposals(proposals_file, [
            _sample_proposal(id_="p1", status_val="approved", job_id="x"),
        ])
        resp = client.patch("/proposals/p1/ignore")
        assert resp.status_code == 409
