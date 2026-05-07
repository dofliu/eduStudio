"""Runtime helpers — 只在 CLI / Web 啟動時才該呼叫的東西。

setup_utf8_stdout() 取代過去散在 5 個檔案最頂層的 sys.stdout.reconfigure 區塊。
之所以要拉出來:
- 模組頂層做 stdout reconfigure 是副作用,FastAPI 一 import pipeline 就會被改 stdout
- 統一一個入口好維護,以後若要改 errors 策略也只動這裡
- 純函式,要才呼叫,不會在 import 階段汙染環境
"""
from __future__ import annotations

import sys


def setup_utf8_stdout() -> None:
    """Windows 終端 cp950 不支援 emoji 與部分 Unicode,強制 UTF-8 輸出。

    所有 CLI 進入點 (pipeline.py / solve.py / slide_ingest.py / batch.py /
    publish.py / app.py) 都該在 main() 或 __main__ block 一開頭呼叫一次。

    非 Windows 平台直接 no-op。
    """
    if sys.platform != "win32":
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        # 已經被別處設過 / 非 TextIOWrapper 環境(例如 pytest capture)就跳過
        pass
