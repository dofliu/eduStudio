"""視覺成品素材庫（eduStudio #6：成功生成就自動保存，免手動加入 Project）。

劉老師回報：原本視覺成品要手動「加入 Project」才會留下。改成每次成功生成（圖卡/海報/簡報）
由 /api/generate 自動寫進這個庫，素材頁可直接看到全部紀錄、可刪除。沿 share_store 的
SQLite + lazy 單例模式；無 TTL（素材要長期保存），但保留筆數上限避免無限長大。
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Optional

from core import config

_MAX_ITEMS = 300  # 上限：超過就剪掉最舊的（base64 圖佔空間，個人工具量級夠用）


class VisualLibraryStore:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.get_visual_library_db_path()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS visual_assets (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT DEFAULT '',
            thumb TEXT DEFAULT '',
            data TEXT NOT NULL,
            created_at REAL NOT NULL
        )
        """)
        conn.commit()
        conn.close()

    def _prune(self, conn: sqlite3.Connection) -> None:
        """超過 _MAX_ITEMS 就刪最舊（保留最新 _MAX_ITEMS 筆）。"""
        conn.execute(
            "DELETE FROM visual_assets WHERE id NOT IN "
            "(SELECT id FROM visual_assets ORDER BY created_at DESC LIMIT ?)",
            (_MAX_ITEMS,),
        )

    def add(self, asset_type: str, title: str, data: Any, thumb: str = "") -> str:
        """新增一筆成品，回 id。data 任意 JSON-serializable（海報 {imageUrl} 或簡報 deck）。
        thumb：清單縮圖（海報＝imageUrl；簡報＝首張有圖的 slide imageUrl，可空）。
        """
        asset_id = uuid.uuid4().hex[:12]
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO visual_assets (id, type, title, thumb, data, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (asset_id, asset_type, title or "", thumb or "",
             json.dumps(data, ensure_ascii=False), time.time()),
        )
        self._prune(conn)
        conn.commit()
        conn.close()
        return asset_id

    def list(self, limit: int = _MAX_ITEMS) -> list[dict]:
        """清單（新到舊），含 thumb 供直接顯示，不含完整 data（清單輕量）。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, type, title, thumb, created_at FROM visual_assets "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get(self, asset_id: str) -> Optional[dict]:
        """取單筆完整內容（含 data）；不存在回 None。"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM visual_assets WHERE id = ?", (asset_id,)).fetchone()
        conn.close()
        if row is None:
            return None
        out = dict(row)
        out["data"] = json.loads(out["data"])
        return out

    def delete(self, asset_id: str) -> bool:
        """刪一筆，回是否真的刪到。"""
        conn = sqlite3.connect(self.db_path)
        cur = conn.execute("DELETE FROM visual_assets WHERE id = ?", (asset_id,))
        conn.commit()
        deleted = cur.rowcount > 0
        conn.close()
        return deleted


# ── lazy 單例 ──
_default_store: VisualLibraryStore | None = None


def get_visual_library() -> VisualLibraryStore:
    """共享 VisualLibraryStore（lazy；第一次取用才連 db / 建表）。"""
    global _default_store
    if _default_store is None:
        _default_store = VisualLibraryStore()
    return _default_store
