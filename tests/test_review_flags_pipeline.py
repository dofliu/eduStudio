"""F9-1c — 確定性 review 校驗接進 pipeline + 落 review_flags.json + 端點。

F9-1a 把純函式 `core.review_assist.check_deck` 做好 (deck in → ReviewFlag out, 全
offline)。這一刀把它接上線:
  - ingest 完 (進 awaiting_review 前) 算一次, 落 jobs/<id>/review_flags.json
  - PUT /jobs/{id}/draft 改 deck 後重算
  - GET /jobs/{id}/review-flags 給 reviewer / 前端 (F9-1d) 讀

不可妥協紀律 (呼應 RFC): flags 只標記、不改 deck、**不入狀態機、不阻 approve**,
校驗失敗 fail-open (不卡 review)。這支鎖住「接線不斷」+「不越界碰 review gate」。

offline-first: 全程不打 API — 直接造 deck dict / 用 mock 考卷 (solve.mock_output)。
"""
from __future__ import annotations

import asyncio
import json

import pytest

from server.jobs import JobStore
from server.runner import run_job, write_review_flags
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)


# 一個故意算錯的 deck: 50000/500=100, 但寫成 1000 (差一個數量級的低級錯)。
# narration 用阿拉伯數字 1000 對齊 display 結果, 把 narration_mismatch 那項排除掉,
# 讓測試聚焦在 arithmetic 一項上 (不混兩種 flag)。
_BAD_DECK = {
    "exam_title": "材力測試",
    "problems": [
        {
            "id": "q1",
            "steps": [
                {"display": "σ = 50000 / 500 = 1000 MPa",
                 "narration": "代入數值後得到 1000 百萬帕斯卡。"},
            ],
        }
    ],
}

_CLEAN_DECK = {
    "exam_title": "材力測試",
    "problems": [
        {
            "id": "q1",
            "steps": [
                {"display": "σ = 50000 / 500 = 100 MPa",
                 "narration": "代入數值後得到 100 百萬帕斯卡。"},
            ],
        }
    ],
}


def _mk_job(store: JobStore, deck: dict | None = None) -> str:
    rec = store.create(CreateJobRequest(
        source_type=SourceType.EXAM_PDF,
        source=JobSource(path="/tmp/x.pdf"),
        options=JobOptions(),
    ))
    if deck is not None:
        store.deck_path(rec.id).write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8",
        )
    return rec.id


# ---------- write_review_flags (純落盤層) ----------

def test_write_flags_for_bad_deck(tmp_path):
    """有算術錯的 deck → review_flags.json 落一個 arithmetic flag。"""
    store = JobStore(root=tmp_path / "jobs")
    jid = _mk_job(store, _BAD_DECK)

    n = write_review_flags(store, jid)

    assert n == 1
    flags = json.loads(store.review_flags_path(jid).read_text(encoding="utf-8"))
    assert len(flags) == 1
    assert flags[0]["kind"] == "arithmetic"
    assert flags[0]["problem_id"] == "q1"
    assert flags[0]["source"] == "deterministic"


def test_write_flags_for_clean_deck(tmp_path):
    """乾淨 deck → 落空 list (檔案存在但無 flag), 不是不寫檔。"""
    store = JobStore(root=tmp_path / "jobs")
    jid = _mk_job(store, _CLEAN_DECK)

    n = write_review_flags(store, jid)

    assert n == 0
    assert store.review_flags_path(jid).exists()
    assert json.loads(store.review_flags_path(jid).read_text(encoding="utf-8")) == []


def test_write_flags_no_deck_noop(tmp_path):
    """沒 deck.json (ingest 未完) → 回 0 且不寫檔 (不誤造空檔)。"""
    store = JobStore(root=tmp_path / "jobs")
    jid = _mk_job(store, deck=None)

    n = write_review_flags(store, jid)

    assert n == 0
    assert not store.review_flags_path(jid).exists()


def test_flags_does_not_touch_deck_or_state(tmp_path):
    """硬規則 #1: 只標記不改 deck、不動 state (flags 不入狀態機)。"""
    store = JobStore(root=tmp_path / "jobs")
    jid = _mk_job(store, _BAD_DECK)
    store.update(jid, state=JobState.AWAITING_REVIEW)
    deck_before = store.deck_path(jid).read_text(encoding="utf-8")

    write_review_flags(store, jid)

    assert store.deck_path(jid).read_text(encoding="utf-8") == deck_before
    assert store.get(jid).state is JobState.AWAITING_REVIEW


