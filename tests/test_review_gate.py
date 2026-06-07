"""R-2 review gate 不可繞 (硬規則 #1)。

核心: _run_render_phase 入口 assert — require_review job 必須 reviewed=True 才能 render。
任何想跳過審查直接 render 的路徑都被擋死。
"""
from __future__ import annotations

import asyncio

import pytest

from server.jobs import JobStore
from server.runner import _run_render_phase
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)

_REVIEW_MSG = "尚未通過人工審查"


def _mk(store: JobStore, *, require_review: bool, state: JobState, reviewed: bool = False) -> str:
    req = CreateJobRequest(
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/tmp/x.pdf"),
        options=JobOptions(require_review=require_review),
    )
    rec = store.create(req)
    store.update(rec.id, state=state, reviewed=reviewed)
    return rec.id


def test_blocks_unreviewed_require_review_job(tmp_path):
    """require_review=True 且 reviewed=False → render 入口擋下, 標 FAILED。"""
    store = JobStore(root=tmp_path / "jobs")
    jid = _mk(store, require_review=True, state=JobState.AWAITING_REVIEW, reviewed=False)

    asyncio.run(_run_render_phase(store, jid))

    rec = store.get(jid)
    assert rec.state is JobState.FAILED
    assert _REVIEW_MSG in (rec.error or "")
    # 沒有產出任何 artifact (根本沒進 render)
    assert rec.artifacts == []


def test_reviewed_job_passes_gate(tmp_path):
    """reviewed=True → 通過 gate (之後因測試環境無 deck 在 render 階段失敗,
    但 error 不是 review-gate 訊息, 證明 gate 已放行)。"""
    store = JobStore(root=tmp_path / "jobs")
    jid = _mk(store, require_review=True, state=JobState.AWAITING_REVIEW, reviewed=True)

    asyncio.run(_run_render_phase(store, jid))

    rec = store.get(jid)
    assert _REVIEW_MSG not in (rec.error or "")


def test_non_require_review_not_blocked(tmp_path):
    """require_review=False → 不需審查, gate 不擋。"""
    store = JobStore(root=tmp_path / "jobs")
    jid = _mk(store, require_review=False, state=JobState.RENDERING, reviewed=False)

    asyncio.run(_run_render_phase(store, jid))

    rec = store.get(jid)
    assert _REVIEW_MSG not in (rec.error or "")


# ---------- approve 端點標記 reviewed ----------

def test_approve_marks_reviewed(tmp_path):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient

    from server.jobs import get_default_store
    from server.main import create_app

    store = JobStore(root=tmp_path / "jobs")
    jid = _mk(store, require_review=True, state=JobState.AWAITING_REVIEW, reviewed=False)

    app = create_app()
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        resp = c.post(f"/jobs/{jid}/approve")
        assert resp.status_code == 200

    # 人工 approve 後 reviewed 應為 True (同步寫入, 早於背景 render task)
    rec = store.get(jid)
    assert rec.reviewed is True
    assert rec.reviewed_at is not None


def test_default_reviewed_is_false(tmp_path):
    """新建 job reviewed 預設 False (還沒人審)。"""
    store = JobStore(root=tmp_path / "jobs")
    req = CreateJobRequest(
        source_type=SourceType.EXAM_PDF,
        source=JobSource(path="/tmp/x.pdf"),
        options=JobOptions(),
    )
    rec = store.create(req)
    assert rec.reviewed is False
    assert rec.reviewed_at is None
