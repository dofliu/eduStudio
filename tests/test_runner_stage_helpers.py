"""server.runner._start_stage / _end_stage_ok / _end_stage_fail — iter 41 trio safety lock.

iter 41 上線後沒對應直接測試: JobStore.add_stage / update_last_stage 在
test_jobs_store.py TestStages 已覆蓋, 但 runner 內這三個 wrapper 的 value-add
(state literal "running"/"done"/"failed" 寫死 + started_at/ended_at 由 utc_now()
塞時間戳 + error 透傳) 從沒打 — 任何 refactor 不小心動 state 字串 / 漏設
timestamp / truncate error 訊息就直接上線, 跟 iter 111-128 同思路
(route / helper safety lock).

stage 狀態機是 UI / monitoring / log dispatch 共用 source of truth, 任一 wrapper
behaviour drift 都會讓 awaiting_review badge / final.mp4 progress bar / log
filter 失準 — 必須鎖住.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

import server.jobs as jobs_mod
from server.jobs import JobStore
from server.runner import _start_stage, _end_stage_ok, _end_stage_fail
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    SourceType,
)


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    """乾淨 JobStore — JobStore 內部 helpers 用 module-level JOBS_DIR (不是 self.root),
    跟 test_jobs_store.py 同 pattern.
    """
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


@pytest.fixture
def job_id(store: JobStore) -> str:
    """建一筆 PENDING job 拿 id, 給 stage 操作用."""
    rec = store.create(CreateJobRequest(
        source_type=SourceType.EXAM_PDF,
        source=JobSource(path="/fake.pdf"),
        options=JobOptions(),
    ))
    return rec.id


# ---------------------------------------------------------------- TestStartStage


class TestStartStage:
    """_start_stage 鎖: state="running" 字面值 + started_at tz-aware 接近 now + name 透傳."""

    def test_creates_stage_with_running_state(self, store, job_id):
        """state 寫死 "running" — 任何 refactor 改成 enum / 別的字串都該 fail."""
        _start_stage(store, job_id, "ingest")

        rec = store.get(job_id)
        assert len(rec.stages) == 1
        assert rec.stages[0].state == "running"

    def test_sets_started_at_to_recent_utc(self, store, job_id):
        """started_at 應該由 utc_now() 塞 tz-aware UTC, 在最近 5 秒內 — 鎖
        不被改成 datetime.utcnow() (naive) 或漏設.
        """
        before = datetime.now(timezone.utc)
        _start_stage(store, job_id, "render")
        after = datetime.now(timezone.utc)

        rec = store.get(job_id)
        sa = rec.stages[0].started_at
        assert sa is not None
        assert sa.tzinfo is not None, "started_at 必須 tz-aware (寫 ISO 帶 +00:00)"
        # 容忍 1 秒 IO 延遲
        assert before - timedelta(seconds=1) <= sa <= after + timedelta(seconds=1)

    def test_passes_through_name_verbatim(self, store, job_id):
        """name 不該被 normalize / lowercased — 鎖 caller 傳什麼存什麼."""
        _start_stage(store, job_id, "INGEST_REPO")

        rec = store.get(job_id)
        assert rec.stages[0].name == "INGEST_REPO"

    def test_does_not_set_ended_at_or_error(self, store, job_id):
        """剛 start 還沒結束, ended_at 跟 error 該保持 None — 鎖 wrapper 不偷
        早期填值 (否則 UI 看到 ended_at 會誤以為已結束).
        """
        _start_stage(store, job_id, "ingest")

        stage = store.get(job_id).stages[0]
        assert stage.ended_at is None
        assert stage.error is None

    def test_appends_multiple_stages_in_order(self, store, job_id):
        """連續 start 多 stage → 順序保留 (append 不該插中間 / 倒序). UI
        timeline 顯示 ingest → render → publish 依賴此順序.
        """
        _start_stage(store, job_id, "ingest")
        _start_stage(store, job_id, "render")
        _start_stage(store, job_id, "publish")

        names = [s.name for s in store.get(job_id).stages]
        assert names == ["ingest", "render", "publish"]


# ---------------------------------------------------------------- TestEndStageOk


class TestEndStageOk:
    """_end_stage_ok 鎖: state="done" + ended_at tz-aware + 不動既有欄位."""

    def test_sets_done_state_and_ended_at(self, store, job_id):
        """state→"done" + ended_at 接近 now, 鎖 wrapper value-add."""
        _start_stage(store, job_id, "ingest")
        before = datetime.now(timezone.utc)
        _end_stage_ok(store, job_id)
        after = datetime.now(timezone.utc)

        stage = store.get(job_id).stages[-1]
        assert stage.state == "done"
        assert stage.ended_at is not None
        assert stage.ended_at.tzinfo is not None
        assert before - timedelta(seconds=1) <= stage.ended_at <= after + timedelta(seconds=1)

    def test_preserves_name_started_at_and_no_error(self, store, job_id):
        """end_ok 不該動 name / started_at / error — JobStore.update_last_stage 用
        model_copy(update=...) 只改傳入欄位, 鎖此行為 (refactor 改成 model_dump+rebuild
        會偷洗掉沒在 fields 的欄位).
        """
        _start_stage(store, job_id, "render")
        original_started = store.get(job_id).stages[-1].started_at

        _end_stage_ok(store, job_id)

        stage = store.get(job_id).stages[-1]
        assert stage.name == "render"
        assert stage.started_at == original_started
        assert stage.error is None  # ok 路徑不該無中生有 error

    def test_no_stage_raises(self, store, job_id):
        """沒 stage 就 _end_stage_ok → 該 raise ValueError (透傳 JobStore 行為).
        wrapper 不該 swallow, 否則 caller bug 被靜默吃掉 (例: 漏叫 _start_stage).
        """
        with pytest.raises(ValueError, match="沒有 stage"):
            _end_stage_ok(store, job_id)


# ---------------------------------------------------------------- TestEndStageFail


class TestEndStageFail:
    """_end_stage_fail 鎖: state="failed" + ended_at + error 完整透傳."""

    def test_sets_failed_state_ended_at_and_error(self, store, job_id):
        """state→"failed" + ended_at + error 透傳, 三件事缺一不可."""
        _start_stage(store, job_id, "ingest")
        before = datetime.now(timezone.utc)
        _end_stage_fail(store, job_id, "Gemini API 429 rate limit")
        after = datetime.now(timezone.utc)

        stage = store.get(job_id).stages[-1]
        assert stage.state == "failed"
        assert stage.ended_at is not None
        assert stage.ended_at.tzinfo is not None
        assert before - timedelta(seconds=1) <= stage.ended_at <= after + timedelta(seconds=1)
        assert stage.error == "Gemini API 429 rate limit"

    def test_preserves_name_and_started_at(self, store, job_id):
        """fail 不該動 name / started_at — 同 ok 路徑, 鎖 model_copy 部分更新."""
        _start_stage(store, job_id, "render")
        original_started = store.get(job_id).stages[-1].started_at

        _end_stage_fail(store, job_id, "ffmpeg crashed")

        stage = store.get(job_id).stages[-1]
        assert stage.name == "render"
        assert stage.started_at == original_started

    def test_error_passthrough_multiline_and_unicode(self, store, job_id):
        """error 多行 / 中文 / stack trace 字元都該原樣存進 state.json,
        不該被 truncate / strip / re-encode (UI / log 需要完整訊息 debug).
        """
        err_msg = (
            "Traceback (most recent call last):\n"
            "  File 'pipeline.py', line 42, in render\n"
            "    raise RuntimeError('字型不存在: /usr/share/fonts/missing.ttf')\n"
            "RuntimeError: 字型不存在 — 跑了 1000 個 step 後在 step 87 炸了"
        )
        _start_stage(store, job_id, "render")
        _end_stage_fail(store, job_id, err_msg)

        stage = store.get(job_id).stages[-1]
        assert stage.error == err_msg

    def test_no_stage_raises(self, store, job_id):
        """沒 stage 就 _end_stage_fail → 該 raise ValueError (透傳).
        runner 內若漏叫 _start_stage 該即時暴露, 不該被 swallow.
        """
        with pytest.raises(ValueError, match="沒有 stage"):
            _end_stage_fail(store, job_id, "unrelated error")


# ---------------------------------------------------------------- TestSequence


class TestStageSequence:
    """完整 ingest→render 流程行為鎖 — 同 job 多個 stage 不互相污染."""

    def test_multiple_stages_only_last_one_updated(self, store, job_id):
        """start1 → end_ok → start2 → end_fail 後:
          - stages[0] 仍 state="done" (不該被第二 stage 的 fail 污染)
          - stages[1] state="failed" + error 對的
        鎖 update_last_stage 只動 stages[-1], 不誤動 stages[:-1].
        """
        _start_stage(store, job_id, "ingest")
        _end_stage_ok(store, job_id)
        _start_stage(store, job_id, "render")
        _end_stage_fail(store, job_id, "TTS quota exceeded")

        stages = store.get(job_id).stages
        assert len(stages) == 2

        assert stages[0].name == "ingest"
        assert stages[0].state == "done"
        assert stages[0].error is None

        assert stages[1].name == "render"
        assert stages[1].state == "failed"
        assert stages[1].error == "TTS quota exceeded"

    def test_started_at_le_ended_at(self, store, job_id):
        """started_at 該 ≤ ended_at — 防 utc_now() 被換掉變成假時間源 / 順序倒置."""
        _start_stage(store, job_id, "ingest")
        _end_stage_ok(store, job_id)

        stage = store.get(job_id).stages[-1]
        assert stage.started_at <= stage.ended_at