# ---------- pipeline 接線 (run_job ingest 完算一次) ----------

def test_pipeline_writes_flags_at_awaiting_review(tmp_path):
    """run_job 跑 mock 考卷 → 停 awaiting_review 時 review_flags.json 已落盤。

    mock_output 是乾淨 deck → flags 為空 list, 但檔案要存在 (證明接線有跑)。
    """
    store = JobStore(root=tmp_path / "jobs")
    pdf = tmp_path / "exam.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake exam")  # mock ingest 仍會檢查 source.path 存在
    rec = store.create(CreateJobRequest(
        source_type=SourceType.EXAM_PDF,
        source=JobSource(path=str(pdf)),
        options=JobOptions(require_review=True, mock=True),
    ))

    asyncio.run(run_job(store, rec.id))

    assert store.get(rec.id).state is JobState.AWAITING_REVIEW
    assert store.review_flags_path(rec.id).exists()
    flags = json.loads(store.review_flags_path(rec.id).read_text(encoding="utf-8"))
    assert flags == []  # mock_output 算術 / 旁白都對得上


# ---------- 端點 ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi.testclient")
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    import server.routes.jobs as jobs_mod
    from server.jobs import get_default_store
    from server.main import create_app

    monkeypatch.setattr(jobs_mod, "schedule_render", lambda store, jid: None)
    monkeypatch.setattr(jobs_mod, "schedule_job", lambda store, jid: None)

    app = create_app()
    store = JobStore(root=tmp_path / "jobs")
    app.dependency_overrides[get_default_store] = lambda: store
    with TestClient(app) as c:
        yield c, store


def test_get_review_flags_returns_flags(client):
    c, store = client
    jid = _mk_job(store, _BAD_DECK)
    write_review_flags(store, jid)

    r = c.get(f"/jobs/{jid}/review-flags")

    assert r.status_code == 200
    flags = r.json()["flags"]
    assert len(flags) == 1
    assert flags[0]["kind"] == "arithmetic"


def test_get_review_flags_empty_when_uncomputed(client):
    """沒算過 (沒 review_flags.json) → 空 list 非 404 (比照 versions 端點)。

    T0-3 起同時回 `coverage`;舊 job 沒算過 → null (前端據此不顯示覆蓋率區塊)。
    """
    c, store = client
    jid = _mk_job(store, _CLEAN_DECK)

    r = c.get(f"/jobs/{jid}/review-flags")

    assert r.status_code == 200
    assert r.json() == {"flags": [], "coverage": None}


def test_get_review_flags_unknown_job_404(client):
    c, _ = client
    assert c.get("/jobs/nope/review-flags").status_code == 404


def test_put_draft_recomputes_flags(client):
    """PUT /draft 改 deck 後 flags 跟著更新 (改錯→標, 改對→清)。"""
    c, store = client
    jid = _mk_job(store, _BAD_DECK)
    store.update(jid, state=JobState.AWAITING_REVIEW)
    write_review_flags(store, jid)
    assert len(c.get(f"/jobs/{jid}/review-flags").json()["flags"]) == 1

    # reviewer 把 1000 改成正確的 100 → 重算後 flag 清空
    r = c.put(f"/jobs/{jid}/draft", json={"deck": _CLEAN_DECK})
    assert r.status_code == 200
    assert c.get(f"/jobs/{jid}/review-flags").json()["flags"] == []


def test_put_draft_flagging_a_clean_deck(client):
    """反向: 原本乾淨, 改成算錯的 deck → 重算後標出 flag。"""
    c, store = client
    jid = _mk_job(store, _CLEAN_DECK)
    store.update(jid, state=JobState.AWAITING_REVIEW)
    write_review_flags(store, jid)
    assert c.get(f"/jobs/{jid}/review-flags").json()["flags"] == []

    r = c.put(f"/jobs/{jid}/draft", json={"deck": _BAD_DECK})
    assert r.status_code == 200
    flags = c.get(f"/jobs/{jid}/review-flags").json()["flags"]
    assert len(flags) == 1 and flags[0]["kind"] == "arithmetic"
