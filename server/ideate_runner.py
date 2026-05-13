"""ideate background runner — v4 階段 2 B iter 26。

把 core.ideate.run_ideate 包成「從 yaml config 讀 watched_folders → 跑 → 寫
proposals.json」一條龍函式。給三個 caller 共用:

1. **CLI** scripts/run_ideate.py (現有, 從命令列 args 組 config) — 沒走這層
2. **UI 按鈕** POST /proposals/scan (server route) — 走這層
3. **自動排程** server.main startup 起 asyncio interval task — 走這層

不直接動 ideate_config.yaml schema, 只負責 load + dispatch。
yaml 缺檔時回 None (caller 決定 graceful 處理)。

設計筆記:
- load_ideate_config_yaml() 跟 server/jobs.JobStore 一樣可以 monkeypatch 路徑
  測試, 不寫死 IDEATE_CONFIG_PATH
- run_ideate_from_yaml 走 asyncio.to_thread 防 Gemini call 阻 event loop
  (FastAPI 單一 process, sync I/O 是炸雷 — Round 2 lessons-learned #2)
- background scheduler 用簡單 asyncio.sleep(N hours) 迴圈, 失敗 log 但不 crash
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from core.config import IDEATE_CONFIG_PATH, PROPOSALS_PATH
from core.ideate import IdeateConfig, run_ideate

from .jobs import JobStore, get_default_store


logger = logging.getLogger(__name__)


# ============================================================
# Config loader
# ============================================================


def load_ideate_config_yaml(
    path: Path | None = None,
) -> tuple[IdeateConfig | None, int]:
    """讀 ideate_config.yaml. 回 (config, auto_scan_interval_hours).

    參數:
        path: 自訂 yaml 路徑 (測試用), 預設走 core.config.IDEATE_CONFIG_PATH

    回傳:
        (IdeateConfig | None, auto_scan_interval_hours)
        - 檔不存在 / yaml parse 失敗: (None, 0)
        - enabled=False: (None, 0) — 強制關閉, caller 看到 None 視為「不要跑」
        - 正常: (config, hours)

    錯誤處理: 不 raise, 一律 graceful 回 None (server startup 不該因 yaml
    壞掉就起不來; CLI / UI 觸發時自己印 error 給 user)。
    """
    yaml_path = path or IDEATE_CONFIG_PATH
    if not yaml_path.exists():
        return None, 0
    try:
        import yaml  # lazy import — yaml 是 server-side dep, 非全域
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("ideate_config.yaml parse 失敗: %s", e)
        return None, 0

    if not isinstance(raw, dict):
        return None, 0

    if not raw.get("enabled", True):
        return None, 0

    # 組 IdeateConfig (跟 core.ideate.IdeateConfig TypedDict 對齊)
    config: IdeateConfig = {
        "watched_folders": raw.get("watched_folders") or [],
        "llm_model": raw.get("llm_model", "gemini-2.5-flash"),
        "max_proposals_per_file": int(raw.get("max_proposals_per_file", 3)),
        "enabled": True,
    }
    interval = int(raw.get("auto_scan_interval_hours", 0))
    return config, max(0, interval)


# ============================================================
# Main runner — 給 server route + scheduler 用
# ============================================================


async def run_ideate_from_yaml(
    *,
    config_path: Path | None = None,
    out_path: Path | None = None,
    store: JobStore | None = None,
) -> dict[str, Any]:
    """跑一輪 ideate (從 yaml 讀 config). async / to_thread 包過, 不阻 event loop。

    回傳結果摘要 dict — 給 server route 直接當 JSON response 用:
        {
            "ok": bool,
            "scanned": int,        # 掃到候選數
            "proposed": int,       # propose 後總提案數
            "new": int,            # dedupe 後新提案數
            "error": str | None,
        }
    """
    cfg, _ = load_ideate_config_yaml(config_path)
    if cfg is None:
        return {
            "ok": False,
            "scanned": 0,
            "proposed": 0,
            "new": 0,
            "error": "ideate_config.yaml 不存在或 enabled=false",
        }

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
    try:
        await asyncio.to_thread(
            run_ideate,
            cfg, st, out,
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
# Background scheduler — server startup 起來
# ============================================================


# 全域旗標: 防 startup 被呼叫多次重複起 scheduler
_scheduler_task: asyncio.Task | None = None


async def _scheduler_loop():
    """背景 task: 每 interval 小時跑一次 ideate。

    interval 從 ideate_config.yaml 讀, 若 0 / 無設 / yaml 壞掉就不跑。
    每輪結束都重讀 yaml — 用戶改 interval 不必重啟 server。
    """
    logger.info("ideate scheduler started")
    while True:
        _, interval_hours = load_ideate_config_yaml()
        if interval_hours <= 0:
            # config 改成 0 或 disabled, 等 10 分鐘再重看 (不殺迴圈)
            await asyncio.sleep(600)
            continue

        try:
            logger.info("ideate scheduler tick — running ideate")
            result = await run_ideate_from_yaml()
            logger.info("ideate scheduler tick done: %s", result)
        except Exception:
            logger.exception("ideate scheduler tick failed")

        # 下次跑前等 interval_hours
        await asyncio.sleep(interval_hours * 3600)


def start_background_scheduler() -> asyncio.Task | None:
    """server.main startup 呼叫. 起 background loop, 已 running 就回 None。

    僅在 IDEATE_AUTO_SCAN=1 環境變數設了才起 scheduler — 預設關。
    用戶想自動跑要明確 opt-in (避免不知情消耗 Gemini quota)。
    """
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return None  # 已 running
    if os.environ.get("IDEATE_AUTO_SCAN") != "1":
        logger.info("ideate scheduler skipped (set IDEATE_AUTO_SCAN=1 to enable)")
        return None

    _scheduler_task = asyncio.create_task(_scheduler_loop())
    return _scheduler_task


def stop_background_scheduler() -> None:
    """server.main shutdown 呼叫. cancel 背景 task。"""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    _scheduler_task = None
