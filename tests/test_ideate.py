"""core/ideate.py scaffold sanity tests (v4 階段 2 B iter 10).

這支只測 module import + enum + schema 結構, function 真實實作要 iter 11-14
才補。NotImplementedError 故意不測 — 那是設計留白。

設計文件: docs/ideate-design.md
"""
from __future__ import annotations

import pytest


def test_module_imports():
    """core.ideate 載得起來就過 — 防 typo / 循環 import / 缺依賴。"""
    import core.ideate  # noqa: F401


class TestProposalStatusEnum:
    def test_status_values_stable(self):
        from core.ideate import ProposalStatus

        # 鎖 enum 值 — 寫進 proposals.json 後改值會炸舊資料
        assert ProposalStatus.PENDING.value == "pending"
        assert ProposalStatus.APPROVED.value == "approved"
        assert ProposalStatus.IGNORED.value == "ignored"
        assert ProposalStatus.EXPIRED.value == "expired"

    def test_status_set_is_complete(self):
        """完整列舉, 沒漏的 (人為遺失就掛測試)。"""
        from core.ideate import ProposalStatus

        all_values = {s.value for s in ProposalStatus}
        assert all_values == {"pending", "approved", "ignored", "expired"}


class TestScaffoldStubsRaise:
    """確認 function 簽名穩定 — 改簽名前先改測試 (review gate)."""

    def test_scan_changed_files_signature_and_stub(self):
        from core.ideate import IdeateConfig, scan_changed_files

        # 空 config 也應該過 type check, raise NotImplementedError 而非 TypeError
        config: IdeateConfig = {
            "watched_folders": [],
            "llm_model": "gemini-2.5-flash",
            "max_proposals_per_file": 3,
            "enabled": True,
        }
        with pytest.raises(NotImplementedError):
            scan_changed_files(config)

    def test_propose_from_file_signature_and_stub(self):
        from core.ideate import FileCandidate, IdeateConfig, propose_from_file

        candidate: FileCandidate = {
            "path": "/x.pdf",
            "source_type": "exam_pdf",
            "mtime": 0.0,
            "size_bytes": 0,
        }
        config: IdeateConfig = {
            "watched_folders": [],
            "llm_model": "gemini-2.5-flash",
            "max_proposals_per_file": 3,
            "enabled": True,
        }
        with pytest.raises(NotImplementedError):
            propose_from_file(candidate, config)

    def test_dedupe_against_jobs_signature_and_stub(self):
        from core.ideate import dedupe_against_jobs

        # JobStore 暫且傳 None — stub 不會用到, raise NotImplementedError
        with pytest.raises(NotImplementedError):
            dedupe_against_jobs([], None)  # type: ignore[arg-type]
