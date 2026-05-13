"""ideate async runner — v4 階段 2 B iter 27 (大幅簡化)。

把 core.ideate.run_ideate 包成 async + to_thread 版本給 server route 用。
不再讀 yaml / 不再起 background scheduler — 用戶反饋「設定檔太麻煩, 自動排程
使用機率低」, 改成完全 ad-hoc 模式。

需要自動排程的話, 用作業系統 cron / Windows Task Scheduler 排
`python scripts/run_ideate.py` 即可。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from core.config import PROPOSALS_PATH
from core.ideate import IdeateConfig, run_ideate

from .jobs import JobStore, get_default_store


logger = logging.getLogger(__name__)


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
