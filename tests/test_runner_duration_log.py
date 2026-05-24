"""server.runner._log_deck_duration_estimate — iter 48 IO wrapper 安全鎖.

iter 48 上線後沒對應直接測試: 核心 `estimate_deck_duration` 純函式 +
`check_deck_narration_lengths` / `format_validation_report` 都在各自
module 有覆蓋, 但 runner 內這層 IO + log dispatch wrapper (deck.json
讀 → 兩段算 → logger.info / warning 分流) 從沒打 — 任何 refactor 不
小心動「沒檔不該炸」防呆 / over_budget 該走 warning 不該被偷改 /
narration_validator 例外不該擋流程 / length_mode 該透傳 → 直接上線.
跟 iter 111-124 同思路 (route / helper safety lock).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from server.jobs import JobStore
from server.runner import _log_deck_duration_estimate


@pytest.fixture
def store_with_job(tmp_path):
    """空 JobStore + 預建 job 目錄 (deck.json 由各 test 自決定要不要寫)."""
    store = JobStore(root=tmp_path)
    job_id = "job_test"
    (tmp_path / job_id).mkdir()
    return store, job_id


def _write_deck(store: JobStore, job_id: str, deck: dict) -> None:
    store.deck_path(job_id).write_text(
        json.dumps(deck, ensure_ascii=False), encoding="utf-8",
    )


def _sections_deck(narrations: list[str]) -> dict:
    """deck (sections) schema 最小可估時長 deck.

    narrations 內每個字串對應一個 slide.
    """
    return {
        "deck_title": "測試 deck",
        "sections": [
            {
                "id": "intro",
                "slides": [
                    {"id": f"intro_{i + 1}", "narration": n}
                    for i, n in enumerate(narrations)
                ],
            },
        ],
    }


def _problems_deck(narrations: list[str]) -> dict:
    """v1 exam schema 最小可估時長 deck (problems / steps)."""
    return {
        "exam_title": "材料力學 期中考",
        "problems": [
            {
                "id": "q1",
                "steps": [
                    {"display": "x", "narration": n} for n in narrations
                ],
            },
        ],
    }


class TestNoOpPath:
    """檔不存在 — 不該炸, 不該誤建檔, 不該噴 log."""

    def test_missing_deck_json_is_silent_noop(self, store_with_job, caplog):
        store, job_id = store_with_job
        # 不寫 deck.json
        with caplog.at_level(logging.INFO, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "quick")
        assert not store.deck_path(job_id).exists()
        # 完全沒 log — 跟 deck 寫過後的「deck 估算: ...」做出區別
        assert not any("deck 估算" in r.message for r in caplog.records)


class TestUnderBudget:
    """字數在預算內 — 走 logger.info, 不走 warning (UI 看 log 不該紅)."""

    def test_short_narration_logs_info_not_warning(self, store_with_job, caplog):
        store, job_id = store_with_job
        # quick mode 預算 2500 字, 寫 100 字以內絕對 under
        _write_deck(store, job_id, _sections_deck(["短"]))

        with caplog.at_level(logging.DEBUG, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "quick")

        info_msgs = [r for r in caplog.records if r.levelno == logging.INFO
                     and "deck 估算" in r.message]
        warn_msgs = [r for r in caplog.records if r.levelno == logging.WARNING
                     and "deck 估算" in r.message]
        assert len(info_msgs) == 1
        assert len(warn_msgs) == 0
        # 訊息該含關鍵欄位 (sections / slides / chars / 分鐘 / 預算 / 模式)
        msg = info_msgs[0].message
        assert "1 sections" in msg
        assert "1 slides" in msg
        assert "quick" in msg


class TestOverBudget:
    """字數超出預算 — 走 logger.warning + ⚠ + 超出百分比."""

    def test_over_budget_logs_warning_with_overshoot(self, store_with_job, caplog):
        store, job_id = store_with_job
        # ultra_quick 預算 900 字, 寫 2000+ 字確保超出
        _write_deck(store, job_id, _sections_deck(["啊" * 2000]))

        with caplog.at_level(logging.WARNING, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "ultra_quick")

        warn_msgs = [r for r in caplog.records if r.levelno == logging.WARNING
                     and "deck 估算" in r.message]
        assert len(warn_msgs) == 1
        # warning 該帶 ⚠ + 超出 % (給用戶一眼看到超多少)
        formatted = warn_msgs[0].getMessage()
        assert "⚠" in formatted
        assert "超出預算" in formatted


class TestLengthModePassthrough:
    """length_mode 該真透傳給 estimate_deck_duration (不是寫死 quick)."""

    def test_lecture_mode_has_larger_budget_than_ultra_quick(
        self, store_with_job, caplog,
    ):
        """同樣 narration 字數 (1500 字), ultra_quick 該超 / lecture 該不超 —
        驗 preset budget 真的依 length_mode 切換, 不是寫死 quick."""
        store, job_id = store_with_job
        _write_deck(store, job_id, _sections_deck(["啊" * 1500]))

        # ultra_quick budget 900 → 1500 字該超 → warning
        with caplog.at_level(logging.WARNING, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "ultra_quick")
        assert any(r.levelno == logging.WARNING and "deck 估算" in r.message
                   for r in caplog.records)

        caplog.clear()

        # lecture budget 應遠大於 1500 → info
        with caplog.at_level(logging.INFO, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "lecture")
        warn_after = [r for r in caplog.records if r.levelno == logging.WARNING
                      and "deck 估算" in r.message]
        info_after = [r for r in caplog.records if r.levelno == logging.INFO
                      and "deck 估算" in r.message]
        assert len(warn_after) == 0, "lecture mode 1500 字不該超預算"
        assert len(info_after) == 1
        assert "lecture" in info_after[0].message

    def test_none_length_mode_defaults_to_quick_label(self, store_with_job, caplog):
        """length_mode=None 該 fallback 走 quick (msg 顯示 'quick mode')
        不該炸 / 不該顯示 'None mode'."""
        store, job_id = store_with_job
        _write_deck(store, job_id, _sections_deck(["短"]))

        with caplog.at_level(logging.INFO, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, None)

        msgs = [r.message for r in caplog.records if "deck 估算" in r.message]
        assert len(msgs) == 1
        assert "quick" in msgs[0]
        assert "None" not in msgs[0]


class TestSchemaDispatch:
    """estimate_deck_duration 透傳兩種 schema — 透過 wrapper 確保 IO 層沒
    把哪邊壓平 / 漏 dispatch."""

    def test_problems_schema_counts_steps(self, store_with_job, caplog):
        store, job_id = store_with_job
        _write_deck(store, job_id, _problems_deck(["短" * 10, "短" * 20]))

        with caplog.at_level(logging.INFO, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "quick")

        msg = next(r.message for r in caplog.records if "deck 估算" in r.message)
        # problems schema 該被 estimate_deck_duration 認, 算成 1 sections / 2 slides
        assert "1 sections" in msg
        assert "2 slides" in msg

    def test_sections_schema_counts_slides(self, store_with_job, caplog):
        store, job_id = store_with_job
        _write_deck(store, job_id, _sections_deck(["a", "b", "c"]))

        with caplog.at_level(logging.INFO, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "quick")

        msg = next(r.message for r in caplog.records if "deck 估算" in r.message)
        assert "1 sections" in msg
        assert "3 slides" in msg


class TestNarrationValidatorIntegration:
    """第二段 (per-slide narration_validator) 該也跑 — 不是只跑 estimate."""

    def test_per_slide_over_budget_logs_warning(self, store_with_job, caplog):
        """ultra_quick mode narration_chars_range 上限 80 — 寫一 slide 200 字
        該被 narration_validator 抓出 over_budget_count > 0 → warning.

        注意: 200 字仍在 ultra_quick budget 900 內, 所以 estimate 那段走
        INFO 不走 warning — 這 test 只鎖第二段 (per-slide validator) 該
        獨立跑出 warning, 不該被合進 estimate 那段."""
        store, job_id = store_with_job
        _write_deck(store, job_id, _sections_deck(["啊" * 200]))

        with caplog.at_level(logging.INFO, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "ultra_quick")

        warn_msgs = [r.getMessage() for r in caplog.records
                     if r.levelno == logging.WARNING]
        info_msgs = [r.getMessage() for r in caplog.records
                     if r.levelno == logging.INFO]
        # estimate 那段該 info (200 < 900 budget)
        assert any("deck 估算" in m for m in info_msgs)
        # validator 那段該 warning (200 > 80 per-slide)
        assert any("narration 長度驗證" in m for m in warn_msgs)

    def test_per_slide_under_budget_logs_info(self, store_with_job, caplog):
        """全 slide 都在範圍內 — 該走 info 不該誤紅."""
        store, job_id = store_with_job
        _write_deck(store, job_id, _sections_deck(["短"]))

        with caplog.at_level(logging.INFO, logger="server.runner"):
            _log_deck_duration_estimate(store, job_id, "quick")

        info_msgs = [r.getMessage() for r in caplog.records
                     if r.levelno == logging.INFO]
        warn_msgs = [r.getMessage() for r in caplog.records
                     if r.levelno == logging.WARNING]
        assert any("narration 長度驗證" in m for m in info_msgs)
        assert not any("narration 長度驗證" in m for m in warn_msgs)


class TestValidatorExceptionDoesNotPropagate:
    """check_deck_narration_lengths raise 該被 try/except 吞 — 不擋主流程.

    第一段 estimate 仍該成功 log; 第二段失敗該走 logger.exception 不該
    讓 caller (run_job) 整個炸掉."""

    def test_validator_exception_swallowed_with_log(
        self, store_with_job, caplog, monkeypatch,
    ):
        store, job_id = store_with_job
        _write_deck(store, job_id, _sections_deck(["短"]))

        def _boom(*a, **kw):
            raise RuntimeError("validator 故障模擬")

        # patch 進 narration_validator module — runner 是 try 內 import,
        # 動到 source module 就會被抓
        monkeypatch.setattr(
            "core.narration_validator.check_deck_narration_lengths", _boom,
        )

        with caplog.at_level(logging.ERROR, logger="server.runner"):
            # 不該 raise — try/except 該吞
            _log_deck_duration_estimate(store, job_id, "quick")

        # logger.exception 該留紀錄 + 含「不擋流程」字串 (給用戶看出是 graceful)
        err_msgs = [r.getMessage() for r in caplog.records
                    if r.levelno == logging.ERROR]
        assert any("narration 長度驗證失敗" in m and "不擋流程" in m
                   for m in err_msgs)
