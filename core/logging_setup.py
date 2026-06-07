"""統一 logging 設定 (PR-4c).

設計:
- 主 handler: stderr, 人讀格式 (跟舊 print() 看起來差不多, 啟動 banner / runner
  狀態變化等都會印)
- 可選 per-job handler: 寫 jobs/<id>/log.jsonl 一行一筆 JSON, 給 React UI tail
- contextvar `current_job_id` 讓 logger 不必每次手動帶 extra={'job_id':...},
  runner 開 job 時 set, 跑完 reset

使用:
- module 頂部: `logger = logging.getLogger(__name__)`
- runner.py 在背景 task 開頭呼叫 attach_job_log(job_id), 結尾呼叫 detach_job_log
- caller 只要正常 logger.info / warning / error 即可

格式:
    {"ts": "2026-05-09T...", "level": "INFO", "logger": "server.runner",
     "job_id": "abc...", "msg": "...", "stage": "ingest"}
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# contextvar 讓 logger 自動帶當前 job_id, 不必每次 extra={'job_id':...}
current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_job_id", default=None,
)


class JobJsonFormatter(logging.Formatter):
    """每筆 log 一行 JSON, 給機器讀 + React UI tail."""

    def format(self, record: logging.LogRecord) -> str:
        # 從 contextvar 取 job_id (runner attach_job_log 時 set 過)
        job_id = current_job_id.get() or getattr(record, "job_id", None)
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if job_id:
            payload["job_id"] = job_id
        # 額外 extra 欄位 (例: stage / pid / step_idx)
        for k in ("stage", "step_idx", "pid"):
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """stderr 用, 給開發者直接看 console."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        job_id = current_job_id.get() or getattr(record, "job_id", "")
        prefix = f"[{ts}] {record.levelname:5s} {record.name}"
        if job_id:
            prefix += f" job={job_id}"
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"{prefix}: {msg}"


# ---------- module-level state ----------

_configured = False
_job_handlers: dict[str, logging.Handler] = {}    # job_id → FileHandler
# 保護 _job_handlers: 未來改 worker pool 可能多 task 同時 attach/detach,
# 沒鎖會踩到 dict 同步改寫 (CPython GIL 雖然單 op 安全, 但 contains+set 不是 atomic)
_job_handlers_lock = threading.Lock()


def setup_logging(level: int = logging.INFO) -> None:
    """整個 process 一次性 init. import 時不能呼叫 (對 testing 不友善),
    要在 server / CLI 啟動點呼叫一次.

    重複呼叫 idempotent (用 _configured 旗標)。
    """
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    root.setLevel(level)
    # 清掉預設 handlers (避免跟既有 print 重複)
    for h in list(root.handlers):
        root.removeHandler(h)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(HumanFormatter())
    stderr_handler.setLevel(level)
    root.addHandler(stderr_handler)

    # 第三方 lib 的 log 太吵, 限 WARNING+ (uvicorn / httpx 自己有適合的層級)
    # google_genai: 每次 Gemini 呼叫印 "AFC is enabled with max remote calls: 10 /
    # AFC remote call N is done"(自動函式呼叫 INFO log), slides/repo 多次呼叫會洗版 job log → 降級。
    for noisy in ("urllib3", "httpx", "httpcore", "uvicorn.access", "asyncio",
                  "google_genai", "google_genai.models", "google.genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def attach_job_log(job_id: str, log_path: Path) -> None:
    """背景 task 開始時呼叫: 加一個只收這個 job 的 FileHandler 寫 jsonl.

    為什麼用 filter 而不是 separate logger:
    - 整個 process 的 logger tree 走 root handler, 改 logger 樹太侵入
    - 用 filter 篩 contextvar / extra 比較乾淨, 訊息來自 server.runner /
      core.scriptor / core.outliner / pipeline 任何地方都能 attach

    log_path 父層必須先存在 (jobs/<id>/ 已被 JobStore 建好)。
    """
    with _job_handlers_lock:
        if job_id in _job_handlers:
            return     # 重複 attach 視為已開, 不亂加 handler

        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        handler.setFormatter(JobJsonFormatter())
        handler.setLevel(logging.INFO)

        # 只收 contextvar = 這個 job 的訊息
        def _filter(record: logging.LogRecord) -> bool:
            cur = current_job_id.get()
            return cur == job_id

        handler.addFilter(_filter)
        logging.getLogger().addHandler(handler)
        _job_handlers[job_id] = handler


def detach_job_log(job_id: str) -> None:
    """背景 task 結束時呼叫, 把 handler 收掉避免 file descriptor 累積。"""
    with _job_handlers_lock:
        handler = _job_handlers.pop(job_id, None)
    if handler is not None:
        logging.getLogger().removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass


def read_job_log(log_path: Path, *, tail: int = 200) -> list[dict]:
    """給 GET /jobs/{id}/log 用: 讀 jsonl 末尾 N 行, parse 成 dict list.

    壞行 (非合法 JSON) 不丟例外, 退到原始 raw 字串 (機器人 fallback)。
    """
    if not log_path.exists():
        return []
    # 讀末尾 N 行 (對小檔 OK; 大檔可考慮 seek + reverse, 但 jsonl 通常不會超大)
    lines = log_path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in lines[-tail:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            out.append({"level": "RAW", "msg": line})
    return out
