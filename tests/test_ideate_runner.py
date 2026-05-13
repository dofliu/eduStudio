"""server.ideate_runner — yaml load + run_from_yaml + scheduler 行為測試。"""
from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("yaml", reason="需要 PyYAML 安裝")


class TestLoadIdeateConfigYaml:
    def test_missing_file_returns_none(self, tmp_path):
        from server.ideate_runner import load_ideate_config_yaml

        cfg, interval = load_ideate_config_yaml(tmp_path / "missing.yaml")
        assert cfg is None
        assert interval == 0

    def test_corrupt_yaml_returns_none(self, tmp_path):
        from server.ideate_runner import load_ideate_config_yaml

        p = tmp_path / "bad.yaml"
        p.write_text("not valid yaml: : :\n  - [\n", encoding="utf-8")
        cfg, interval = load_ideate_config_yaml(p)
        assert cfg is None
        assert interval == 0

    def test_disabled_returns_none(self, tmp_path):
        from server.ideate_runner import load_ideate_config_yaml

        p = tmp_path / "disabled.yaml"
        p.write_text("enabled: false\nwatched_folders: []\n", encoding="utf-8")
        cfg, interval = load_ideate_config_yaml(p)
        assert cfg is None
        assert interval == 0

    def test_minimal_valid_yaml(self, tmp_path):
        from server.ideate_runner import load_ideate_config_yaml

        p = tmp_path / "cfg.yaml"
        p.write_text(
            "enabled: true\n"
            "watched_folders:\n"
            "  - path: /tmp/x\n"
            "    source_type: auto\n"
            "    scan_window_days: 14\n"
            "auto_scan_interval_hours: 6\n",
            encoding="utf-8",
        )
        cfg, interval = load_ideate_config_yaml(p)
        assert cfg is not None
        assert len(cfg["watched_folders"]) == 1
        assert cfg["watched_folders"][0]["source_type"] == "auto"
        assert cfg["max_proposals_per_file"] == 3   # 預設值
        assert cfg["llm_model"] == "gemini-2.5-flash"
        assert interval == 6

    def test_negative_interval_clamped_to_zero(self, tmp_path):
        from server.ideate_runner import load_ideate_config_yaml

        p = tmp_path / "cfg.yaml"
        p.write_text(
            "enabled: true\nwatched_folders: []\nauto_scan_interval_hours: -3\n",
            encoding="utf-8",
        )
        cfg, interval = load_ideate_config_yaml(p)
        assert cfg is not None
        assert interval == 0


class TestRunFromYaml:
    """跑 run_ideate_from_yaml 整合 — mock run_ideate 不真打 Gemini。"""

    @pytest.fixture
    def yaml_cfg(self, tmp_path):
        p = tmp_path / "cfg.yaml"
        p.write_text(
            "enabled: true\n"
            "watched_folders:\n"
            "  - path: /tmp/x\n"
            "    source_type: auto\n"
            "    scan_window_days: 14\n",
            encoding="utf-8",
        )
        return p

    @pytest.mark.asyncio
    async def test_missing_config_returns_not_ok(self, tmp_path):
        from server.ideate_runner import run_ideate_from_yaml

        result = await run_ideate_from_yaml(
            config_path=tmp_path / "nope.yaml",
            out_path=tmp_path / "p.json",
        )
        assert result["ok"] is False
        assert "ideate_config.yaml 不存在" in (result["error"] or "")

    @pytest.mark.asyncio
    async def test_happy_path_with_mock_run_ideate(self, yaml_cfg, tmp_path, monkeypatch):
        """正常路徑: yaml ok → run_ideate 跑完回 metrics."""
        from server import ideate_runner

        # mock run_ideate 模擬 progress 訊息 (給 _progress 解析)
        def fake_run_ideate(config, store, out_path, progress=None, **kw):
            if progress:
                progress("[1/4] 掃 watched_folders ...")
                progress("      找到 2 個候選 PDF / md / txt")
                progress("      共產生 3 個提案 (dedupe 前)")
                progress("      dedupe 後剩 1 個新提案 (filtered 2 個)")
            return []
        monkeypatch.setattr(ideate_runner, "run_ideate", fake_run_ideate)

        result = await ideate_runner.run_ideate_from_yaml(
            config_path=yaml_cfg,
            out_path=tmp_path / "p.json",
        )
        assert result["ok"] is True
        assert result["scanned"] == 2
        assert result["proposed"] == 3
        assert result["new"] == 1
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_run_ideate_raise_returns_not_ok(self, yaml_cfg, tmp_path, monkeypatch):
        """run_ideate 拋 exception → 回 ok=False + error msg."""
        from server import ideate_runner

        def fake_run_ideate(*a, **kw):
            raise RuntimeError("Gemini quota exhausted")
        monkeypatch.setattr(ideate_runner, "run_ideate", fake_run_ideate)

        result = await ideate_runner.run_ideate_from_yaml(
            config_path=yaml_cfg,
            out_path=tmp_path / "p.json",
        )
        assert result["ok"] is False
        assert "quota" in (result["error"] or "")


class TestBackgroundScheduler:
    """start_background_scheduler 行為 — IDEATE_AUTO_SCAN env 控制是否起."""

    def test_no_env_var_returns_none(self, monkeypatch):
        from server.ideate_runner import start_background_scheduler

        monkeypatch.delenv("IDEATE_AUTO_SCAN", raising=False)
        result = start_background_scheduler()
        assert result is None

    def test_env_var_zero_returns_none(self, monkeypatch):
        from server.ideate_runner import start_background_scheduler

        monkeypatch.setenv("IDEATE_AUTO_SCAN", "0")
        result = start_background_scheduler()
        assert result is None
