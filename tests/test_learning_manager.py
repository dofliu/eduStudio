"""core/learning/manager.py 測試（eduStudio 合併 B-2）。

純 SQLite，用 tmp db 隔離。驗 CRUD、SM-2 排程、UNIQUE 去重、統計、lazy 單例。
"""
from __future__ import annotations

from pathlib import Path

from core.learning.manager import LearningManager


def _mgr(tmp_path: Path) -> LearningManager:
    return LearningManager(db_path=str(tmp_path / "learning.db"))


def test_add_and_get_vocabulary(tmp_path):
    m = _mgr(tmp_path)
    rid = m.add_vocabulary("apple", "蘋果", "en_US", "zh_TW", part_of_speech="n")
    assert rid > 0
    vocab = m.get_vocabulary()
    assert len(vocab) == 1
    assert vocab[0]["word"] == "apple" and vocab[0]["meaning"] == "蘋果"
    assert vocab[0]["ease_factor"] == 2.5  # SM-2 起始值


def test_unique_constraint_dedup(tmp_path):
    m = _mgr(tmp_path)
    m.add_vocabulary("apple", "蘋果", "en_US", "zh_TW")
    m.add_vocabulary("apple", "蘋果", "en_US", "zh_TW")  # 同 word+langs → INSERT OR IGNORE
    assert len(m.get_vocabulary()) == 1


def test_batch_add(tmp_path):
    m = _mgr(tmp_path)
    n = m.add_vocabulary_batch([
        {"word": "a", "meaning": "1", "source_lang": "en_US", "target_lang": "zh_TW"},
        {"word": "b", "meaning": "2", "source_lang": "en_US", "target_lang": "zh_TW"},
    ])
    assert n == 2 and len(m.get_vocabulary()) == 2


def test_get_due_cards_includes_new(tmp_path):
    # 新卡 next_review = now → 立即到期
    m = _mgr(tmp_path)
    m.add_vocabulary("x", "X", "en_US", "zh_TW")
    assert len(m.get_due_cards()) == 1


def test_review_card_sm2_correct_progression(tmp_path):
    m = _mgr(tmp_path)
    rid = m.add_vocabulary("w", "字", "en_US", "zh_TW")
    # 第一次答對(quality 5)：interval → 1, reps → 1
    r1 = m.review_card(rid, 5)
    assert r1["new_interval_days"] == 1
    # 第二次答對：interval → 6
    r2 = m.review_card(rid, 5)
    assert r2["new_interval_days"] == 6
    # ease_factor 答對會上升（>2.5）
    assert r2["new_ease_factor"] >= 2.5


def test_review_card_wrong_resets(tmp_path):
    m = _mgr(tmp_path)
    rid = m.add_vocabulary("w", "字", "en_US", "zh_TW")
    m.review_card(rid, 5)
    m.review_card(rid, 5)
    # 答錯(quality 1)：reps 重置、interval → 1、ef 下降但不低於 1.3
    r = m.review_card(rid, 1)
    assert r["new_interval_days"] == 1
    assert r["new_ease_factor"] >= 1.3


def test_review_missing_card(tmp_path):
    m = _mgr(tmp_path)
    assert "error" in m.review_card(999, 5)


def test_sessions_and_stats(tmp_path):
    m = _mgr(tmp_path)
    m.add_vocabulary("a", "1", "en_US", "zh_TW")
    m.log_session("dictation", "en_US", "zh_TW", score=90, details={"foo": "bar"})
    stats = m.get_stats()
    assert stats["total_words"] == 1
    assert stats["total_sessions"] == 1
    assert "dictation" in stats["session_breakdown"]


def test_lazy_singleton(monkeypatch, tmp_path):
    # get_learning_manager 第一次取用才初始化（不在 import 期）
    import core.learning.manager as mod
    monkeypatch.setattr(mod, "_default_manager", None)
    monkeypatch.setenv("LEARNING_DB_PATH", str(tmp_path / "lazy.db"))
    inst1 = mod.get_learning_manager()
    inst2 = mod.get_learning_manager()
    assert inst1 is inst2  # 同一單例
    assert (tmp_path / "lazy.db").exists()
