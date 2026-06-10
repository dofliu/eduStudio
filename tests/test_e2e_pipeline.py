"""T-1 端到端整合測試 — TestClient + 真 pipeline 接線。

現況既有 ~2400 測強在純函式單元 / 各端點隔離測, 但缺一條把「整條接線」串起來
的 happy-path: 建 job (HTTP) → ingest → review gate → approve (HTTP) → render →
下載 artifact (HTTP)。這支鎖住「整條接線不斷」: route → JobStore → runner →
render → artifacts → 下載 route。

offline-first (硬規則 #3): 兩個外部邊界被 mock —
  - Gemini ingest: 用 EXAM_PDF + options.mock=True, 走 solve.mock_output() 離線資料,
    完全不打真 API。
  - ffmpeg/TTS render: monkeypatch core.render_video, 只寫 fake mp4/srt, 不跑 ffmpeg。

review gate (硬規則 #1) 仍真實生效 — 第二支測試證明 approve 前 render 被擋死,
approve 後才放行, 在整條 pipeline 裡而非只在單元層。
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi.testclient")
from fastapi.testclient import TestClient  # noqa: E402

from server.jobs import JobStore, get_default_store  # noqa: E402
from server.main import create_app  # noqa: E402
from server.runner import _run_render_phase, run_job  # noqa: E402
from server.schemas import JobState  # noqa: E402

_REVIEW_MSG = "尚未通過人工審查"


@pytest.fixture
def e2e(tmp_path, monkeypatch):
    """隔離的 store + app + 被 mock 的 ingest/render 邊界。

    回傳 SimpleNamespace(client, store, pdf, render_calls):
      - render_calls: 每次 fake render_video 被呼叫時 append unique_name,
        用來斷言 render 有沒有真的被觸發 (gate 擋下時應為空)。
    """
    # render 輸出目錄隔到 tmp (fake render_video 寫這裡, runner 再搬到 artifacts/)
    import core.config as core_config
    out_dir = tmp_path / "render_out"
    monkeypatch.setattr(core_config, "OUTPUT_DIR", out_dir)

    # mock ffmpeg/TTS 邊界: render_video → 只寫 fake mp4/srt 到 OUTPUT_DIR
    # (runner._run_render_inner 在 call 時 `from core import render_video`, 讀
    #  core 模組當下的屬性 → 在這裡 setattr 即生效)
    import core as core_pkg
    render_calls: list[str] = []

    async def fake_render_video(v0_path, unique_name, start_step=None):
        render_calls.append(unique_name)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{unique_name}.mp4").write_bytes(b"FAKE_MP4")
        (out_dir / f"{unique_name}.srt").write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nhi\n", encoding="utf-8",
        )

    monkeypatch.setattr(core_pkg, "render_video", fake_render_video)

    # 背景 scheduler noop 化 — HTTP create/approve 不在背景跑 task, 改由測試自己
    # 用 asyncio.run 同步驅動 pipeline, 保持確定性 (不靠 TestClient event loop 競態)
    import server.routes.jobs as jobs_routes
    monkeypatch.setattr(jobs_routes, "schedule_job", lambda store, jid: None)
    monkeypatch.setattr(jobs_routes, "schedule_render", lambda store, jid: None)

    # JobStore.scan_artifacts 用模組層 JOBS_DIR 算 artifact 相對路徑 (server/jobs.py
    # :239), 故 root 與 JOBS_DIR 要一致, 否則 refresh_artifacts 的 relative_to 會炸。
    jobs_root = tmp_path / "jobs"
    import server.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", jobs_root)

    store = JobStore(root=jobs_root)
    app = create_app()
    app.dependency_overrides[get_default_store] = lambda: store

    pdf = tmp_path / "exam.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake exam")

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, store=store, pdf=pdf, render_calls=render_calls,
        )


def _create_exam_job(e2e) -> str:
    """POST /jobs 建一個 require_review 的 mock 考卷 job, 回 job_id。"""
    resp = e2e.client.post("/jobs", json={
        "source_type": "exam_pdf",
        "source": {"path": str(e2e.pdf)},
        "options": {"require_review": True, "mock": True},
    })
    assert resp.status_code == 201, resp.text
    return resp.json()["job_id"]


def test_e2e_exam_pdf_create_to_artifact(e2e):
    """整條 happy-path: 建 job → ingest → review → approve → render → 下載產物。"""
    c, store = e2e.client, e2e.store

    # 1. 建 job (HTTP) — scheduler 被 noop, 還沒跑 → PENDING
    jid = _create_exam_job(e2e)
    assert store.get(jid).state is JobState.PENDING

    # 2. ingest (mock Gemini = solve.mock_output, 不打真 API)
    asyncio.run(run_job(store, jid))
    rec = store.get(jid)
    assert rec.state is JobState.AWAITING_REVIEW  # 停在 review gate
    assert rec.reviewed is False
    assert store.deck_path(jid).exists()

    # 3. reviewer 透過 HTTP 看 deck draft
    draft = c.get(f"/jobs/{jid}/draft")
    assert draft.status_code == 200
    assert draft.json()["problems"][0]["id"] == "q1"

    # 4. 人工 approve (HTTP) → reviewed=True
    appr = c.post(f"/jobs/{jid}/approve")
    assert appr.status_code == 200
    assert store.get(jid).reviewed is True

    # 5. render (mock ffmpeg = fake render_video)
    asyncio.run(_run_render_phase(store, jid))
    rec = store.get(jid)
    assert rec.state is JobState.DONE
    assert rec.error is None
    assert e2e.render_calls == [f"job_{jid}__q1"]  # render 真的被觸發 (逐題一支)

    # 6. 下載 artifact (HTTP GET) — mp4 + srt 都在
    dl = c.get(f"/jobs/{jid}/artifacts/q1.mp4")
    assert dl.status_code == 200
    assert dl.content == b"FAKE_MP4"
    assert c.get(f"/jobs/{jid}/artifacts/q1.srt").status_code == 200


def test_e2e_review_gate_blocks_then_approves(e2e):
    """R-2 review gate 在整條 pipeline 裡仍不可繞 (硬規則 #1)。

    approve 前直接 render → 被 gate 擋下標 FAILED 且根本沒進 render_video;
    approve 後才放行 → DONE + 產 artifact。
    """
    c, store = e2e.client, e2e.store

    jid = _create_exam_job(e2e)
    asyncio.run(run_job(store, jid))
    assert store.get(jid).state is JobState.AWAITING_REVIEW

    # approve 前直接 render → gate 擋下 FAILED, 不產 artifact
    asyncio.run(_run_render_phase(store, jid))
    rec = store.get(jid)
    assert rec.state is JobState.FAILED
    assert _REVIEW_MSG in (rec.error or "")
    assert e2e.render_calls == []  # 根本沒進 render_video
    assert c.get(f"/jobs/{jid}/artifacts/q1.mp4").status_code == 404

    # approve 後 render 放行 → DONE
    assert c.post(f"/jobs/{jid}/approve").status_code == 200
    asyncio.run(_run_render_phase(store, jid))
    rec = store.get(jid)
    assert rec.state is JobState.DONE
    assert e2e.render_calls == [f"job_{jid}__q1"]
    assert c.get(f"/jobs/{jid}/artifacts/q1.mp4").status_code == 200
