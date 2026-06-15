"""Gemini 用量計帳（eduStudio 成本面板真實統計）。

在 Gemini 呼叫的中央 chokepoint 記錄每筆用量（文字以字元數、圖片以模型計），用
MODEL_PRICING（char-based，對齊 infoCard estimateCost）換算成本，存 SQLite。成本面板
讀 summary() 顯示真實 used / 各站花費 / 近期紀錄。

涵蓋範圍：視覺站（core.infocards.gemini）、在地化（core.translation.service），以及
影片/解析 render pipeline 的 Gemini chokepoint（outliner / scriptor / slide_ingest /
solve，經 record_text_now 接入，C-1）。budget/trial 無真實來源，面板端以設定值呈現。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import closing

from core import config
from core.infocards.models import MODEL_PRICING

_TEXT_IN = MODEL_PRICING["text"]["input_per_1k_chars"] / 1000.0
_TEXT_OUT = MODEL_PRICING["text"]["output_per_1k_chars"] / 1000.0
_IMG = MODEL_PRICING["image"]

# 站別顯示標籤。
_STATION_LABEL = {"visual": "視覺", "language": "在地化", "video": "影片", "material": "解析"}


def _text_cost(input_chars: int, output_chars: int) -> float:
    return input_chars * _TEXT_IN + output_chars * _TEXT_OUT


def _image_cost(model: str) -> float:
    return float(_IMG.get(model, 0.0))


class UsageStore:
    """SQLite 用量計帳。執行緒安全（單一 lock，量小可接受）。"""

    def __init__(self, db_path: str | None = None):
        self._path = db_path or config.get_usage_db_path()
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def _init_db(self) -> None:
        with self._lock, closing(self._conn()) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    station TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    model TEXT,
                    input_chars INTEGER DEFAULT 0,
                    output_chars INTEGER DEFAULT 0,
                    cost REAL NOT NULL,
                    label TEXT
                )"""
            )
            conn.commit()

    def record_text(self, station: str, input_chars: int, output_chars: int,
                    *, model: str = "", label: str = "", ts: str = "") -> float:
        """記一筆文字呼叫；回該筆成本（USD）。"""
        cost = _text_cost(max(0, input_chars), max(0, output_chars))
        self._insert(ts, station, "text", model, input_chars, output_chars, cost, label)
        return cost

    def record_image(self, station: str, model: str, *, label: str = "", ts: str = "") -> float:
        """記一筆圖片生成；回該筆成本（USD）。"""
        cost = _image_cost(model)
        self._insert(ts, station, "image", model, 0, 0, cost, label)
        return cost

    def _insert(self, ts, station, kind, model, ic, oc, cost, label) -> None:
        # ts 由呼叫端給（避免在 core 用 datetime.now 破壞可重現性）；空則存空字串。
        with self._lock, closing(self._conn()) as conn:
            conn.execute(
                "INSERT INTO usage (ts, station, kind, model, input_chars, output_chars, cost, label)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (ts or "", station, kind, model or "", ic, oc, cost, label or ""),
            )
            conn.commit()

    def summary(self, recent_limit: int = 8) -> dict:
        """彙總：總成本 used / 各站花費 byStation / 近期 recent / 筆數 count。"""
        with self._lock, closing(self._conn()) as conn:
            total = conn.execute("SELECT COALESCE(SUM(cost),0), COUNT(*) FROM usage").fetchone()
            by = conn.execute(
                "SELECT station, COALESCE(SUM(cost),0) FROM usage GROUP BY station ORDER BY 2 DESC"
            ).fetchall()
            recent = conn.execute(
                "SELECT ts, station, kind, model, cost, label FROM usage ORDER BY id DESC LIMIT ?",
                (recent_limit,),
            ).fetchall()
        return {
            "used": round(total[0], 4),
            "count": total[1],
            "currency": "USD",
            "byStation": [
                {"key": s, "label": _STATION_LABEL.get(s, s), "amount": round(c, 4)}
                for s, c in by
            ],
            "recent": [
                {"time": ts, "station": _STATION_LABEL.get(st, st), "kind": kind,
                 "model": model, "amount": round(c, 5), "label": label}
                for ts, st, kind, model, c, label in recent
            ],
        }


_default_store: UsageStore | None = None


def get_usage_store() -> UsageStore:
    """共享 UsageStore（lazy 單例）。測試以新實例（tmp db_path）隔離。"""
    global _default_store
    if _default_store is None:
        _default_store = UsageStore()
    return _default_store


def record_text(station: str, input_chars: int, output_chars: int, **kw) -> None:
    """模組級便捷：記文字用量，吞例外（計帳不可拖垮主流程）。"""
    try:
        get_usage_store().record_text(station, input_chars, output_chars, **kw)
    except Exception:
        pass


def record_image(station: str, model: str, **kw) -> None:
    """模組級便捷：記圖片用量，吞例外。"""
    try:
        get_usage_store().record_image(station, model, **kw)
    except Exception:
        pass


def record_text_now(station: str, model: str, prompt: str, response: str,
                    *, label: str = "") -> None:
    """便捷：以當前 UTC 時間記一筆文字用量（直接給 prompt/response 字串，自動數字元）。

    為影片/解析 render pipeline 等「呼叫端手上是字串」的 chokepoint 設計：填 ts=now、
    數 prompt/response 字元後轉呼 record_text。datetime 只落在這層便捷包裝，UsageStore
    核心仍純（ts 由參數帶入），維持可重現。吞例外不拖垮主流程。
    """
    try:
        from datetime import datetime, timezone

        record_text(station, len(prompt or ""), len(response or ""),
                    model=model, label=label,
                    ts=datetime.now(timezone.utc).isoformat())
    except Exception:
        pass
