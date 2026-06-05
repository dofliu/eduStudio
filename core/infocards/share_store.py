"""infoCard 分享連結儲存（Phase C-4，C-0#3 決策：SQLite 取代原 in-memory Map）。

infoCard 原本用 in-memory Map（7 天 TTL，重啟即失）。合併後改 SQLite 持久化（沿 core/storage
模式），db 走 config、lazy 單例去 import side-effect。建立分享回 id，讀取自動剪除過期。
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Optional

from core import config

_TTL_SECONDS = 7 * 24 * 3600  # 7 天（對齊 infoCard）


class ShareStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.get_share_db_path()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS shares (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT DEFAULT '',
            data TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """)
        conn.commit()
        conn.close()

    def _prune(self, conn: sqlite3.Connection) -> None:
        """剪除過期分享（created_at 早於 now-TTL）。"""
        cutoff = time.time() - _TTL_SECONDS
        conn.execute("DELETE FROM shares WHERE created_at < ?", (cutoff,))

    def create(self, share_type: str, title: str, data: Any) -> str:
        """建立分享，回 id。data 任意 JSON-serializable（簡報/海報/漫畫成品）。"""
        share_id = uuid.uuid4().hex[:12]
        conn = sqlite3.connect(self.db_path)
        self._prune(conn)
        conn.execute(
            "INSERT INTO shares (id, type, title, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (share_id, share_type, title or "", json.dumps(data, ensure_ascii=False), time.time()),
        )
        conn.commit()
        conn.close()
        return share_id

    def get(self, share_id: str) -> Optional[dict]:
        """取分享內容；不存在或過期回 None（順帶剪除過期）。"""
        conn = sqlite3.connect(self.db_path)
        self._prune(conn)
        conn.commit()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM shares WHERE id = ?", (share_id,)).fetchone()
        conn.close()
        if row is None:
            return None
        return {
            "id": row["id"],
            "type": row["type"],
            "title": row["title"],
            "data": json.loads(row["data"]),
            "created_at": row["created_at"],
        }


# ── lazy 單例 ──
_default_share_store: ShareStore | None = None


def get_share_store() -> ShareStore:
    """共享 ShareStore（lazy；第一次取用才連 db / 建表）。"""
    global _default_share_store
    if _default_share_store is None:
        _default_share_store = ShareStore()
    return _default_share_store
