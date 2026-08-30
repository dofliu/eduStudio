"""共用媒體命令 runner（CODE_REVIEW_2026-07 T3-3 / T1-2）。

全 repo 跑 ffmpeg / ffprobe / 轉檔類 subprocess 的統一入口：

- **一律帶 timeout**：預設 1800s（長 render 夠用），環境變數
  ``EDUSTUDIO_FFMPEG_TIMEOUT`` 可全域覆寫，呼叫端可依站點再覆寫。
  沒 timeout 的 render 在 ffmpeg 卡死時會永久掛住整個 job（T1-2）。
- **一律檢查 returncode**（``check=True`` 預設）：失敗 raise
  ``RuntimeError(f"{step} 失敗 (code {rc}): {stderr 前 500 字}")`` ——
  step 由呼叫端給，讓錯誤訊息能定位是哪一步炸掉。
  刻意「失敗要降級不 raise」的呼叫端傳 ``check=False`` 自行判斷。
- **一律 capture output**：stderr 進錯誤訊息，不再直噴 console 或被丟棄。

例外語意：
- ``FileNotFoundError``（ffmpeg 不在 PATH）原樣拋出，呼叫端可補自己的提示
  （server/runner 對 song render 有既有的中文指引訊息）。
- ``subprocess.TimeoutExpired`` 原樣拋出（訊息含命令），視同 render 失敗。

測試相容：本模組直接呼叫 ``subprocess.run``（stdlib module attribute），
既有測試 monkeypatch 全域 ``subprocess.run`` 的手法照樣攔得到；
per-module patch 的測試改 patch ``core.ffmpeg.subprocess`` 即可。
"""
from __future__ import annotations

import os
import subprocess

FFMPEG_TIMEOUT_ENV = "EDUSTUDIO_FFMPEG_TIMEOUT"
DEFAULT_TIMEOUT_S = 1800


def default_timeout_s() -> int:
    """全域預設 timeout（秒）；環境變數可覆寫，非法值退回內建預設。"""
    raw = os.environ.get(FFMPEG_TIMEOUT_ENV, "")
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    return DEFAULT_TIMEOUT_S


def run_media_cmd(
    cmd: list[str],
    *,
    step: str,
    timeout: int | None = None,
    cwd=None,
    check: bool = True,
    text: bool = True,
):
    """跑一條媒體命令，回 ``subprocess.CompletedProcess``。

    Args:
        cmd: 完整命令 list（不走 shell）。
        step: 這一步在做什麼（進錯誤訊息，例 ``"ffmpeg render"``）。
        timeout: 秒；None → ``default_timeout_s()``。
        cwd: 工作目錄（concat list 用相對路徑時需要）。
        check: True（預設）→ returncode != 0 raise RuntimeError；
               False → 呼叫端自行看 returncode（降級語意）。
        text: 以文字模式 capture（False 給要 bytes 的呼叫端）。
    """
    effective_timeout = timeout if (timeout and timeout > 0) else default_timeout_s()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=text,
        cwd=cwd,
        timeout=effective_timeout,
    )
    if check and proc.returncode != 0:
        stderr = proc.stderr or b"" if not text else (proc.stderr or "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        detail = stderr.strip()[:500] or "unknown error"
        raise RuntimeError(f"{step} 失敗 (code {proc.returncode}): {detail}")
    return proc


def assert_nonempty_file(file_path: str, step: str) -> None:
    """驗證輸出檔存在且非空 —— ffmpeg 偶爾 rc=0 但輸出 0 byte，早炸早查。"""
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        raise RuntimeError(f"{step} 失敗: 輸出檔不存在或為空 ({file_path})")
