"""ideate async runner — v4 階段 2 B iter 27 (簡化) + iter 33 (進度 streaming)。

把 core.ideate.run_ideate 包成 async + to_thread 版本給 server route 用。
不再讀 yaml / 不再起 background scheduler — 用戶反饋「設定檔太麻煩, 自動排程
使用機率低」, 改成完全 ad-hoc 模式。

需要自動排程的話, 用作業系統 cron / Windows Task Scheduler 排
`python scripts/run_ideate.py` 即可。

iter 33: 兩種使用模式並存
- 同步: await run_ideate_async(config) → 回 metrics dict (跟 iter 27 一樣)
- 非同步: scan_id = start_async_scan(config) → 立刻回 id;
  GET status: get_scan_state(scan_id) 回進度 dict
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from core.config import PROPOSALS_PATH
from core.ideate import IdeateConfig, run_ideate

from .jobs import JobStore, get_default_store


logger = logging.getLogger(__name__)


# ============================================================
# In-memory scan progress state (iter 33)
# 不持久化 — server restart 失去, UI poll 拿不到就視為「沒在跑」
# 多執行緒安全靠 _scan_lock
# ============================================================

# state shape: {scan_id: {state, scanned, proposed, new, error, started_at, ended_at, message}}
# state values: "running" | "done" | "failed"
_scan_state: dict[str, dict[str, Any]] = {}
_scan_lock = Lock()
# 每個 scan 保留 1 小時 (避免無限累積記憶體)
_SCAN_TTL_SECONDS = 3600


def _gc_old_scans() -> None:
    """清掉 ended 超過 TTL 的 scan state."""
    now = time.time()
    with _scan_lock:
        to_remove = [
            sid for sid, s in _scan_state.items()
            if s.get("_ended_ts") and (now - s["_ended_ts"]) > _SCAN_TTL_SECONDS
        ]
        for sid in to_remove:
            del _scan_state[sid]


def _new_scan_id() -> str:
    """產 8 char scan id (跟 prop_ 之類別開, 純 hex)."""
    return uuid.uuid4().hex[:12]


def _init_scan_state(scan_id: str) -> None:
    with _scan_lock:
        _scan_state[scan_id] = {
            "state": "running",
            "scanned": 0,
            "proposed": 0,
            "new": 0,
            "error": None,
            "message": "",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": None,
            "_ended_ts": None,
        }


def _update_scan_state(scan_id: str, **fields: Any) -> None:
    with _scan_lock:
        if scan_id not in _scan_state:
            return  # 過了 TTL 被清掉, 忽略
        _scan_state[scan_id].update(fields)


def _finish_scan_state(scan_id: str, *, state: str, error: str | None = None) -> None:
    with _scan_lock:
        if scan_id not in _scan_state:
            return
        _scan_state[scan_id]["state"] = state
        _scan_state[scan_id]["error"] = error
        _scan_state[scan_id]["ended_at"] = datetime.now(timezone.utc).isoformat()
        _scan_state[scan_id]["_ended_ts"] = time.time()


def get_scan_state(scan_id: str) -> dict[str, Any] | None:
    """GET handler 用 — 回 scan 當前狀態 (None = id 不存在或已過期)."""
    _gc_old_scans()
    with _scan_lock:
        s = _scan_state.get(scan_id)
        if not s:
            return None
        # copy 防 caller 改到內部 dict
        return {k: v for k, v in s.items() if not k.startswith("_")}


# ============================================================
# Synchronous async wrapper (iter 27, 不變)
# ============================================================


async def run_ideate_async(
    config: IdeateConfig,
    *,
    out_path: Path | None = None,
    store: JobStore | None = None,
) -> dict[str, Any]:
    """跑一輪 ideate (async 包裝, 不阻 event loop). 給 server route 直接 await。

    參數:
        config: 完整 IdeateConfig (watched_folders / llm_model / max_proposals_per_file)
            通常 server route 自己從 request body 組
        out_path: proposals.json 路徑, 預設 PROPOSALS_PATH
        store: JobStore, 預設 get_default_store()

    回傳:
        dict: {ok, scanned, proposed, new, error} 給 server route 當 JSON response 用
    """
    out = out_path or PROPOSALS_PATH
    st = store or get_default_store()

    counts: dict[str, int] = {"scanned": 0, "proposed": 0, "new": 0}

    def _progress(msg: str):
        # 解析 run_ideate progress 訊息抓 metrics — 不是最乾淨但夠用
        if "找到" in msg and "候選" in msg:
            try:
                counts["scanned"] = int(msg.split("找到")[1].split("個")[0].strip())
            except (IndexError, ValueError):
                pass
        elif "共產生" in msg:
            try:
                counts["proposed"] = int(msg.split("共產生")[1].split("個")[0].strip())
            except (IndexError, ValueError):
                pass
        elif "dedupe 後剩" in msg:
            try:
                counts["new"] = int(msg.split("dedupe 後剩")[1].split("個")[0].strip())
            except (IndexError, ValueError):
                pass
        logger.info("ideate: %s", msg)

    # Gemini call 是 sync (lazy import 內), 跑 thread pool 不阻 event loop
    # (Round 2 lessons-learned #2: 單一 FastAPI process 的任何 sync I/O 都要 to_thread)
    try:
        await asyncio.to_thread(
            run_ideate,
            config, st, out,
            progress=_progress,
        )
    except Exception as e:
        logger.exception("run_ideate failed")
        return {
            "ok": False,
            "scanned": counts["scanned"],
            "proposed": counts["proposed"],
            "new": counts["new"],
            "error": str(e),
        }

    return {
        "ok": True,
        "scanned": counts["scanned"],
        "proposed": counts["proposed"],
        "new": counts["new"],
        "error": None,
    }


# ============================================================
# Async background scan with progress (iter 33)
# ============================================================


def start_async_scan(
    config: IdeateConfig,
    *,
    out_path: Path | None = None,
    store: JobStore | None = None,
) -> str:
    """fire-and-forget: 起一個 background task 跑 ideate, 立刻回 scan_id.

    UI 拿 scan_id 後可 poll get_scan_state(scan_id) 看進度 / 結果.

    回傳:
        scan_id: 12 char hex, GET /scan-status/{scan_id} 用

    錯誤處理:
        - task 內任何 exception → state 變 "failed" + error msg
        - 過 1 小時的 done/failed state 自動 GC
    """
    scan_id = _new_scan_id()
    _init_scan_state(scan_id)

    async def _task():
        try:
            result = await _run_with_progress(scan_id, config, out_path, store)
            _update_scan_state(
                scan_id,
                scanned=result["scanned"],
                proposed=result["proposed"],
                new=result["new"],
            )
            if result["ok"]:
                _finish_scan_state(scan_id, state="done")
            else:
                _finish_scan_state(scan_id, state="failed", error=result.get("error"))
        except Exception as e:
            logger.exception("async scan task failed")
            _finish_scan_state(scan_id, state="failed", error=str(e))

    asyncio.create_task(_task())
    return scan_id


async def _run_with_progress(
    scan_id: str,
    config: IdeateConfig,
    out_path: Path | None,
    store: JobStore | None,
) -> dict[str, Any]:
    """run_ideate 包裝版 — 進度 callback 寫進 _scan_state 給 GET status 用."""
    out = out_path or PROPOSALS_PATH
    st = store or get_default_store()

    counts: dict[str, int] = {"scanned": 0, "proposed": 0, "new": 0}

    def _progress(msg: str):
        if "找到" in msg and "候選" in msg:
            try:
                counts["scanned"] = int(msg.split("找到")[1].split("個")[0].strip())
            except (IndexError, ValueError):
                pass
        elif "共產生" in msg:
            try:
                counts["proposed"] = int(msg.split("共產生")[1].split("個")[0].strip())
            except (IndexError, ValueError):
                pass
        elif "dedupe 後剩" in msg:
            try:
                counts["new"] = int(msg.split("dedupe 後剩")[1].split("個")[0].strip())
            except (IndexError, ValueError):
                pass
        # 同步寫進 state 給 UI 即時看
        _update_scan_state(
            scan_id,
            scanned=counts["scanned"],
            proposed=counts["proposed"],
            new=counts["new"],
            message=msg.strip()[:200],   # 保留最近一條 progress msg
        )
        logger.info("ideate: %s", msg)

    try:
        await asyncio.to_thread(
            run_ideate,
            config, st, out,
            progress=_progress,
        )
    except Exception as e:
        logger.exception("run_ideate failed")
        return {
            "ok": False,
            "scanned": counts["scanned"],
            "proposed": counts["proposed"],
            "new": counts["new"],
            "error": str(e),
        }

    return {
        "ok": True,
        "scanned": counts["scanned"],
        "proposed": counts["proposed"],
        "new": counts["new"],
        "error": None,
    }
