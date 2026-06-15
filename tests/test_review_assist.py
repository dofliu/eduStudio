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


# ---------- 單位 / 量綱換算校驗(F9-1b) ----------
def test_unit_conversion_mismatch_flagged():
    # 50 kN 與 50 N 差 1000 倍,剝單位後的算術看不出來,要靠量綱校驗抓
    flags = check_deck(_deck([{"display": "50 kN = 50 N", "narration": ""}]))
    units = [f for f in flags if f.kind == "unit"]
    assert len(units) == 1
    assert units[0].severity == "warn"
    assert units[0].problem_id == "q1"
    assert units[0].step_index == 0


def test_unit_conversion_correct_not_flagged():
    for disp in ["50 kN = 50000 N", "1 m = 100 cm", "1 GPa = 1000 MPa", "500 mm² = 0.0005 m²"]:
        flags = check_deck(_deck([{"display": disp, "narration": ""}]))
        assert [f for f in flags if f.kind == "unit"] == [], disp
        # 正確換算也不該被算術校驗誤標(剝單位的數值不同但物理量相等)
        assert [f for f in flags if f.kind == "arithmetic"] == [], disp


def test_unit_dimension_mismatch_flagged():
    flags = check_deck(_deck([{"display": "100 MPa = 100 N", "narration": ""}]))
    units = [f for f in flags if f.kind == "unit"]
    assert len(units) == 1
    assert units[0].severity == "warn"
    assert "量綱" in units[0].message


def test_unit_wrong_conversion_flagged():
    flags = check_deck(_deck([{"display": "1 m = 50 cm", "narration": ""}]))
    assert any(f.kind == "unit" for f in flags)


def test_unrecognized_units_skipped_no_false_positive():
    # 白名單外的單位(km/h、m/s、N·m)不認得 → 既不出 unit flag,也不被算術誤標
    for disp in ["100 km/h = 27.8 m/s", "M = 5 N·m = 5000 N·mm"]:
        flags = check_deck(_deck([{"display": disp, "narration": ""}]))
        assert flags == [], disp


def test_single_unit_segment_not_unit_flagged():
    # 只有一段帶單位(常見的 "P = 50 kN" 賦值)→ 無從比換算,不標
    for disp in ["P = 50 kN", "σ = 50000 / 500 = 100 MPa", "L = 2 m,  A = 500 mm²"]:
        flags = check_deck(_deck([{"display": disp, "narration": ""}]))
        assert [f for f in flags if f.kind == "unit"] == [], disp


def test_unit_chain_of_three_consistent():
    flags = check_deck(_deck([{"display": "1 m = 100 cm = 1000 mm", "narration": ""}]))
    assert [f for f in flags if f.kind == "unit"] == []


def test_unit_in_flag_kinds():
    assert "unit" in FLAG_KINDS


# ---------- 符號漂移校驗(symbol，F9-1b 高精度子集) ----------
def test_symbol_drift_inverted_formula_flagged():
    # σ = P / A 後又 σ = A / P:變數相同({P,A})但公式倒過來 → 高機率筆誤,標 symbol
    flags = check_deck(
        _deck(
            [
                {"display": "σ = P / A", "narration": ""},
                {"display": "σ = A / P = 0.01", "narration": ""},
            ]
        )
    )
    sym = [f for f in flags if f.kind == "symbol"]
    assert len(sym) == 1
    assert sym[0].severity == "warn"
    assert sym[0].problem_id == "q1"
    assert sym[0].step_index == 1  # 標在較後出現的定義那一步
    assert "σ" in sym[0].message


def test_symbol_drift_operator_flip_flagged():
    # P · A vs P / A:同變數集、換了運算符 → 標
    flags = check_deck(
        _deck(
            [
                {"display": "σ = P × A", "narration": ""},
                {"display": "σ = P / A", "narration": ""},
            ]
        )
    )
    assert any(f.kind == "symbol" for f in flags)


def test_symbol_drift_legit_substitution_not_flagged():
    # σ = P / A → σ = P / (π r²):變數集不同(代入 A = π r²)＝合法推導,不標
    flags = check_deck(
        _deck(
            [
                {"display": "σ = P / A", "narration": ""},
                {"display": "σ = P / (π r²)", "narration": ""},
            ]
        )
    )
    assert [f for f in flags if f.kind == "symbol"] == []


def test_symbol_drift_different_variable_not_flagged():
    # σ = P / A 與 σ = F / A:不同變數(P vs F,可能是不同力符號)→ 變數集不同,不亂標
    flags = check_deck(
        _deck(
            [
                {"display": "σ = P / A", "narration": ""},
                {"display": "σ = F / A", "narration": ""},
            ]
        )
    )
    assert [f for f in flags if f.kind == "symbol"] == []


def test_symbol_drift_numeric_substitution_not_flagged():
    # σ = P / A 後接數值代入 σ = 50000 / 500 = 100 MPa:含數字的段不是符號定義,不標
    flags = check_deck(
        _deck(
            [
                {"display": "σ = P / A", "narration": ""},
                {"display": "σ = 50000 / 500 = 100 MPa", "narration": ""},
            ]
        )
    )
    assert [f for f in flags if f.kind == "symbol"] == []


def test_symbol_drift_same_formula_repeated_not_flagged():
    # 同一公式重複出現(只是格式不同)→ 不標
    flags = check_deck(
        _deck(
            [
                {"display": "σ = P / A", "narration": ""},
                {"display": "σ = P/A", "narration": ""},
            ]
        )
    )
    assert [f for f in flags if f.kind == "symbol"] == []


def test_symbol_drift_isolated_per_problem():
    # 跨題不串:q1 的 σ=P/A 與 q2 的 σ=A/P 不算衝突
    deck = {
        "problems": [
            {"id": "q1", "steps": [{"display": "σ = P / A", "narration": ""}]},
            {"id": "q2", "steps": [{"display": "σ = A / P", "narration": ""}]},
        ]
    }
    assert [f for f in check_deck(deck) if f.kind == "symbol"] == []


def test_symbol_drift_single_definition_not_flagged():
    # 只定義一次(其餘步驟是數值代入)→ 沒有可比對的第二條公式,不標
    flags = check_deck(_deck([{"display": "σ = P / A", "narration": ""}]))
    assert [f for f in flags if f.kind == "symbol"] == []


def test_symbol_in_flag_kinds():
    assert "symbol" in FLAG_KINDS


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
