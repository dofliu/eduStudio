"""server.runner._rewrite_deck_intros_inplace — iter 42 IO wrapper 安全鎖.

iter 42 上線後沒對應直接測試: 核心 `rewrite_deck_intros` 純函式在
tests/test_intro_rewriter.py 已有覆蓋, 但 runner 內這層 IO wrapper
(deck.json 讀 → rewrite → 寫回) 從沒打 — 任何 refactor 不小心動
檔不存在防呆 / ensure_ascii=False / indent=2 / source_type 透傳就直接
上線. 跟 iter 111-123 同思路 (route / helper safety lock).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from core.intro_rewriter import GENERAL_VARIANTS, STUDENT_VARIANTS
from server.jobs import JobStore
from server.runner import _rewrite_deck_intros_inplace


@pytest.fixture
def store_with_job(tmp_path):
    """空 JobStore + 預建 job 目錄 (deck.json 由各 test 自決定要不要寫)."""
    store = JobStore(root=tmp_path)
    job_id = "job_test"
    (tmp_path / job_id).mkdir()
    return store, job_id


def _problems_deck(narration: str = "各位同學好,來看第 1 題") -> dict:
    """v1 exam schema 最小可 rewrite deck.

    注意: 第一個 problem 用 id="q1" 而非 "p1" — _stable_seed("p1") % 8 = 0
    剛好對到 STUDENT_VARIANTS[0]="各位同學好", 替換結果等於原文, 看似沒
    rewrite (其實有跑過, 只是 idempotent). 用 "q1" 對到 STUDENT_VARIANTS[1]
    避免 hash collision 干擾測試斷言.
    """
    return {
        "exam_title": "材料力學 期中考",
        "problems": [
            {
                "id": "q1",
                "steps": [
                    {"display": "題目", "narration": narration},
                    {"display": "解答", "narration": "已知 F=10N, 求 σ"},
                ],
            },
            {
                "id": "q2",
                "steps": [
                    {"display": "題目", "narration": "大家好,看第 2 題"},
                ],
            },
        ],
    }


def _sections_deck(narration: str = "大家好,今天聊聊 React") -> dict:
    """deck (sections) schema 最小可 rewrite deck."""
    return {
        "deck_title": "React 入門",
        "sections": [
            {
                "id": "intro",
                "slides": [
                    {"id": "intro_1", "narration": narration},
                    {"id": "intro_2", "narration": "JSX 是語法糖"},
                ],
            },
        ],
    }


class TestNoOpPath:
    """檔不存在 / 空 deck — 不該炸, 不該誤建檔."""

    def test_missing_deck_json_is_noop(self, store_with_job):
        store, job_id = store_with_job
        # 不寫 deck.json
        _rewrite_deck_intros_inplace(store, job_id, "exam_pdf")
        assert not store.deck_path(job_id).exists()


class TestSchemaDispatch:
    """兩種 schema 都能讀寫."""

    def test_problems_schema_rewrites_first_step(self, store_with_job):
        store, job_id = store_with_job
        deck = _problems_deck("各位同學好,來看第 1 題")
        original_step2 = deck["problems"][0]["steps"][1]["narration"]
        store.deck_path(job_id).write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8",
        )

        _rewrite_deck_intros_inplace(store, job_id, "exam_pdf")

        new_deck = json.loads(store.deck_path(job_id).read_text(encoding="utf-8"))
        # 第一 step narration 開頭該被換 (regex 抓到 greeting + 取代)
        first = new_deck["problems"][0]["steps"][0]["narration"]
        assert first != "各位同學好,來看第 1 題"
        assert "看第 1 題" in first   # 後段內容保留
        # 第二 step 不該被動 (rewrite 只動每題第一步)
        assert new_deck["problems"][0]["steps"][1]["narration"] == original_step2

    def test_sections_schema_rewrites_first_slide(self, store_with_job):
        store, job_id = store_with_job
        deck = _sections_deck("大家好,今天聊聊 React")
        store.deck_path(job_id).write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8",
        )

        _rewrite_deck_intros_inplace(store, job_id, "document")

        new_deck = json.loads(store.deck_path(job_id).read_text(encoding="utf-8"))
        first = new_deck["sections"][0]["slides"][0]["narration"]
        assert first != "大家好,今天聊聊 React"
        assert "今天聊聊 React" in first
        # 第二 slide 不該被動
        assert new_deck["sections"][0]["slides"][1]["narration"] == "JSX 是語法糖"


class TestSourceTypeMapping:
    """source_type → audience pool 對應, 驗 IO wrapper 把 source_type_value
    正確透傳給 rewrite_deck_intros (不會傳成 None / 寫死字串)."""

    def test_exam_pdf_uses_student_variant(self, store_with_job):
        store, job_id = store_with_job
        deck = _problems_deck("各位同學好,來看這題")
        store.deck_path(job_id).write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8",
        )

        _rewrite_deck_intros_inplace(store, job_id, "exam_pdf")

        new_deck = json.loads(store.deck_path(job_id).read_text(encoding="utf-8"))
        first = new_deck["problems"][0]["steps"][0]["narration"]
        head = first.split(",")[0]
        assert head in STUDENT_VARIANTS, f"head={head!r} 不在 STUDENT_VARIANTS"

    def test_document_uses_general_variant(self, store_with_job):
        store, job_id = store_with_job
        deck = _sections_deck("大家好,今天聊聊 React")
        store.deck_path(job_id).write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8",
        )

        _rewrite_deck_intros_inplace(store, job_id, "document")

        new_deck = json.loads(store.deck_path(job_id).read_text(encoding="utf-8"))
        first = new_deck["sections"][0]["slides"][0]["narration"]
        head = first.split(",")[0]
        assert head in GENERAL_VARIANTS, f"head={head!r} 不在 GENERAL_VARIANTS"

    def test_unknown_source_type_falls_back_to_student(self, store_with_job):
        """AUDIENCE_BY_SOURCE_TYPE.get(source_type, "student") fallback —
        若日後新加 source_type 但忘更新對應 map, 不該炸, 走 student 保守選."""
        store, job_id = store_with_job
        deck = _problems_deck("大家好,來看這題")
        store.deck_path(job_id).write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8",
        )

        _rewrite_deck_intros_inplace(store, job_id, "bogus_new_source_type")

        new_deck = json.loads(store.deck_path(job_id).read_text(encoding="utf-8"))
        first = new_deck["problems"][0]["steps"][0]["narration"]
        head = first.split(",")[0]
        assert head in STUDENT_VARIANTS


class TestWriteFormat:
    """寫回格式契約: ensure_ascii=False + indent=2 (人讀 / git diff 友善).
    任何 refactor 不該偷改成 ensure_ascii=True 把中文變成 \\uXXXX."""

    def test_writes_chinese_without_unicode_escape(self, store_with_job):
        store, job_id = store_with_job
        deck = _problems_deck("各位同學好,來看這題")
        store.deck_path(job_id).write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8",
        )

        _rewrite_deck_intros_inplace(store, job_id, "exam_pdf")

        raw = store.deck_path(job_id).read_text(encoding="utf-8")
        assert "\\u" not in raw, "ensure_ascii=False 被改回 True, 中文被 escape"
        # 顯式驗中文字仍是原字 (不只是檢 \u prefix)
        assert "材料力學" in raw

    def test_writes_indent_2_pretty_json(self, store_with_job):
        store, job_id = store_with_job
        deck = _problems_deck()
        store.deck_path(job_id).write_text(
            json.dumps(deck), encoding="utf-8",   # 故意寫單行
        )

        _rewrite_deck_intros_inplace(store, job_id, "exam_pdf")

        raw = store.deck_path(job_id).read_text(encoding="utf-8")
        assert "\n" in raw, "indent=2 沒套, 寫回成單行"
        # 至少有一行以「  」(2 空白) 開頭, 證明 indent 真套上
        assert any(line.startswith("  ") for line in raw.splitlines())


class TestUnknownSchema:
    """deck 既無 problems 又無 sections — rewrite_deck_intros 原樣回, IO
    wrapper 仍走完 write_back 流程 (不該因為「沒改」就 skip write,
    避免下次 read 拿到不一致 indent / encoding 的舊檔)."""

    def test_unknown_schema_still_writes_back(self, store_with_job):
        store, job_id = store_with_job
        deck = {"foo": "bar", "weird": [1, 2, 3]}
        store.deck_path(job_id).write_text(
            json.dumps(deck), encoding="utf-8",
        )

        # 不該炸
        _rewrite_deck_intros_inplace(store, job_id, "exam_pdf")

        new_deck = json.loads(store.deck_path(job_id).read_text(encoding="utf-8"))
        assert new_deck == deck, "未知 schema 該原樣保留"


class TestLogging:
    """logger.info 該寫出 source_type, debug / 用戶閱讀 log 找得到改寫紀錄."""

    def test_logs_source_type_at_info_level(self, store_with_job, caplog):
        store, job_id = store_with_job
        deck = _problems_deck()
        store.deck_path(job_id).write_text(
            json.dumps(deck, ensure_ascii=False), encoding="utf-8",
        )

        with caplog.at_level(logging.INFO, logger="server.runner"):
            _rewrite_deck_intros_inplace(store, job_id, "exam_pdf")

        # logger.info("intro 多樣化套用完成 (source_type=%s)", source_type_value)
        assert any("exam_pdf" in rec.getMessage() for rec in caplog.records), (
            f"未在 INFO log 找到 source_type=exam_pdf: {[r.getMessage() for r in caplog.records]}"
        )
