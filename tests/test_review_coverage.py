"""T0-3 自動校驗覆蓋率測試 — `core/review_assist.analyze_coverage`。

問題:確定性校驗是高精度低召回,含三角 / 開根號的步驟一律跳過不產 flag。
reviewer 看到「沒有 ⚠」會誤讀成「已驗證」,但材力 / 動力學幾乎每步都有 sin/cos/√,
= 最容易按錯計算機的步驟恰好完全沒被檢查。修法不是放寬檢查(會犧牲精度),
而是**誠實揭露**「N 步無法自動驗證」。
"""
from __future__ import annotations

import json

import pytest

from core.review_assist import (
    COVERAGE_REASONS,
    CoverageReport,
    analyze_coverage,
    check_deck,
)


def _deck(*displays: str) -> dict:
    return {
        "problems": [{
            "id": "q1",
            "steps": [{"display": d, "narration": ""} for d in displays],
        }]
    }


class TestStepClassification:
    @pytest.mark.parametrize(("display", "verified", "reason"), [
        # 兩段以上可求值 → 真的驗到了
        ("σ = 50000 / 500 = 100 MPa", True, ""),
        ("F = 2 * 3 = 6", True, ""),
        # T0-3 點名的那一類:含函式
        ("θ = sin(30°) × 2 = 1.0", False, "function"),
        ("d = √(3² + 4²) = 5", False, "function"),
        ("v = tan(θ) * L", False, "function"),
        ("E = log(100) = 2", False, "function"),
        ("Σ F = 0", False, "function"),
        # 純符號公式
        ("σ = P / A", False, "symbolic"),
        ("ε = σ / E", False, "symbolic"),
        # 只有一個數值
        ("F = 250 N", False, "single_value"),
        # 空
        ("", False, "empty"),
        ("   ", False, "empty"),
    ])
    def test_classification(self, display, verified, reason):
        rep = analyze_coverage(_deck(display))
        assert rep.total_steps == 1
        step = rep.steps[0]
        assert step.verified is verified
        assert step.reason == reason

    def test_lowercase_sigma_is_not_a_function(self):
        """回歸:`Σ` 若用 IGNORECASE 比對會吃掉 `σ`(材力最常見的應力符號),
        害每條 `σ = P / A` 都被誤判成「含函式」而不是「純符號」。"""
        rep = analyze_coverage(_deck("σ = P / A"))
        assert rep.steps[0].reason == "symbolic"

    def test_all_reasons_are_declared(self):
        """分類出來的 reason 一定要在 COVERAGE_REASONS 裡(擋拼錯)。"""
        rep = analyze_coverage(_deck(
            "", "σ = P / A", "F = 250 N", "θ = sin(30°) = 0.5",
        ))
        for step in rep.steps:
            if not step.verified:
                assert step.reason in COVERAGE_REASONS


class TestReportTotals:
    def test_counts_and_reasons(self):
        rep = analyze_coverage(_deck(
            "σ = 50000 / 500 = 100 MPa",   # verified
            "θ = sin(30°) × 2 = 1.0",      # function
            "d = √(2) × 3",                # function
            "σ = P / A",                   # symbolic
            "",                            # empty
        ))
        assert rep.total_steps == 5
        assert rep.verified_steps == 1
        assert rep.unverified_steps == 4
        assert rep.by_reason == {"function": 2, "symbolic": 1, "empty": 1}
        assert rep.ratio == pytest.approx(0.2)

    def test_multiple_problems_are_aggregated(self):
        deck = {"problems": [
            {"id": "q1", "steps": [{"display": "F = 2 * 3 = 6"}]},
            {"id": "q2", "steps": [{"display": "θ = sin(1) = 0.84"}]},
        ]}
        rep = analyze_coverage(deck)
        assert rep.total_steps == 2
        assert rep.verified_steps == 1
        assert {s.problem_id for s in rep.steps} == {"q1", "q2"}

    def test_ratio_zero_when_no_steps(self):
        assert analyze_coverage({"problems": []}).ratio == 0.0


