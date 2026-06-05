"""core/storage/history.py 測試（eduStudio 合併 B-2）。純 SQLite，tmp db 隔離。"""
from __future__ import annotations

from pathlib import Path

from core.storage.history import HistoryManager


def _mgr(tmp_path: Path) -> HistoryManager:
    return HistoryManager(db_path=str(tmp_path / "h.db"))


def test_add_and_get(tmp_path):
    m = _mgr(tmp_path)
    m.add_history("text", "en_US", "zh_TW", "hello", "你好", details={"k": "v"})
    rows = m.get_history()
    assert len(rows) == 1
    assert rows[0]["original_content"] == "hello"
    assert rows[0]["translated_content"] == "你好"
    assert rows[0]["details"] == {"k": "v"}


def test_type_filter(tmp_path):
    m = _mgr(tmp_path)
    m.add_history("text", "en_US", "zh_TW", "a", "A")
    m.add_history("image", "en_US", "zh_TW", "b", "B")
    assert len(m.get_history(type_filter="image")) == 1
    assert m.get_history(type_filter="image")[0]["type"] == "image"


def test_clear(tmp_path):
    m = _mgr(tmp_path)
    m.add_history("text", "en_US", "zh_TW", "a", "A")
    m.clear_history()
    assert m.get_history() == []


def test_no_details_defaults_empty(tmp_path):
    m = _mgr(tmp_path)
    m.add_history("text", "en_US", "zh_TW", "a", "A")
    assert m.get_history()[0]["details"] == {}


def test_lazy_singleton(monkeypatch, tmp_path):
    import core.storage.history as mod
    monkeypatch.setattr(mod, "_default_history", None)
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "lazy_h.db"))
    a = mod.get_history_manager()
    b = mod.get_history_manager()
    assert a is b
    assert (tmp_path / "lazy_h.db").exists()
