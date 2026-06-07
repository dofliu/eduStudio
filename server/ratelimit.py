"""S-6 簡單 per-IP rate limit (in-memory token bucket)。

目的: 防自架者被內網誤觸 / 腳本迴圈刷爆 Gemini 額度。**不引入 slowapi 等額外依賴**,
純標準庫實作 (token bucket)。

設計:
- 對「燒額度」端點 (infocard 生成/refine、建 job、上傳) 掛 `Depends(rate_limit)`。
- 每個 client IP 一個共享 bucket (跨這些端點合計), 超限回 429。
- 容量/補充速率用 env `EDUSTUDIO_RATE_LIMIT_PER_MIN` 調 (預設 30/min; <=0 = 關閉)。
- in-memory、單程序; 單機自架夠用。真要多 worker 跨程序共享再換 redis。
"""
from __future__ import annotations

import os
import threading
import time

from fastapi import HTTPException, Request, status

DEFAULT_PER_MIN = 30
RATE_LIMIT_ENV = "EDUSTUDIO_RATE_LIMIT_PER_MIN"


def limit_per_min() -> int:
    """每分鐘上限。未設→預設; 解析失敗→預設; <=0→關閉。"""
    raw = os.environ.get(RATE_LIMIT_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_PER_MIN
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PER_MIN


class _Bucket:
    __slots__ = ("tokens", "last")

    def __init__(self, tokens: float, last: float) -> None:
        self.tokens = tokens
        self.last = last


class RateLimiter:
    """每個 key (= client IP) 一個 token bucket。thread-safe。"""

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, per_min: int, *, now: float | None = None) -> bool:
        """消耗一個 token; 還有額度回 True, 否則 False。per_min<=0 永遠放行。"""
        if per_min <= 0:
            return True
        capacity = float(per_min)
        refill_per_sec = per_min / 60.0
        t = time.monotonic() if now is None else now
        with self._lock:
            b = self._buckets.get(key)
            if b is None:
                # 新 client 先給滿桶
                b = _Bucket(capacity, t)
                self._buckets[key] = b
            else:
                elapsed = max(0.0, t - b.last)
                b.tokens = min(capacity, b.tokens + elapsed * refill_per_sec)
                b.last = t
            if b.tokens >= 1.0:
                b.tokens -= 1.0
                return True
            return False


# 模組級 fallback limiter (app.state 沒掛時用; 正常會用 per-app 那個)
_fallback_limiter = RateLimiter()


def install_limiter(app) -> None:
    """每個 app instance 掛一個獨立 limiter。

    放 app.state 而非用模組全域, 好處: 測試每次 create_app() 都拿到全新滿桶,
    不會因為前一個測試把同一 'testclient' IP 的桶用掉而誤觸 429。
    真實部署只有一個 app → 一個 limiter, 行為正確。
    """
    app.state.rate_limiter = RateLimiter()


def _get_limiter(request: Request) -> RateLimiter:
    return getattr(request.app.state, "rate_limiter", _fallback_limiter)


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def rate_limit(request: Request) -> None:
    """FastAPI dependency: 燒額度端點掛這個, 超限回 429。"""
    per_min = limit_per_min()
    if not _get_limiter(request).allow(_client_ip(request), per_min):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"請求過於頻繁（每分鐘上限 {per_min} 次），請稍後再試。",
        )
