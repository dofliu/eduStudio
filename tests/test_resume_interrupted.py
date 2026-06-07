"""R-1 啟動止血: JobStore.resume_interrupted() — 重啟後卡住的 job 標 failed。

PENDING/INGESTING/RENDERING = 重啟前在跑/排隊, task 已沒 → 標 failed。
AWAITING_REVIEW = 合法暫停(等人工), 不動。DONE/FAILED = 終態, 不動。
"""
from __future__ import annotations

import pytest

from server.jobs import JobStore
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)


def _mk_job(store: JobStore, state: JobState) -> str:
    req = CreateJobRequest(
        source_type=SourceType.DOCUMENT,
        source=JobSource(path="/tmp/x.pdf"),
        options=JobOptions(),
    )
    rec = store.create(req)  # 建立後是 PENDING
    if state is not JobState.PENDING:
        store.update(rec.id, state=state)
    return rec.id


def test_marks_inflight_states_failed(tmp_path):
    store = JobStore(root=tmp_path / "jobs")
    pending = _mk_job(store, JobState.PENDING)
    ingesting = _mk_job(store, JobState.INGESTING)
    rendering = _mk_job(store, JobState.RENDERING)

    affected = set(store.resume_interrupted())
    assert affected == {pending, ingesting, rendering}

    for jid in (pending, ingesting, rendering):
        rec = store.get(jid)
        assert rec.state is JobState.FAILED
        assert "重啟" in (rec.error or "")


def test_leaves_awaiting_review_and_terminal_untouched(tmp_path):
    store = JobStore(root=tmp_path / "jobs")
    review = _mk_job(store, JobState.AWAITING_REVIEW)
    done = _mk_job(store, JobState.DONE)
    failed = _mk_job(store, JobState.FAILED)

    affected = store.resume_interrupted()
    assert affected == []  # 沒有 in-flight job

    assert store.get(review).state is JobState.AWAITING_REVIEW
    assert store.get(done).state is JobState.DONE
    assert store.get(failed).state is JobState.FAILED


def test_persists_across_reload(tmp_path):
    """標 failed 要寫盤 — 重新 load 的 store 也看得到。"""
    root = tmp_path / "jobs"
    store = JobStore(root=root)
    jid = _mk_job(store, JobState.RENDERING)
    store.resume_interrupted()

    # 模擬 server 再次啟動: 全新 store 從磁碟讀回
    store2 = JobStore(root=root)
    assert store2.get(jid).state is JobState.FAILED


def test_idempotent(tmp_path):
    """跑兩次不應重複處理(第二次沒有 in-flight job)。"""
    store = JobStore(root=tmp_path / "jobs")
    _mk_job(store, JobState.INGESTING)
    first = store.resume_interrupted()
    second = store.resume_interrupted()
    assert len(first) == 1
    assert second == []
