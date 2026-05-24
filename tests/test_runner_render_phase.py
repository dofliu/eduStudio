"""server.runner._run_render_phase — iter PR-3j / PR-4a / PR-4c orchestrator 安全鎖.

_run_render_phase 是 awaiting_review → render → done 主入口 (也供 /approve +
schedule_section_render 共用). 從 PR-3a 上線後沒對應直接測試 — value-add 全在
這層 wrapper:

  - PR-3j: 進入時 store.update(state=RENDERING, error=None) 把 FAILED retry 留
    下的 stale error 清掉. 不清會讓成功後 record.error 還掛上次失敗訊息, UI
    誤判又紅
  - PR-4a: stage_name = "render-section-{section_id}" if section_id else "render"
    讓 UI / log filter 分得出哪一章在跑
  - PR-4c: own_log gate — schedule_section_render 進來時 current_job_id 還沒
    set, 自己 attach log file; run_job 已 attach 過則不重 attach (避免 handler
    重複 + double-write)
  - 例外吞: _run_render 任一 raise → state FAILED + error="render 失敗: {msg}"
    + _end_stage_fail, **不該** propagate 出 task 讓 asyncio 噴未捕捉錯誤
  - 成功: refresh_artifacts → state DONE + error=None (清掉之前 retry) +
    output_dir 設成 "jobs/{id}/artifacts" forward slash
  - finally: own_log=True 才 reset contextvar + detach (重複 detach 不安全)

任何 refactor 動 state 字串 / 例外傳播 / stage_name 模板 / own_log 條件就直接
上線, 跟 iter 111-132 同思路 (route / helper safety lock).

策略 = monkeypatch server.runner._run_render 成 async stub, 在 stub 內 snapshot
store.get(job_id) 證明 entry 時 error 已被清; monkeypatch attach_job_log /
detach_job_log 計次驗 own_log gate. 不真跑渲染 / ffmpeg / TTS.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import server.jobs as jobs_mod
import server.runner as runner_mod
from core.logging_setup import current_job_id
from server.jobs import JobStore
from server.runner import _run_render_phase
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
    """乾淨 JobStore — 跟 test_runner_stage_helpers / test_jobs_store 同 pattern.
    monkeypatch module-level JOBS_DIR, 不然 artifact / log path 仍指向真實 jobs/.
    """
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


@pytest.fixture
def job_id(store: JobStore) -> str:
    """建一筆 EXAM_PDF job + artifacts 目錄 (refresh_artifacts 不會炸)."""
    rec = store.create(CreateJobRequest(
        source_type=SourceType.EXAM_PDF,
        source=JobSource(path="/fake.pdf"),
        options=JobOptions(),
    ))
    store.artifacts_dir(rec.id).mkdir(parents=True, exist_ok=True)
    return rec.id


@pytest.fixture
def stub_render(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stub _run_render — 預設 no-op 成功. 可設 state['raise'] = Exception 模擬失敗.

    snapshot store/rec/section_id 跟 mid-call store state (證明 error=None 已套).
    """
    state: dict = {
        "called": 0,
        "store": None,
        "rec": None,
        "section_id": None,
        "mid_call_state": None,
        "mid_call_error": None,
        "raise": None,
    }

    async def fake_run_render(store, rec, *, section_id=None):
        state["called"] += 1
        state["store"] = store
        state["rec"] = rec
        state["section_id"] = section_id
        # 在 _run_render 執行瞬間 snapshot store 內 record state — 證明 entry
        # 時 store.update(state=RENDERING, error=None) 已落地
        cur = store.get(rec.id)
        state["mid_call_state"] = cur.state
        state["mid_call_error"] = cur.error
        if state["raise"] is not None:
            raise state["raise"]

    monkeypatch.setattr(runner_mod, "_run_render", fake_run_render)
    return state


@pytest.fixture
def stub_log_handlers(monkeypatch: pytest.MonkeyPatch) -> dict:
    """攔截 attach_job_log / detach_job_log — 不真開 FileHandler, 計次驗 own_log gate."""
    state: dict = {"attach_calls": [], "detach_calls": []}

    def fake_attach(jid: str, log_path: Path) -> None:
        state["attach_calls"].append((jid, log_path))

    def fake_detach(jid: str) -> None:
        state["detach_calls"].append(jid)

    monkeypatch.setattr(runner_mod, "attach_job_log", fake_attach)
    monkeypatch.setattr(runner_mod, "detach_job_log", fake_detach)
    return state


# ---------------------------------------------------------------- TestSuccessPath


