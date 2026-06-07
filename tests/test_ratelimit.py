"""S-6 per-IP rate limit 測試。

涵蓋 token bucket 核心邏輯 + rate_limit dependency 的 429 行為 + env 開關。
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="需要 fastapi 安裝")

from fastapi import HTTPException  # noqa: E402
from starlette.requests import Request  # noqa: E402

from server.ratelimit import (  # noqa: E402
    DEFAULT_PER_MIN,
    RATE_LIMIT_ENV,
    RateLimiter,
    limit_per_min,
    rate_limit,
)


def _fake_request(ip: str) -> Request:
    # 最小 ASGI scope; rate_limit 只用到 client 與 app.state
    class _State:
        pass

    class _App:
        state = _State()

    scope = {
        "type": "http",
        "client": (ip, 12345),
        "headers": [],
        "app": _App(),
    }
    return Request(scope)


# ---------- token bucket 核心 ----------

def test_allows_up_to_capacity_then_blocks():
    rl = RateLimiter()
    now = 1000.0
    # 滿桶 = 5; 前 5 次放行, 第 6 次擋 (同一瞬間不補充)
    allowed = [rl.allow("ip", 5, now=now) for _ in range(5)]
    assert all(allowed)
    assert rl.allow("ip", 5, now=now) is False


def test_refill_over_time():
    rl = RateLimiter()
    # 60/min = 1 token/sec。用光後過 2 秒應補回 ~2 個
    t = 1000.0
    for _ in range(60):
        rl.allow("ip", 60, now=t)
    assert rl.allow("ip", 60, now=t) is False
    assert rl.allow("ip", 60, now=t + 2.0) is True  # 補回 token


def test_per_ip_isolation():
    rl = RateLimiter()
    now = 1000.0
    for _ in range(3):
        rl.allow("a", 3, now=now)
    assert rl.allow("a", 3, now=now) is False  # a 用光
    assert rl.allow("b", 3, now=now) is True   # b 不受影響


def test_disabled_when_non_positive():
    rl = RateLimiter()
    now = 1000.0
    # per_min <= 0 → 永遠放行
    assert all(rl.allow("ip", 0, now=now) for _ in range(100))
    assert all(rl.allow("ip", -5, now=now) for _ in range(100))


# ---------- env 解析 ----------

def test_limit_per_min_default(monkeypatch):
    monkeypatch.delenv(RATE_LIMIT_ENV, raising=False)
    assert limit_per_min() == DEFAULT_PER_MIN


def test_limit_per_min_override(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_ENV, "5")
    assert limit_per_min() == 5


def test_limit_per_min_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_ENV, "abc")
    assert limit_per_min() == DEFAULT_PER_MIN


# ---------- dependency 429 行為 ----------

def test_rate_limit_dependency_raises_429(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_ENV, "3")
    req = _fake_request("9.9.9.9")
    # 前 3 次過, 第 4 次 429
    for _ in range(3):
        rate_limit(req)  # 不 raise
    with pytest.raises(HTTPException) as e:
        rate_limit(req)
    assert e.value.status_code == 429


def test_rate_limit_disabled_never_raises(monkeypatch):
    monkeypatch.setenv(RATE_LIMIT_ENV, "0")
    req = _fake_request("8.8.8.8")
    for _ in range(200):
        rate_limit(req)  # 全部不 raise
