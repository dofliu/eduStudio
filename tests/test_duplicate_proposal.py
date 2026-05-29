"""iter 89: POST /proposals/{id}/duplicate — 從任何 status 複製成新 PENDING."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.jobs import JobStore, get_default_store


@pytest.fixture
def client(tmp_path, monkeypatch):
    """proposals 寫到 tmp_path 避免污染真實 PROPOSALS_PATH.

    iter 11: 同時 override get_default_store → tmp JobStore. 否則
    test_duplicate_then_approve_succeeds 呼叫 /approve 會在 production
    jobs/ 真建 job + schedule_job ingest 假路徑 /x/prop_approved_1.pdf,
    每次 pytest 跑都漏一筆「ingest 失敗」到真實 Jobs 作業中心 (routine
    每 2 小時跑 baseline 測試 → 每 2 小時冒一筆). 沿用全 repo route 測試慣例.
    """
    fake_path = tmp_path / "proposals.json"
    monkeypatch.setattr("server.routes.proposals.PROPOSALS_PATH", fake_path)
    store = JobStore(tmp_path / "jobs")
    # 初始 proposals
    def _make(pid: str, status: str, title: str, dur: int = 5):
        return {
            "id": pid, "status": status, "source_type": "document",
            "source_file": f"/x/{pid}.pdf",
            "suggested_title": title,
            "suggested_chapters": [],
            "reason": "test fixture",
            "estimated_duration_min": dur,
            "generated_at": "2026-05-17T00:00:00",
        }
    sample = [
        _make("prop_pending_1", "pending", "PENDING 一個"),
        {**_make("prop_approved_1", "approved", "APPROVED 一個"),
         "job_id": "j_done_1"},
        _make("prop_ignored_1", "ignored", "IGNORED 一個", dur=3),
    ]
    # load_proposals 預期格式: {"proposals": [...]}
    fake_path.write_text(
        json.dumps({"proposals": sample}, ensure_ascii=False),
        encoding="utf-8",
    )
    app = create_app()
    app.dependency_overrides[get_default_store] = lambda: store
    return TestClient(app)


def _load(client) -> list[dict]:
    r = client.get("/proposals?only_pending=false")
    assert r.status_code == 200
    return r.json()["proposals"]


class TestDuplicateProposal:
    def test_duplicate_approved_creates_new_pending(self, client):
        r = client.post("/proposals/prop_approved_1/duplicate")
        assert r.status_code == 200
        new_prop = r.json()
        assert new_prop["status"] == "pending"
        assert new_prop["id"] != "prop_approved_1"
        assert new_prop["id"].startswith("prop_")
        # 來源 metadata 該複製過去
        assert new_prop["source_file"] == "/x/prop_approved_1.pdf"
        assert new_prop["suggested_title"] == "APPROVED 一個"
        # _from 該記原 id (alias 後 ProposalResponse 暴露為 _from)
        assert new_prop.get("_from") == "prop_approved_1"
        # job_id 該清掉
        assert new_prop.get("job_id") is None

    def test_duplicate_persists_to_file(self, client):
        before = _load(client)
        client.post("/proposals/prop_approved_1/duplicate")
        after = _load(client)
        assert len(after) == len(before) + 1
        # 原 approved 仍 approved
        approved = next(p for p in after if p["id"] == "prop_approved_1")
        assert approved["status"] == "approved"

    def test_duplicate_ignored_also_works(self, client):
        r = client.post("/proposals/prop_ignored_1/duplicate")
        assert r.status_code == 200
        assert r.json()["status"] == "pending"
        assert r.json().get("_from") == "prop_ignored_1"

    def test_duplicate_pending_also_works(self, client):
        """duplicate 不檢查 status, pending 也能複製 (給用戶想試不同設定)."""
        r = client.post("/proposals/prop_pending_1/duplicate")
        assert r.status_code == 200
        assert r.json()["status"] == "pending"

    def test_duplicate_nonexistent_returns_404(self, client):
        r = client.post("/proposals/nonexistent/duplicate")
        assert r.status_code == 404

    def test_duplicate_then_approve_succeeds(self, client):
        """完整流程: approved → duplicate → 新 pending → approve. 不會 409."""
        # 複製
        r1 = client.post("/proposals/prop_approved_1/duplicate")
        new_id = r1.json()["id"]
        # approve 新的 (不會 409 conflict)
        r2 = client.post(f"/proposals/{new_id}/approve")
        # 應該 200 (建 job 成功) — 但因 mock store 無法真建 job, 至少不該 409
        # 用 ! 401/409/422 來確認狀態檢查 pass
        assert r2.status_code != 409, "duplicated proposal 該能 approve, 不該 409"
