"""翻譯歷史紀錄（從 translateGemma history.py 收編，eduStudio 合併 B-2）。

移植調整:db 路徑走 core.config.get_history_db_path()（集中 + env 可覆寫）；改 lazy 單例
去 import 期建 db 的 side-effect。純 stdlib（sqlite3/json/datetime）。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from core import config


class HistoryManager:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.get_history_db_path()
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            source_lang TEXT,
            target_lang TEXT,
            original_content TEXT,
            translated_content TEXT,
            details TEXT
        )
        """)
        conn.commit()
        conn.close()

    def add_history(self, type: str, source_lang: str, target_lang: str,
                    original_content: str, translated_content: str,
                    details: Optional[Dict[str, Any]] = None) -> None:
        """新增一筆歷史。type ∈ text/learning/image/pdf/voice/video。"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        timestamp = datetime.now().isoformat()
        details_json = json.dumps(details, ensure_ascii=False) if details else "{}"
        cursor.execute("""
        INSERT INTO history (timestamp, type, source_lang, target_lang, original_content, translated_content, details)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, type, source_lang, target_lang, original_content, translated_content, details_json))
        conn.commit()
        conn.close()

    def get_history(self, limit: int = 50, offset: int = 0,
                    type_filter: Optional[str] = None) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = "SELECT * FROM history"
        params: list = []
        if type_filter:
            query += " WHERE type = ?"
            params.append(type_filter)
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cursor.execute(query, params)
        rows = cursor.fetchall()
        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "timestamp": row["timestamp"],
                "type": row["type"],
                "source_lang": row["source_lang"],
                "target_lang": row["target_lang"],
                "original_content": row["original_content"],
                "translated_content": row["translated_content"],
                "details": json.loads(row["details"]) if row["details"] else {},
            })
        conn.close()
        return results

    def clear_history(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history")
        conn.commit()
        conn.close()


# ── lazy 單例（避免 import 期建 db）──
_default_history: HistoryManager | None = None


def get_history_manager() -> HistoryManager:
    """共享 HistoryManager（lazy；第一次取用才連 db / 建表）。"""
    global _default_history
    if _default_history is None:
        _default_history = HistoryManager()
    return _default_history
