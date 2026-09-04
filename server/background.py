"""背景任務管理 — 並行上限 + 強參照保管 (T1-3)。

原本各處直接 `asyncio.create_task(...)` 且**把回傳值丟掉**,兩個問題:

1. **無並行上限**:連送 N 個 job 就有 N 條 pipeline 同時跑
   `asyncio.to_thread(ffmpeg / solve_pdf / whisper)`,一起搶預設
   ThreadPoolExecutor 的執行緒。CPU / 記憶體爆掉之外,還會**餓死其他 handler 的
   檔案 I/O**(`to_thread` 是同一個 default executor),整台 server 看起來像當掉。
2. **task 可能被 GC**:asyncio 只持有 task 的 **weak reference**。沒有任何強
   參照時,理論上 task 可以在跑到一半被回收 → 背景工作靜默中斷、job 永遠卡著。

本模組給一個 `spawn()` 取代裸 `create_task`:
- 把 task 放進 module 級 `set` 保強參照,`add_done_callback` 完成後移除。
- 順手把「背景 task 炸掉但沒人 await」的例外記進 log(否則只有直譯器關閉時才會
  看到 "Task exception was never retrieved")。
- `limit=True`(預設)時先過一道 `asyncio.Semaphore`:**排隊而不是拒絕** ——
  job 已經建好了,只是等前面的跑完才輪到它,對使用者是「慢」不是「失敗」。

並行數用 `EDUSTUDIO_MAX_CONCURRENT_JOBS` 調(預設 2);設 0 或負數 = 不限制
(還原舊行為)。預設 2 的理由:單機自架,render 是 CPU/IO 都重的工作,
留餘裕給 HTTP handler 與其他 to_thread 呼叫。

**semaphore 綁 event loop**:每個 running loop 各自一個(用
`WeakKeyDictionary` 快取),避免測試裡不同 loop 共用同一個 semaphore 而卡住。
"""
from __future__ import annotations

import asyncio
import logging
import os
import weakref
from typing import Any, Coroutine

log = logging.getLogger(__name__)


DEFAULT_MAX_CONCURRENT_JOBS = 2
MAX_CONCURRENT_ENV = "EDUSTUDIO_MAX_CONCURRENT_JOBS"

#: 進行中的背景 task 強參照(避免被 GC);完成即移除。
_TASKS: set[asyncio.Task] = set()

#: 每個 event loop 一個 semaphore。
_SEMAPHORES: "weakref.WeakKeyDictionary[Any, asyncio.Semaphore]" = (
    weakref.WeakKeyDictionary()
)


def max_concurrent_jobs() -> int:
    """並行上限;0 或負數 = 不限制。無法解析的值退回預設(不讓打錯字關掉保護)。"""
    raw = os.environ.get(MAX_CONCURRENT_ENV)
    if raw is None or not raw.strip():
        return DEFAULT_MAX_CONCURRENT_JOBS
    try:
        return int(raw)
    except ValueError:
        log.warning(
            "%s=%r 不是整數, 用預設 %d", MAX_CONCURRENT_ENV, raw,
            DEFAULT_MAX_CONCURRENT_JOBS,
        )
        return DEFAULT_MAX_CONCURRENT_JOBS


def _semaphore() -> asyncio.Semaphore | None:
    """取得目前 loop 的 semaphore;不限制時回 None。"""
    limit = max_concurrent_jobs()
    if limit <= 0:
        return None
    loop = asyncio.get_running_loop()
    sem = _SEMAPHORES.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(limit)
        _SEMAPHORES[loop] = sem
    return sem


def pending_count() -> int:
    """目前仍在進行中的背景 task 數(給測試與健檢用)。"""
    return len(_TASKS)


async def _guarded(coro: Coroutine, *, name: str) -> None:
    """先排隊拿到名額再跑;`limit=False` 時不會走到這裡。"""
    sem = _semaphore()
    if sem is None:
        await coro
        return
    if sem.locked():
        log.info("背景工作排隊中 (並行上限 %d): %s", max_concurrent_jobs(), name)
    async with sem:
        await coro


def _on_done(task: asyncio.Task) -> None:
    _TASKS.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        # 背景 task 沒人 await, 例外不記下來就等於消失
        log.error("背景工作失敗: %s", task.get_name(), exc_info=exc)


def spawn(
    coro: Coroutine,
    *,
    name: str | None = None,
    limit: bool = True,
) -> asyncio.Task:
    """把 coroutine 丟到背景跑,保強參照;`limit=True` 時受並行上限管制。

    Args:
        coro: 要跑的 coroutine。
        name: task 名稱(進 log,方便追是哪個 job)。
        limit: 是否佔用「重工作」名額。render / ingest 這種吃 CPU 與磁碟的走
            `True`;純網路等待(YouTube 上傳)或輕量文字呼叫走 `False` ——
            它們只需要強參照,不該佔掉 render 的名額。
    """
    label = name or getattr(coro, "__name__", "background")
    task = asyncio.create_task(
        _guarded(coro, name=label) if limit else coro,
        name=label,
    )
    _TASKS.add(task)
    task.add_done_callback(_on_done)
    return task