class TestSuccessPath:
    """happy path: PENDING → RENDERING → DONE, error=None, output_dir 設好, stage done."""

    @pytest.mark.asyncio
    async def test_state_transitions_to_done(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.state == JobState.DONE

    @pytest.mark.asyncio
    async def test_output_dir_set_relative_with_forward_slashes(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """output_dir = '<root.name>/<job_id>/artifacts', forward slash even on Windows.

        鎖 .replace('\\\\', '/') 跨平台 path 一致性 — 前端 / YT description 拼
        URL 直接用, 反斜線會 escape 亂.
        """
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.output_dir == f"jobs/{job_id}/artifacts"
        assert "\\" not in rec.output_dir

    @pytest.mark.asyncio
    async def test_stale_error_cleared_on_entry(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """PR-3j: 進入時 error=None 該被清掉 — FAILED retry 路徑非常重要.

        鎖 store.update(state=RENDERING, error=None) 不被偷拿掉 error=None,
        否則成功 done 後 record.error 仍掛上次失敗訊息.
        """
        store.update(job_id, state=JobState.FAILED, error="render 失敗: 上次 ffmpeg 炸")
        await _run_render_phase(store, job_id)
        # mid-call snapshot 證明 _run_render 看到 error 已被清
        assert stub_render["mid_call_state"] == JobState.RENDERING
        assert stub_render["mid_call_error"] is None
        # done 後仍是 None
        rec = store.get(job_id)
        assert rec.error is None

    @pytest.mark.asyncio
    async def test_done_clears_error_again(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """成功 done 那次 store.update(state=DONE, error=None) 第二段防護 — 即便
        entry 漏清, 成功路徑也要保證 error=None. 雙閘比單閘穩, 不可被改成只 set state.
        """
        store.update(job_id, state=JobState.FAILED, error="stale")
        await _run_render_phase(store, job_id)
        assert store.get(job_id).error is None

    @pytest.mark.asyncio
    async def test_stage_recorded_done(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """成功路徑該有一個 stage entry, name="render", state="done"."""
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert len(rec.stages) == 1
        assert rec.stages[0].name == "render"
        assert rec.stages[0].state == "done"
        assert rec.stages[0].error is None

    @pytest.mark.asyncio
    async def test_run_render_called_with_section_id_none(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """預設 section_id=None 該透傳給 _run_render (不被改成空字串 / 'all')."""
        await _run_render_phase(store, job_id)
        assert stub_render["called"] == 1
        assert stub_render["section_id"] is None
        # store 跟 rec 都透傳
        assert stub_render["store"] is store
        assert stub_render["rec"].id == job_id


# ---------------------------------------------------------------- TestFailurePath


class TestFailurePath:
    """_run_render raise → state FAILED + error="render 失敗: {msg}" + stage failed,
    例外不該 propagate 出 task (asyncio 噴 unhandled exception 會污染 log)."""

    @pytest.mark.asyncio
    async def test_runtime_error_caught_state_failed(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        stub_render["raise"] = RuntimeError("ffmpeg 沒裝")
        # 不該 raise — try/except 在 _run_render_phase 內吞掉
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.state == JobState.FAILED

    @pytest.mark.asyncio
    async def test_error_message_has_prefix(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """error="render 失敗: {orig msg}" — 前綴鎖, debug grep / UI badge 依賴此格式."""
        stub_render["raise"] = RuntimeError("ffmpeg 沒裝")
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.error is not None
        assert rec.error.startswith("render 失敗: ")
        assert "ffmpeg 沒裝" in rec.error

    @pytest.mark.asyncio
    async def test_value_error_also_caught(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """except 範圍夠寬 — 不只擋 RuntimeError, schemas validation / json 錯也吞.
        鎖 except Exception 不被偷改成 except RuntimeError 只擋特定型別.
        """
        stub_render["raise"] = ValueError("deck.json 格式錯")
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.state == JobState.FAILED
        assert "deck.json 格式錯" in rec.error

    @pytest.mark.asyncio
    async def test_stage_recorded_failed_with_error(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """stage[-1] state="failed" + error 透傳原 msg (不被 render 失敗 prefix 污染)."""
        stub_render["raise"] = RuntimeError("某個內部錯")
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert len(rec.stages) == 1
        assert rec.stages[0].state == "failed"
        # _end_stage_fail(store, job_id, str(e)) — stage error 是原 msg, 沒前綴
        assert rec.stages[0].error == "某個內部錯"


# ---------------------------------------------------------------- TestStageName


class TestStageName:
    """PR-4a stage_name dispatch — section_id 有無切換命名格式."""

    @pytest.mark.asyncio
    async def test_no_section_id_stage_name_render(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        await _run_render_phase(store, job_id)
        rec = store.get(job_id)
        assert rec.stages[0].name == "render"

    @pytest.mark.asyncio
    async def test_with_section_id_stage_name_prefixed(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """section_id="q1" → stage name "render-section-q1" — 鎖 f-string 模板
        不被改成 "render-{q1}" / "section-q1" / 等其他變體, UI 解析依賴此前綴.
        """
        await _run_render_phase(store, job_id, section_id="q1")
        rec = store.get(job_id)
        assert rec.stages[0].name == "render-section-q1"

    @pytest.mark.asyncio
    async def test_section_id_propagated_to_run_render(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """section_id 該以 kwarg 透傳給 _run_render, 不被偷改成 positional / 拿掉."""
        await _run_render_phase(store, job_id, section_id="ch_intro")
        assert stub_render["section_id"] == "ch_intro"
        # stage name 對齊
        rec = store.get(job_id)
        assert rec.stages[0].name == "render-section-ch_intro"


# ---------------------------------------------------------------- TestLoggerDispatch


class TestLoggerDispatch:
    """logger.info 訊息分流: section vs 整份 — 維運 grep log 該分得出來."""

    @pytest.mark.asyncio
    async def test_full_render_logs_zhengfen(
        self, store, job_id, stub_render, stub_log_handlers, caplog
    ):
        with caplog.at_level(logging.INFO, logger="server.runner"):
            await _run_render_phase(store, job_id)
        msgs = [r.getMessage() for r in caplog.records]
        assert any("render 開始 (整份)" in m for m in msgs)
        assert any("render 完成" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_section_render_logs_section_id(
        self, store, job_id, stub_render, stub_log_handlers, caplog
    ):
        """section_id="q1" 路徑該記 section_id 進 log, 不是「整份」字串."""
        with caplog.at_level(logging.INFO, logger="server.runner"):
            await _run_render_phase(store, job_id, section_id="q1")
        msgs = [r.getMessage() for r in caplog.records]
        assert any("section_id=q1" in m for m in msgs)
        # 嚴格排除「整份」, 防被合併成同一條訊息
        assert not any("(整份)" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_failure_logs_render_shibai(
        self, store, job_id, stub_render, stub_log_handlers, caplog
    ):
        """例外路徑 logger.exception("render 失敗") — 鎖訊息字串 + ERROR level."""
        stub_render["raise"] = RuntimeError("boom")
        with caplog.at_level(logging.ERROR, logger="server.runner"):
            await _run_render_phase(store, job_id)
        err_msgs = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("render 失敗" in m for m in err_msgs)


# ---------------------------------------------------------------- TestOwnLogGate


class TestOwnLogGate:
    """PR-4c: 從 schedule_section_render 進來時 current_job_id 未 set, 自己 attach;
    從 run_job 進來 (contextvar 已 set 同 job_id) 則不重 attach, 避免 handler 重複."""

    @pytest.mark.asyncio
    async def test_attaches_when_contextvar_unset(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """current_job_id 預設 None → own_log=True → attach 該被叫一次."""
        await _run_render_phase(store, job_id)
        assert len(stub_log_handlers["attach_calls"]) == 1
        jid, log_path = stub_log_handlers["attach_calls"][0]
        assert jid == job_id
        # log_path = jobs/<id>/log.jsonl
        assert log_path.name == "log.jsonl"
        assert log_path.parent.name == job_id
        # finally 該 detach 一次
        assert stub_log_handlers["detach_calls"] == [job_id]

    @pytest.mark.asyncio
    async def test_skips_attach_when_contextvar_already_set_to_same_job(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """current_job_id 已是同 job_id (run_job 上層 attach 過) → own_log=False →
        不該再 attach, 不該再 detach (run_job 那層 finally 會自己 detach).

        若改成總是 attach, 同 job 會有兩個 FileHandler, log.jsonl 每行寫兩次.
        """
        token = current_job_id.set(job_id)
        try:
            await _run_render_phase(store, job_id)
            assert stub_log_handlers["attach_calls"] == []
            assert stub_log_handlers["detach_calls"] == []
        finally:
            current_job_id.reset(token)

    @pytest.mark.asyncio
    async def test_attaches_when_contextvar_set_to_different_job(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """current_job_id != job_id (理論上不該發生, 但防呆) → own_log=True 仍 attach.
        鎖 own_log = current_job_id.get() != job_id 條件, 不被偷改成 is None check.
        """
        token = current_job_id.set("other_job")
        try:
            await _run_render_phase(store, job_id)
            assert len(stub_log_handlers["attach_calls"]) == 1
            assert stub_log_handlers["attach_calls"][0][0] == job_id
            assert stub_log_handlers["detach_calls"] == [job_id]
        finally:
            current_job_id.reset(token)

    @pytest.mark.asyncio
    async def test_finally_detaches_on_exception(
        self, store, job_id, stub_render, stub_log_handlers
    ):
        """_run_render raise → 仍該走 finally → detach (own_log=True 那條).
        鎖 finally cleanup, 否則失敗 job 累積 FileHandler 沒 close FD 洩漏.
        """
        stub_render["raise"] = RuntimeError("失敗也要 cleanup")
        await _run_render_phase(store, job_id)
        # 失敗仍 attach + detach 一次
        assert len(stub_log_handlers["attach_calls"]) == 1
        assert stub_log_handlers["detach_calls"] == [job_id]
