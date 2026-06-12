"""F9-1a：review 數值二次校驗(確定性一致性檢查)測試。

全 offline——純函式 fixture in → flags out,不打任何 API。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.review_assist import (
    DEFAULT_REL_TOL,
    FLAG_KINDS,
    ReviewFlag,
    check_deck,
)


def _deck(steps, *, pid="q1"):
    return {"problems": [{"id": pid, "steps": steps}]}


# ---------- schema / type guard ----------
def test_flag_schema_defaults_source_deterministic():
    f = ReviewFlag(
        problem_id="q1", step_index=0, kind="arithmetic", severity="warn", message="x"
    )
    assert f.source == "deterministic"


def test_flag_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ReviewFlag(
            problem_id="q1", step_index=0, kind="bogus", severity="warn", message="x"
        )


def test_flag_rejects_unknown_severity_and_source():
    with pytest.raises(ValidationError):
        ReviewFlag(
            problem_id="q1", step_index=0, kind="arithmetic", severity="error", message="x"
        )
    with pytest.raises(ValidationError):
        ReviewFlag(
            problem_id="q1",
            step_index=0,
            kind="arithmetic",
            severity="warn",
            message="x",
            source="psychic",
        )


# ---------- mock_output(真實離線資料)應乾淨無 flag ----------
def test_mock_output_clean():
    from solve import mock_output

    assert check_deck(mock_output()) == []


# ---------- 算術校驗 ----------
def test_arithmetic_mismatch_flagged():
    flags = check_deck(_deck([{"display": "σ = 50000 / 500 = 1000 MPa", "narration": ""}]))
    arith = [f for f in flags if f.kind == "arithmetic"]
    assert len(arith) == 1
    assert arith[0].severity == "warn"
    assert arith[0].problem_id == "q1"
    assert arith[0].step_index == 0


def test_arithmetic_correct_not_flagged():
    flags = check_deck(_deck([{"display": "σ = 50000 / 500 = 100 MPa", "narration": ""}]))
    assert [f for f in flags if f.kind == "arithmetic"] == []


def test_arithmetic_unicode_operators():
    # × ÷ ^ 與真減號都要被認得
    bad = check_deck(_deck([{"display": "2 × 3 = 7", "narration": ""}]))
    assert any(f.kind == "arithmetic" for f in bad)
    good = check_deck(_deck([{"display": "2 × 3 = 6", "narration": ""}]))
    assert [f for f in good if f.kind == "arithmetic"] == []
    pw = check_deck(_deck([{"display": "2 ^ 3 = 9", "narration": ""}]))
    assert any(f.kind == "arithmetic" for f in pw)


def test_symbolic_segments_skipped_no_false_positive():
    # 純符號 / 逗號分隔賦值 / 含函式的段不能安全求值 → 不亂標
    for disp in ["σ = P / A", "L = 2 m,  A = 500 mm²", "F1 = F × cos 30°"]:
        flags = check_deck(_deck([{"display": disp, "narration": ""}]))
        assert [f for f in flags if f.kind == "arithmetic"] == [], disp


def test_arithmetic_tolerance_allows_rounding():
    # 1/3 = 0.333 在 1% 容差內,不標
    flags = check_deck(_deck([{"display": "1 / 3 = 0.333", "narration": ""}]))
    assert [f for f in flags if f.kind == "arithmetic"] == []


def test_custom_tolerance():
    # 收緊容差後,捨入差被視為不一致
    deck = _deck([{"display": "1 / 3 = 0.333", "narration": ""}])
    assert any(f.kind == "arithmetic" for f in check_deck(deck, rel_tol=1e-6))


def test_chain_of_three_equalities():
    bad = check_deck(_deck([{"display": "10 = 5 + 5 = 11", "narration": ""}]))
    assert any(f.kind == "arithmetic" for f in bad)
    good = check_deck(_deck([{"display": "10 = 5 + 5 = 10", "narration": ""}]))
    assert [f for f in good if f.kind == "arithmetic"] == []


# ---------- narration 數字對齊 ----------
def test_narration_mismatch_flagged():
    flags = check_deck(
        _deck([{"display": "x = 10 / 2 = 5", "narration": "兩者相除等於 50。"}])
    )
    nm = [f for f in flags if f.kind == "narration_mismatch"]
    assert len(nm) == 1
    assert nm[0].severity == "info"


def test_narration_result_present_not_flagged():
    flags = check_deck(
        _deck([{"display": "x = 10 / 2 = 5", "narration": "兩者相除等於 5。"}])
    )
    assert [f for f in flags if f.kind == "narration_mismatch"] == []


def test_narration_skipped_when_no_numbers_or_empty():
    assert check_deck(_deck([{"display": "σ = P / A", "narration": "應力定義。"}])) == []
    assert check_deck(_deck([{"display": "x = 5", "narration": ""}])) == []


def test_narration_rounding_within_tolerance():
    flags = check_deck(
        _deck([{"display": "1 / 3 = 0.333", "narration": "約等於 0.3333。"}])
    )
    assert [f for f in flags if f.kind == "narration_mismatch"] == []


# ---------- 結構 / robustness ----------
def test_non_dict_and_empty_deck():
    assert check_deck(None) == []  # type: ignore[arg-type]
    assert check_deck({}) == []
    assert check_deck({"problems": []}) == []
    assert check_deck({"problems": "nope"}) == []


def test_problem_id_fallback_and_indexing():
    deck = {
        "problems": [
            {"steps": [{"display": "1 = 2", "narration": ""}]},  # 無 id → q1
            {"id": "qX", "steps": [{"display": "3 = 4", "narration": ""}]},
        ]
    }
    flags = check_deck(deck)
    arith = {(f.problem_id, f.step_index) for f in flags if f.kind == "arithmetic"}
    assert ("q1", 0) in arith
    assert ("qX", 0) in arith


def test_malformed_steps_fail_open():
    # 非 dict step / 怪 display 不可丟例外,只是不出 flag
    deck = {
        "problems": [
            {"id": "q1", "steps": ["not a dict", {"display": "= = =", "narration": "x"}, 42]}
        ]
    }
    assert isinstance(check_deck(deck), list)  # 不 raise


def test_safe_eval_rejects_dangerous_input():
    # 含名稱/呼叫的 display 不會被執行,只是無法求值 → 不標、不爆
    deck = _deck([{"display": "__import__('os') = 5", "narration": ""}])
    assert [f for f in check_deck(deck) if f.kind == "arithmetic"] == []


def test_default_tolerance_constant_and_kinds():
    assert 0 < DEFAULT_REL_TOL < 1
    assert {"arithmetic", "narration_mismatch"} <= FLAG_KINDS
