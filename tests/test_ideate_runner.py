"""server.ideate_runner — run_ideate_async 行為測試 (iter 27 重寫)。

iter 26 的 yaml load + scheduler 已砍 (用戶反饋 UX 太繁瑣 + 排程使用機率低)。
這支只測 ad-hoc IdeateConfig dict 進 → metrics dict 出。

iter 33: 加 in-memory scan state + start_async_scan 測試。
"""
from __future__ import annotations

import asyncio

import pytest


class TestRunIdeateAsync:
    """run_ideate_async(config, ...) ad-hoc 模式 — mock run_ideate."""

    @pytest.fixture
    def sample_config(self):
        from core.ideate import IdeateConfig

        cfg: IdeateConfig = {
            "watched_folders": [
                {"path": "/tmp/x", "source_type": "auto", "scan_window_days": 14}
            ],
            "llm_model": "gemini-2.5-flash",
            "max_proposals_per_file": 3,
            "enabled": True,
        }
        return cfg

    @pytest.mark.asyncio
    async def test_happy_path_progress_parsed(self, sample_config, tmp_path, monkeypatch):
        """正常路徑: run_ideate 跑完, _progress callback 解析 metrics 到 result dict."""
        from server import ideate_runner

        def fake_run_ideate(config, store, out_path, progress=None, **kw):
            if progress:
                progress("[1/4] 掃 watched_folders ...")
                progress("      找到 5 個候選 PDF / md / txt")
                progress("      共產生 7 個提案 (dedupe 前)")
                progress("      dedupe 後剩 3 個新提案 (filtered 4 個)")
            return []
        monkeypatch.setattr(ideate_runner, "run_ideate", fake_run_ideate)

        result = await ideate_runner.run_ideate_async(
            sample_config,
            out_path=tmp_path / "p.json",
        )
        assert result["ok"] is True
        assert result["scanned"] == 5
        assert result["proposed"] == 7
        assert result["new"] == 3
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_run_ideate_raise_returns_not_ok(self, sample_config, tmp_path, monkeypatch):
        """run_ideate 拋 exception → 回 ok=False + error msg, 不重新 raise。"""
        from server import ideate_runner

        def fake_run_ideate(*a, **kw):
            raise RuntimeError("Gemini quota exhausted")
        monkeypatch.setattr(ideate_runner, "run_ideate", fake_run_ideate)

        result = await ideate_runner.run_ideate_async(
            sample_config,
            out_path=tmp_path / "p.json",
        )
        assert result["ok"] is False
        assert "quota" in (result["error"] or "")
        # 計數應為 0 (沒跑成功)
        assert result["scanned"] == 0
        assert result["proposed"] == 0
        assert result["new"] == 0

    @pytest.mark.asyncio
    async def test_partial_progress_before_raise(self, sample_config, tmp_path, monkeypatch):
        """run_ideate 跑到一半 (有部分 progress) 才 raise — metrics 保留已知值."""
        from server import ideate_runner

        def fake_run_ideate(config, store, out_path, progress=None, **kw):
            if progress:
                progress("      找到 2 個候選 PDF / md / txt")
            raise RuntimeError("network down")
        monkeypatch.setattr(ideate_runner, "run_ideate", fake_run_ideate)

        result = await ideate_runner.run_ideate_async(
            sample_config,
            out_path=tmp_path / "p.json",
        )
        assert result["ok"] is False
        assert result["scanned"] == 2   # 已知值保留
        assert "network down" in (result["error"] or "")


