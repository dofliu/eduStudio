"""server.runner.run_job — iter 137 (Closeout backlog 4/4) 主流程串接安全鎖.

run_job 是整個 job pipeline 的最外層 orchestrator (routes 層 schedule 成
asyncio.create_task 背景跑). 串起 ingest → (require_review pause | render) → done,
外加 per-job log 生命週期. 從 PR-2a / PR-3a 上線後一路加 hook (iter 42 intro
多樣化 / iter 48 時長估算 / PR-4c log attach), 但這層 wrapper 本身沒對應直接
測試. 任何 refactor 不小心動以下任一就直接上線, 跟 iter 111-136 同思路
(route / helper / orchestrator safety lock):

  - rec is None (job 不存在) → 早 return, 不 attach log / 不跑 ingest
  - entry: attach_job_log(job_id, jobs/<id>/log.jsonl) + current_job_id 設成 job_id
  - ingest 階段 state → INGESTING, _start_stage("ingest"), await _run_ingest
  - ingest 失敗 → logger.exception + _end_stage_fail + state FAILED +
    error="ingest 失敗: {e}" + **early return** (不進 review 分支 / 不 render)
  - ingest 成功 → _end_stage_ok + 兩個 post-ingest hook (intro 多樣化 / 時長
    估算) 各自 try/except 吞例外 (失敗只 warning, 不擋 awaiting_review)
  - deck_path 更新成 relative + forward slash ("jobs/{id}/deck.json")
  - **require_review=True → state AWAITING_REVIEW + early return, _run_render_phase
    NOT called** (CLAUDE.md 硬規則 #1: AI 產出考題答案必須人工 review, 不可繞)
  - require_review=False → await _run_render_phase (續跑 render)
  - 外層 catch-all: 任何沒被內層 handle 的例外 → state FAILED + error="unexpected: {e}"
  - finally: current_job_id.reset(token) + detach_job_log (永遠跑)

策略 = monkeypatch runner_mod._run_ingest / _run_render_phase /
_rewrite_deck_intros_inplace / _log_deck_duration_estimate / attach_job_log /
detach_job_log 成計次 stub (都是 server.runner module global, run_job 以 bare
name lookup, patch runner_mod 直接生效). 不真打 Gemini / ffmpeg / TTS /
讀真 PDF. 0 production code 改動.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import server.jobs as jobs_mod
import server.runner as runner_mod
from core.logging_setup import current_job_id
from server.jobs import JobStore
from server.runner import run_job
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    JobState,
    SourceType,
)


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    """乾淨 JobStore — 跟 test_runner_render_phase 同 pattern.
    monkeypatch module-level JOBS_DIR, 不然 artifact / log path 仍指真實 jobs/.
    """
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


@pytest.fixture
def make_job(store: JobStore):
    """factory: 建一筆 job, 可指定 source_type / require_review.

    require_review 顯式傳值 (避免依賴 _resolve_default_review 預設) — run_job
    只讀 rec.options.require_review 決定要不要 pause.
    """
    def _make(
        source_type: SourceType = SourceType.EXAM_PDF,
        require_review: bool = True,
    ) -> str:
        rec = store.create(CreateJobRequest(
            source_type=source_type,
            source=JobSource(path="/fake.pdf"),
            options=JobOptions(require_review=require_review),
        ))
        store.artifacts_dir(rec.id).mkdir(parents=True, exist_ok=True)
        return rec.id
    return _make


@pytest.fixture
def stubs(monkeypatch: pytest.MonkeyPatch) -> dict:
    """攔截 run_job 串接的所有下游 — 預設全 no-op 成功.

    可設 state['ingest_raise'] / ['render_phase_raise'] / ['rewrite_raise'] /
    ['log_dur_raise'] = Exception 模擬各環節失敗.
    """
    state: dict = {
        "ingest_called": 0,
        "ingest_store": None,
        "ingest_rec": None,
        "ingest_mid_state": None,   # _run_ingest 執行瞬間的 store state
        "ingest_raise": None,
        "render_phase_called": 0,
        "render_phase_args": None,
        "render_phase_raise": None,
        "rewrite_called": 0,
        "rewrite_args": None,
        "rewrite_raise": None,
        "log_dur_called": 0,
        "log_dur_args": None,
        "log_dur_raise": None,
        "attach_calls": [],
        "detach_calls": [],
    }

    async def fake_ingest(store, rec):
        state["ingest_called"] += 1
        state["ingest_store"] = store
        state["ingest_rec"] = rec
        # 執行瞬間 snapshot — 證明 entry 已 store.update(state=INGESTING)
        state["ingest_mid_state"] = store.get(rec.id).state
        if state["ingest_raise"] is not None:
            raise state["ingest_raise"]
        return {"ok": True}

    async def fake_render_phase(store, job_id, *, section_id=None):
        state["render_phase_called"] += 1
        state["render_phase_args"] = (store, job_id, section_id)
        if state["render_phase_raise"] is not None:
            raise state["render_phase_raise"]

    def fake_rewrite(store, job_id, source_type_value):
        state["rewrite_called"] += 1
        state["rewrite_args"] = (store, job_id, source_type_value)
        if state["rewrite_raise"] is not None:
            raise state["rewrite_raise"]

    def fake_log_dur(store, job_id, length_mode):
        state["log_dur_called"] += 1
        state["log_dur_args"] = (store, job_id, length_mode)
        if state["log_dur_raise"] is not None:
            raise state["log_dur_raise"]

    def fake_attach(jid, log_path):
        state["attach_calls"].append((jid, log_path))

    def fake_detach(jid):
        state["detach_calls"].append(jid)

    monkeypatch.setattr(runner_mod, "_run_ingest", fake_ingest)
    monkeypatch.setattr(runner_mod, "_run_render_phase", fake_render_phase)
    monkeypatch.setattr(runner_mod, "_rewrite_deck_intros_inplace", fake_rewrite)
    monkeypatch.setattr(runner_mod, "_log_deck_duration_estimate", fake_log_dur)
    monkeypatch.setattr(runner_mod, "attach_job_log", fake_attach)
    monkeypatch.setattr(runner_mod, "detach_job_log", fake_detach)
    return state


# ---------------------------------------------------------------- TestJobNotFound


class TestJobNotFound:
    """rec is None → 早 return, 什麼都不該發生 (PR-4c log attach 也不該跑)."""

    @pytest.mark.asyncio
    async def test_missing_job_returns_early(self, store, stubs):
        """不存在的 job_id → 不 attach log / 不跑 ingest (鎖 `if rec is None: return`
        在 attach_job_log 之前, 否則對不存在的 job 開 FileHandler 洩 FD).
        """
        await run_job(store, "nonexistent-job-id")
        assert stubs["attach_calls"] == []
        assert stubs["ingest_called"] == 0
        assert stubs["detach_calls"] == []


# ---------------------------------------------------------------- TestIngestPhase


class TestIngestPhase:
    """ingest 階段串接: state INGESTING + _run_ingest(store, rec) + stage done."""

    @pytest.mark.asyncio
    async def test_ingest_called_once_with_store_and_rec(self, store, make_job, stubs):
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert stubs["ingest_called"] == 1
        assert stubs["ingest_store"] is store
        assert stubs["ingest_rec"].id == job_id

    @pytest.mark.asyncio
    async def test_state_is_ingesting_during_ingest(self, store, make_job, stubs):
        """_run_ingest 執行瞬間 store state 該是 INGESTING — 鎖 entry 那次
        store.update(state=INGESTING) 在 await _run_ingest 之前 (UI 才看得到「處理中」).
        """
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert stubs["ingest_mid_state"] == JobState.INGESTING

    @pytest.mark.asyncio
    async def test_ingest_stage_recorded_done(self, store, make_job, stubs):
        """ingest 成功 → stage[0] name="ingest" state="done" (require_review=True
        會 pause, 不會多一個 render stage, 鎖 ingest stage 單獨存在且標 done).
        """
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        rec = store.get(job_id)
        assert rec.stages[0].name == "ingest"
        assert rec.stages[0].state == "done"
        assert rec.stages[0].error is None


# ---------------------------------------------------------------- TestRequireReviewPause


class TestRequireReviewPause:
    """硬規則 #1: require_review=True → 停在 awaiting_review, 絕不自動 render.

    這是學術誠信底線 (AI 產出考題答案不可未經人工 review 就渲染上片).
    require_review=False → 才續跑 render.
    """

    @pytest.mark.asyncio
    async def test_require_review_true_pauses_no_render(self, store, make_job, stubs):
        """require_review=True → state AWAITING_REVIEW + _run_render_phase 0 calls.

        鎖 `if rec.options.require_review: ... return` 的 return 不被偷拿掉,
        否則 exam_pdf job 會跳過人工 review 直接 render — 踩硬規則 #1.
        """
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        rec = store.get(job_id)
        assert rec.state == JobState.AWAITING_REVIEW
        assert stubs["render_phase_called"] == 0

    @pytest.mark.asyncio
    async def test_require_review_true_logs_await(self, store, make_job, stubs, caplog):
        import logging
        job_id = make_job(require_review=True)
        with caplog.at_level(logging.INFO, logger="server.runner"):
            await run_job(store, job_id)
        msgs = [r.getMessage() for r in caplog.records]
        assert any("等候 review" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_require_review_false_proceeds_to_render(self, store, make_job, stubs):
        """require_review=False → _run_render_phase 被叫一次 (store, job_id 透傳,
        section_id 預設 None — 整份 render).
        """
        job_id = make_job(source_type=SourceType.SLIDES_PDF, require_review=False)
        await run_job(store, job_id)
        assert stubs["render_phase_called"] == 1
        st, jid, section_id = stubs["render_phase_args"]
        assert st is store
        assert jid == job_id
        assert section_id is None
        # render_phase 是 stub (no-op), 不該掉到 AWAITING_REVIEW
        assert store.get(job_id).state != JobState.AWAITING_REVIEW


# ---------------------------------------------------------------- TestIngestFailure


class TestIngestFailure:
    """_run_ingest raise → state FAILED + error="ingest 失敗: {e}" + early return.
    例外不該 propagate 出 task (asyncio unhandled exception 污染 log)."""

    @pytest.mark.asyncio
    async def test_failure_state_failed_with_prefix(self, store, make_job, stubs):
        """error 前綴 "ingest 失敗: " — debug grep / UI badge 依賴此格式,
        跟 "render 失敗: " / "unexpected: " 區分得出是哪階段炸的.
        """
        stubs["ingest_raise"] = RuntimeError("solve_pdf 炸了")
        job_id = make_job(require_review=True)
        await run_job(store, job_id)  # 不該 raise — try/except 吞掉
        rec = store.get(job_id)
        assert rec.state == JobState.FAILED
        assert rec.error.startswith("ingest 失敗: ")
        assert "solve_pdf 炸了" in rec.error

    @pytest.mark.asyncio
    async def test_failure_does_not_render(self, store, make_job, stubs):
        """ingest 失敗 → _run_render_phase 0 calls (早 return, render 不該跑)."""
        stubs["ingest_raise"] = RuntimeError("boom")
        job_id = make_job(require_review=False)  # 即便不需 review 也不該 render
        await run_job(store, job_id)
        assert stubs["render_phase_called"] == 0

    @pytest.mark.asyncio
    async def test_failure_stage_failed_original_msg(self, store, make_job, stubs):
        """stage[-1] state="failed" + error=原 msg (沒 "ingest 失敗" 前綴 —
        _end_stage_fail 收 str(e), 前綴只加在 record.error).
        """
        stubs["ingest_raise"] = ValueError("PDF 讀不到")
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        rec = store.get(job_id)
        assert rec.stages[0].state == "failed"
        assert rec.stages[0].error == "PDF 讀不到"

    @pytest.mark.asyncio
    async def test_failure_skips_review_pause(self, store, make_job, stubs):
        """require_review=True 但 ingest 先炸 → state FAILED 而非 AWAITING_REVIEW.

        鎖 ingest 失敗那條 return 在 review 分支之前 — 否則失敗 job 會錯誤地
        停在 awaiting_review 等用戶 approve 一個根本沒 ingest 成的 deck.
        """
        stubs["ingest_raise"] = RuntimeError("ingest 死")
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert store.get(job_id).state == JobState.FAILED


# ---------------------------------------------------------------- TestPostIngestHooks


class TestPostIngestHooks:
    """ingest 成功後兩個 hook (iter 42 intro 多樣化 / iter 48 時長估算) 各自
    try/except 吞例外 — 失敗只 warning, 絕不擋 awaiting_review."""

    @pytest.mark.asyncio
    async def test_rewrite_intros_called_with_source_type(self, store, make_job, stubs):
        """_rewrite_deck_intros_inplace 收 (store, job_id, source_type.value)."""
        job_id = make_job(source_type=SourceType.EXAM_PDF, require_review=True)
        await run_job(store, job_id)
        assert stubs["rewrite_called"] == 1
        st, jid, src_val = stubs["rewrite_args"]
        assert st is store
        assert jid == job_id
        assert src_val == "exam_pdf"  # rec.source_type.value, 不是 enum 物件

    @pytest.mark.asyncio
    async def test_log_duration_called_with_length_mode(self, store, make_job, stubs):
        """_log_deck_duration_estimate 收 (store, job_id, options.length_mode)."""
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert stubs["log_dur_called"] == 1
        st, jid, length_mode = stubs["log_dur_args"]
        assert st is store
        assert jid == job_id

    @pytest.mark.asyncio
    async def test_rewrite_exception_swallowed(self, store, make_job, stubs):
        """intro 多樣化炸 → job 仍走到 AWAITING_REVIEW (不擋, 不 FAILED).
        鎖 try/except 包住 hook, 不被偷拿掉 — deck.json 保留 ingest 原版即可.
        """
        stubs["rewrite_raise"] = RuntimeError("intro rewrite 炸")
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert store.get(job_id).state == JobState.AWAITING_REVIEW

    @pytest.mark.asyncio
    async def test_log_duration_exception_swallowed(self, store, make_job, stubs):
        """時長估算炸 → job 仍走到 AWAITING_REVIEW (估算只是參考, 不擋 review)."""
        stubs["log_dur_raise"] = RuntimeError("時長估算炸")
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert store.get(job_id).state == JobState.AWAITING_REVIEW


# ---------------------------------------------------------------- TestDeckPathUpdate


class TestDeckPathUpdate:
    """ingest 成功後 deck_path 設成 relative + forward slash (跨平台一致)."""

    @pytest.mark.asyncio
    async def test_deck_path_relative_forward_slash(self, store, make_job, stubs):
        """deck_path = "jobs/{id}/deck.json" — relative to root.parent, forward
        slash (前端 / API 拼路徑直接用, Windows 反斜線會 escape 亂).
        """
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        rec = store.get(job_id)
        assert rec.deck_path == f"jobs/{job_id}/deck.json"

    @pytest.mark.asyncio
    async def test_deck_path_no_backslash(self, store, make_job, stubs):
        """鎖 .replace("\\\\", "/") 真生效 — deck_path 不含反斜線 (即便 Windows)."""
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert "\\" not in store.get(job_id).deck_path


# ---------------------------------------------------------------- TestLogLifecycle


class TestLogLifecycle:
    """PR-4c per-job log 生命週期: entry attach + contextvar set, finally detach + reset."""

    @pytest.mark.asyncio
    async def test_attach_once_at_entry(self, store, make_job, stubs):
        """attach_job_log(job_id, jobs/<id>/log.jsonl) 被叫一次."""
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert len(stubs["attach_calls"]) == 1
        jid, log_path = stubs["attach_calls"][0]
        assert jid == job_id
        assert log_path.name == "log.jsonl"
        assert log_path.parent.name == job_id

    @pytest.mark.asyncio
    async def test_detach_once_in_finally_on_success(self, store, make_job, stubs):
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert stubs["detach_calls"] == [job_id]

    @pytest.mark.asyncio
    async def test_detach_on_ingest_failure(self, store, make_job, stubs):
        """ingest 失敗早 return → finally 仍 detach (鎖 cleanup 不被 early return 跳過)."""
        stubs["ingest_raise"] = RuntimeError("boom")
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert stubs["detach_calls"] == [job_id]

    @pytest.mark.asyncio
    async def test_contextvar_reset_after_completion(self, store, make_job, stubs):
        """run_job 結束後 current_job_id 該 reset 回 None (鎖 finally reset(token),
        否則下一個 task 的 log 會被掛到上一個 job_id).
        """
        assert current_job_id.get() is None  # 前置條件
        job_id = make_job(require_review=True)
        await run_job(store, job_id)
        assert current_job_id.get() is None


# ---------------------------------------------------------------- TestCatchAll


class TestCatchAll:
    """外層 catch-all 安全網: 任何沒被內層 handle 的例外 → state FAILED +
    error="unexpected: {e}". 防 asyncio task 噴未捕捉例外.

    注意: 正常情況 _run_render_phase 自己吞掉所有例外不會 propagate, 所以這層
    catch-all 是 defense-in-depth. 這裡 stub 讓 _run_render_phase raise 來逼出
    catch-all, 鎖住 "unexpected: " 前綴 (跟 ingest / render 失敗區分) + detach 仍跑.
    """

    @pytest.mark.asyncio
    async def test_unexpected_exception_state_failed_with_prefix(
        self, store, make_job, stubs
    ):
        stubs["render_phase_raise"] = RuntimeError("天外飛來一筆")
        job_id = make_job(require_review=False)  # 要走到 render_phase
        await run_job(store, job_id)  # 不該 propagate
        rec = store.get(job_id)
        assert rec.state == JobState.FAILED
        assert rec.error.startswith("unexpected: ")
        assert "天外飛來一筆" in rec.error

    @pytest.mark.asyncio
    async def test_detach_still_runs_on_unexpected(self, store, make_job, stubs):
        """catch-all 路徑也走 finally → detach + contextvar reset."""
        stubs["render_phase_raise"] = RuntimeError("boom")
        job_id = make_job(require_review=False)
        await run_job(store, job_id)
        assert stubs["detach_calls"] == [job_id]
        assert current_job_id.get() is None
