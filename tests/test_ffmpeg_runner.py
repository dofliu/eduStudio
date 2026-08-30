"""core/ffmpeg.py 共用媒體 runner 測試（T3-3 / T1-2）。不真跑 ffmpeg。"""
from __future__ import annotations

import subprocess

import pytest

import core.ffmpeg as ff


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_success_returns_proc(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured.update(kw)
        return _Proc(0, stdout="ok")

    monkeypatch.setattr(ff.subprocess, "run", fake_run)
    proc = ff.run_media_cmd(["ffmpeg", "-y"], step="test step")
    assert proc.stdout == "ok"
    assert captured["cmd"] == ["ffmpeg", "-y"]
    # 一律帶 timeout（T1-2 核心訴求）
    assert captured["timeout"] == ff.default_timeout_s()
    assert captured["capture_output"] is True


def test_nonzero_raises_with_step_and_stderr(monkeypatch):
    monkeypatch.setattr(ff.subprocess, "run",
                        lambda cmd, **kw: _Proc(1, stderr="boom detail"))
    with pytest.raises(RuntimeError, match="test render 失敗 \\(code 1\\): boom detail"):
        ff.run_media_cmd(["ffmpeg"], step="test render")


def test_check_false_returns_failed_proc(monkeypatch):
    monkeypatch.setattr(ff.subprocess, "run", lambda cmd, **kw: _Proc(3, stderr="x"))
    proc = ff.run_media_cmd(["ffmpeg"], step="soft", check=False)
    assert proc.returncode == 3  # 降級語意: 呼叫端自行判斷


def test_bytes_stderr_decoded_in_error(monkeypatch):
    monkeypatch.setattr(ff.subprocess, "run",
                        lambda cmd, **kw: _Proc(1, stderr=b"\xe9\x8c\xafmsg"))
    with pytest.raises(RuntimeError, match="msg"):
        ff.run_media_cmd(["ffmpeg"], step="s", text=False)


def test_cwd_and_timeout_passthrough(monkeypatch):
    captured = {}

    def fake_run(cmd, **kw):
        captured.update(kw)
        return _Proc(0)

    monkeypatch.setattr(ff.subprocess, "run", fake_run)
    ff.run_media_cmd(["ffprobe"], step="probe", cwd="/tmp/x", timeout=42)
    assert captured["cwd"] == "/tmp/x"
    assert captured["timeout"] == 42


def test_file_not_found_propagates(monkeypatch):
    def fake_run(cmd, **kw):
        raise FileNotFoundError("ffmpeg not found")

    monkeypatch.setattr(ff.subprocess, "run", fake_run)
    with pytest.raises(FileNotFoundError):
        ff.run_media_cmd(["ffmpeg"], step="s")


def test_timeout_env_override(monkeypatch):
    monkeypatch.setenv(ff.FFMPEG_TIMEOUT_ENV, "60")
    assert ff.default_timeout_s() == 60
    monkeypatch.setenv(ff.FFMPEG_TIMEOUT_ENV, "junk")
    assert ff.default_timeout_s() == ff.DEFAULT_TIMEOUT_S
    monkeypatch.delenv(ff.FFMPEG_TIMEOUT_ENV)
    assert ff.default_timeout_s() == ff.DEFAULT_TIMEOUT_S


def test_assert_nonempty_file(tmp_path):
    p = tmp_path / "out.mp4"
    with pytest.raises(RuntimeError, match="輸出檔不存在或為空"):
        ff.assert_nonempty_file(str(p), "render")
    p.write_bytes(b"")
    with pytest.raises(RuntimeError, match="輸出檔不存在或為空"):
        ff.assert_nonempty_file(str(p), "render")
    p.write_bytes(b"data")
    ff.assert_nonempty_file(str(p), "render")  # 不 raise


def test_global_subprocess_patch_still_intercepts(monkeypatch):
    # 既有測試手法: monkeypatch 全域 subprocess.run —— 共用 runner 必須攔得到
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: _Proc(0, stdout="patched"))
    proc = ff.run_media_cmd(["ffmpeg"], step="s")
    assert proc.stdout == "patched"