class TestScanState:
    """iter 33: in-memory scan state for progress tracking."""

    def test_new_scan_id_is_hex(self):
        from server.ideate_runner import _new_scan_id
        scan_id = _new_scan_id()
        assert len(scan_id) == 12
        assert all(c in "0123456789abcdef" for c in scan_id)

    def test_unknown_scan_id_returns_none(self):
        from server.ideate_runner import get_scan_state
        assert get_scan_state("definitely_not_real_xx") is None

    def test_init_state_running(self):
        from server.ideate_runner import _init_scan_state, get_scan_state

        sid = "abc123"
        _init_scan_state(sid)
        state = get_scan_state(sid)
        assert state is not None
        assert state["state"] == "running"
        assert state["scanned"] == 0
        assert state["started_at"] is not None
        assert state["ended_at"] is None

    def test_update_then_get(self):
        from server.ideate_runner import (
            _init_scan_state, _update_scan_state, get_scan_state,
        )

        sid = "def456"
        _init_scan_state(sid)
        _update_scan_state(sid, scanned=5, proposed=3, message="...")
        state = get_scan_state(sid)
        assert state["scanned"] == 5
        assert state["proposed"] == 3
        assert state["message"] == "..."

    def test_finish_state_done(self):
        from server.ideate_runner import (
            _finish_scan_state, _init_scan_state, get_scan_state,
        )

        sid = "ghi789"
        _init_scan_state(sid)
        _finish_scan_state(sid, state="done")
        state = get_scan_state(sid)
        assert state["state"] == "done"
        assert state["ended_at"] is not None

    def test_finish_state_failed_with_error(self):
        from server.ideate_runner import (
            _finish_scan_state, _init_scan_state, get_scan_state,
        )

        sid = "jkl012"
        _init_scan_state(sid)
        _finish_scan_state(sid, state="failed", error="API limit")
        state = get_scan_state(sid)
        assert state["state"] == "failed"
        assert state["error"] == "API limit"


class TestAsyncScan:
    """start_async_scan — fire-and-forget background task."""

    @pytest.mark.asyncio
    async def test_start_async_scan_returns_id_and_runs(self, monkeypatch):
        from server import ideate_runner

        # mock run_ideate 立刻完成
        def fake_run_ideate(config, store, out_path, progress=None, **kw):
            if progress:
                progress("      找到 3 個候選 PDF / md / txt")
                progress("      共產生 5 個提案 (dedupe 前)")
                progress("      dedupe 後剩 2 個新提案")
            return []
        monkeypatch.setattr(ideate_runner, "run_ideate", fake_run_ideate)

        config = {
            "watched_folders": [{"path": "/tmp", "source_type": "auto", "scan_window_days": 14}],
            "llm_model": "x",
            "max_proposals_per_file": 3,
            "enabled": True,
        }
        scan_id = ideate_runner.start_async_scan(config)
        assert len(scan_id) == 12

        # 等 background task 跑完 (run_ideate 是 sync 不阻塞 event loop 但要讓 task 排期)
        await asyncio.sleep(0.1)

        state = ideate_runner.get_scan_state(scan_id)
        assert state is not None
        assert state["state"] in ("done", "running")  # 視 timing
        # 即使還 running, 進度應該 reflect 至少 scan
        # 等更久確保 done
        for _ in range(20):
            await asyncio.sleep(0.05)
            state = ideate_runner.get_scan_state(scan_id)
            if state["state"] != "running":
                break
        assert state["state"] == "done"
        assert state["scanned"] == 3
        assert state["proposed"] == 5
        assert state["new"] == 2

    @pytest.mark.asyncio
    async def test_async_scan_failure_marks_failed(self, monkeypatch):
        from server import ideate_runner

        def fake_run_ideate(*a, **kw):
            raise RuntimeError("Gemini down")
        monkeypatch.setattr(ideate_runner, "run_ideate", fake_run_ideate)

        config = {
            "watched_folders": [{"path": "/tmp", "source_type": "auto", "scan_window_days": 14}],
            "llm_model": "x",
            "max_proposals_per_file": 3,
            "enabled": True,
        }
        scan_id = ideate_runner.start_async_scan(config)
        # 等 task 跑完
        for _ in range(20):
            await asyncio.sleep(0.05)
            state = ideate_runner.get_scan_state(scan_id)
            if state and state["state"] != "running":
                break
        assert state["state"] == "failed"
        assert "Gemini down" in (state["error"] or "")