class TestSummaryWording:
    """摘要文字是這項修正的重點 —— 不能讓 reviewer 讀成「已驗證」。"""

    def test_mentions_unverified_count_and_warns(self):
        rep = analyze_coverage(_deck("θ = sin(30°) = 0.5", "F = 2 * 3 = 6"))
        msg = rep.summary()
        assert "1" in msg
        assert "無法自動驗證" in msg
        assert "人工複核" in msg

    def test_never_claims_verified_even_when_all_checked(self):
        """全部驗到時也不能說「已驗證」——算術對得上不等於物理正確。"""
        rep = analyze_coverage(_deck("F = 2 * 3 = 6"))
        msg = rep.summary()
        assert "已驗證" not in msg
        assert "人工複核" in msg

    def test_empty_deck_summary(self):
        assert "沒有可檢查" in analyze_coverage({"problems": []}).summary()


class TestFailOpen:
    """跟 check_deck 一樣:壞輸入不可炸,不可卡 review。"""

    @pytest.mark.parametrize("bad", [None, [], "字串", 42, {"problems": "not a list"}])
    def test_bad_input_returns_empty_report(self, bad):
        rep = analyze_coverage(bad)
        assert isinstance(rep, CoverageReport)
        assert rep.total_steps == 0

    def test_non_dict_problems_and_steps_skipped(self):
        deck = {"problems": [None, 42, {"id": "q1", "steps": [None, {"display": "F = 2 * 3 = 6"}]}]}
        rep = analyze_coverage(deck)
        assert rep.total_steps == 1
        assert rep.verified_steps == 1


class TestAgreesWithCheckDeck:
    """覆蓋率與實際檢查必須同一套判斷,不能各說各話。"""

    def test_verified_step_can_produce_arithmetic_flag(self):
        """被判定「驗到了」的步驟,算錯時確實會出 flag。"""
        deck = _deck("σ = 50000 / 500 = 999 MPa")
        assert analyze_coverage(deck).steps[0].verified is True
        flags = check_deck(deck)
        assert [f.kind for f in flags] == ["arithmetic"]

    def test_unverified_step_never_produces_arithmetic_flag(self):
        """判定「沒驗到」的步驟,即使數字是錯的也不會有 arithmetic flag ——
        這正是 T0-3 要揭露的盲區。"""
        deck = _deck("θ = sin(30°) = 999")
        assert analyze_coverage(deck).steps[0].verified is False
        assert [f.kind for f in check_deck(deck) if f.kind == "arithmetic"] == []


class TestPipelineAndEndpoint:
    def test_write_review_flags_also_writes_coverage(self, tmp_path):
        from server.jobs import JobStore
        from server.runner import write_review_flags
        from server.schemas import CreateJobRequest, JobSource, SourceType

        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.EXAM_PDF, source=JobSource(path="/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(
            json.dumps(_deck("θ = sin(30°) = 0.5", "F = 2 * 3 = 6")),
            encoding="utf-8",
        )

        write_review_flags(store, rec.id)

        cov_path = store.review_coverage_path(rec.id)
        assert cov_path.exists()
        cov = json.loads(cov_path.read_text(encoding="utf-8"))
        assert cov["total_steps"] == 2
        assert cov["unverified_steps"] == 1
        assert cov["by_reason"] == {"function": 1}
        assert "無法自動驗證" in cov["summary"]

    def test_flags_file_stays_a_bare_list(self, tmp_path):
        """覆蓋率分檔存 —— review_flags.json 的既有格式(裸 list)不能被改動,
        否則舊 job 與既有端點要寫 migration(硬規則 #7)。"""
        from server.jobs import JobStore
        from server.runner import write_review_flags
        from server.schemas import CreateJobRequest, JobSource, SourceType

        store = JobStore(root=tmp_path / "jobs")
        rec = store.create(CreateJobRequest(
            source_type=SourceType.EXAM_PDF, source=JobSource(path="/fake.pdf"),
        ))
        store.deck_path(rec.id).write_text(json.dumps(_deck("F = 2 * 3 = 6")), encoding="utf-8")

        write_review_flags(store, rec.id)

        loaded = json.loads(store.review_flags_path(rec.id).read_text(encoding="utf-8"))
        assert isinstance(loaded, list)
