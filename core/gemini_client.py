"""統一 Gemini client 工廠（CODE_REVIEW_2026-07 T3-2 / T1-2）。

全 repo 建 google-genai ``Client`` 的唯一入口，收斂兩個長期不一致：

1. **金鑰單一來源**：一律走 ``core.config.get_gemini_api_key()``（設定頁優先，
   否則環境變數）。修掉多處 ``os.environ`` 直讀造成「設定頁填了 key、
   部分工作站卻不生效」的行為不一致。
2. **一律帶 HTTP timeout**（T1-2）：預設 120s，可用環境變數
   ``GEMINI_TIMEOUT_MS`` 全域覆寫；呼叫端可依站點特性再覆寫
   （如 slide_ingest 逐頁呼叫用 90s）。沒有 timeout 的 generate_content
   在連線 stall 時會無限掛住整個 job。

測試相容：``from google import genai`` 走函式內延遲 import，既有測試以
monkeypatch ``google.genai`` / ``sys.modules`` 換假 SDK 的手法照樣攔得到；
假 SDK 的 ``Client`` 若只收 ``api_key``（多數測試如此），會自動降級不帶
``http_options`` 重試 —— 該降級只該發生在測試替身上，正牌 SDK 一定收。
"""
from __future__ import annotations

import os

from core import config

GEMINI_TIMEOUT_MS_ENV = "GEMINI_TIMEOUT_MS"
DEFAULT_TIMEOUT_MS = 120_000


def default_timeout_ms() -> int:
    """全域預設 timeout（毫秒）；環境變數可覆寫，非法值退回內建預設。"""
    raw = os.environ.get(GEMINI_TIMEOUT_MS_ENV, "")
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    return DEFAULT_TIMEOUT_MS


def make_client(api_key: str | None = None, *, timeout_ms: int | None = None):
    """建立帶 timeout 的 Gemini client。

    api_key 未給時走 ``config.get_gemini_api_key()``（設定頁 > 環境變數），
    都沒有 → RuntimeError（訊息同 infocards 舊工廠，呼叫端／測試相容）。
    """
    key = api_key or config.get_gemini_api_key()
    if not key:
        raise RuntimeError("缺少 GEMINI_API_KEY 環境變數")
    from google import genai

    timeout = timeout_ms if (timeout_ms and timeout_ms > 0) else default_timeout_ms()
    http_options = None
    try:
        from google.genai import types
        http_options = types.HttpOptions(timeout=timeout)
    except Exception:
        http_options = None  # 假 SDK 可能沒有 types.HttpOptions
    if http_options is not None:
        try:
            return genai.Client(api_key=key, http_options=http_options)
        except TypeError:
            pass  # 測試替身的 Client 常只收 api_key —— 降級重試
    return genai.Client(api_key=key)
