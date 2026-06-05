"""core/infocards/share_store 測試（Phase C-4）。SQLite，tmp db 隔離。"""
from __future__ import annotations

import time
from pathlib import Path

from core.infocards.share_store import ShareStore


def _store(tmp_path: Path) -> ShareStore:
    return ShareStore(db_path=str(tmp_path / "shares.db"))


def test_create_get_round_trip(tmp_path):
    s = _store(tmp_path)
    sid = s.create("poster", "靜力學海報", {"imageUrl": "data:...", "prompt": "p"})
    assert len(sid) == 12
    got = s.get(sid)
    assert got["type"] == "poster"
    assert got["title"] == "靜力學海報"
    assert got["data"]["prompt"] == "p"


def test_get_missing_returns_none(tmp_path):
    assert _store(tmp_path).get("nope") is None


def test_expired_pruned(tmp_path, monkeypatch):
    s = _store(tmp_path)
    sid = s.create("comic", "t", {"x": 1})
    # 把 created_at 改成 8 天前 → 下次 get 會被剪除
    import sqlite3
    conn = sqlite3.connect(s.db_path)
    conn.execute("UPDATE shares SET created_at = ?", (time.time() - 8 * 24 * 3600,))
    conn.commit()
    conn.close()
    assert s.get(sid) is None


def test_lazy_singleton(monkeypatch, tmp_path):
    import core.infocards.share_store as mod
    monkeypatch.setattr(mod, "_default_share_store", None)
    monkeypatch.setenv("SHARE_DB_PATH", str(tmp_path / "lazy_shares.db"))
    a = mod.get_share_store()
    b = mod.get_share_store()
    assert a is b
    assert (tmp_path / "lazy_shares.db").exists()
