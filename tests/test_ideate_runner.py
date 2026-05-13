"""server.ideate_runner — run_ideate_async 行為測試 (iter 27 重寫)。

iter 26 的 yaml load + scheduler 已砍 (用戶反饋 UX 太繁瑣 + 排程使用機率低)。
這支只測 ad-hoc IdeateConfig dict 進 → metrics dict 出。
"""
from __future__ import annotations

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
