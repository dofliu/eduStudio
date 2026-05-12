"""core/ideate.py tests (v4 階段 2 B iter 10 scaffold + iter 11 scan/save).

設計文件: docs/ideate-design.md
"""
from __future__ import annotations

import os
import time
from pathlib import Path

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


class TestStillStubbed:
    """這些 stub 等 iter 12/13 才實作, 鎖簽名 + raise 行為."""

    def test_propose_from_file_still_stub(self):
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

    def test_dedupe_against_jobs_still_stub(self):
        from core.ideate import dedupe_against_jobs

        with pytest.raises(NotImplementedError):
            dedupe_against_jobs([], None)  # type: ignore[arg-type]


class TestScanChangedFiles:
    """scan_changed_files 實作測試 (iter 11)."""

    @pytest.fixture
    def make_config(self):
        from core.ideate import IdeateConfig

        def _build(folders, enabled=True):
            cfg: IdeateConfig = {
                "watched_folders": folders,
                "llm_model": "gemini-2.5-flash",
                "max_proposals_per_file": 3,
                "enabled": enabled,
            }
            return cfg
        return _build

    def test_empty_folders_returns_empty(self, make_config):
        from core.ideate import scan_changed_files

        result = scan_changed_files(make_config([]))
        assert result == []

    def test_disabled_config_returns_empty_even_with_files(self, tmp_path, make_config):
        from core.ideate import scan_changed_files

        (tmp_path / "exam.pdf").write_bytes(b"%PDF-1.4\n")
        cfg = make_config([
            {"path": str(tmp_path), "source_type": "exam_pdf", "scan_window_days": 14}
        ], enabled=False)
        assert scan_changed_files(cfg) == []

    def test_finds_recent_pdf(self, tmp_path, make_config):
        from core.ideate import scan_changed_files

        f = tmp_path / "midterm.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        cfg = make_config([
            {"path": str(tmp_path), "source_type": "exam_pdf", "scan_window_days": 14}
        ])
        result = scan_changed_files(cfg)
        assert len(result) == 1
        assert result[0]["path"] == str(f.resolve())
        assert result[0]["source_type"] == "exam_pdf"
        assert result[0]["size_bytes"] > 0

    def test_excludes_old_files_outside_window(self, tmp_path, make_config):
        from core.ideate import scan_changed_files

        f = tmp_path / "old.pdf"
        f.write_bytes(b"%PDF-1.4\n")
        # 把 mtime 推回 30 天前, window=14 → 應該被排除
        old_ts = time.time() - 30 * 86400
        os.utime(f, (old_ts, old_ts))

        cfg = make_config([
            {"path": str(tmp_path), "source_type": "exam_pdf", "scan_window_days": 14}
        ])
        assert scan_changed_files(cfg) == []

    def test_excludes_wrong_extension_for_source_type(self, tmp_path, make_config):
        from core.ideate import scan_changed_files

        # exam_pdf 只認 .pdf, .docx 應該被跳過
        (tmp_path / "exam.docx").write_bytes(b"PK\x03\x04")
        cfg = make_config([
            {"path": str(tmp_path), "source_type": "exam_pdf", "scan_window_days": 14}
        ])
        assert scan_changed_files(cfg) == []

    def test_document_type_accepts_md_and_txt(self, tmp_path, make_config):
        from core.ideate import scan_changed_files

        (tmp_path / "note.md").write_text("# hi")
        (tmp_path / "outline.txt").write_text("hi")
        (tmp_path / "img.png").write_bytes(b"\x89PNG")  # 應排除
        cfg = make_config([
            {"path": str(tmp_path), "source_type": "document", "scan_window_days": 14}
        ])
        result = scan_changed_files(cfg)
        exts = {Path(c["path"]).suffix.lower() for c in result}
        assert exts == {".md", ".txt"}

    def test_skips_hidden_and_temp_files(self, tmp_path, make_config):
        from core.ideate import scan_changed_files

        (tmp_path / ".hidden.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "~$lock.pdf").write_bytes(b"%PDF-1.4")
        (tmp_path / "real.pdf").write_bytes(b"%PDF-1.4")
        cfg = make_config([
            {"path": str(tmp_path), "source_type": "exam_pdf", "scan_window_days": 14}
        ])
        result = scan_changed_files(cfg)
        names = [Path(c["path"]).name for c in result]
        assert names == ["real.pdf"]

    def test_nonexistent_folder_skipped_not_raised(self, make_config):
        from core.ideate import scan_changed_files

        cfg = make_config([
            {"path": "/this/does/not/exist", "source_type": "exam_pdf", "scan_window_days": 14}
        ])
        # 不存在的路徑跳過, 不擋整批 (即使是空結果也 OK)
        result = scan_changed_files(cfg)
        assert result == []

    def test_result_sorted_newest_first(self, tmp_path, make_config):
        from core.ideate import scan_changed_files

        old_f = tmp_path / "old.pdf"
        new_f = tmp_path / "new.pdf"
        old_f.write_bytes(b"%PDF")
        new_f.write_bytes(b"%PDF")

        now = time.time()
        os.utime(old_f, (now - 5 * 86400, now - 5 * 86400))
        os.utime(new_f, (now - 1 * 86400, now - 1 * 86400))

        cfg = make_config([
            {"path": str(tmp_path), "source_type": "exam_pdf", "scan_window_days": 14}
        ])
        result = scan_changed_files(cfg)
        assert [Path(c["path"]).name for c in result] == ["new.pdf", "old.pdf"]


class TestLoadSaveProposals:
    """round-trip + atomic write (iter 11)."""

    def test_load_missing_file_returns_empty(self, tmp_path):
        from core.ideate import load_proposals

        result = load_proposals(tmp_path / "nope.json")
        assert result == []

    def test_load_corrupt_json_returns_empty_no_raise(self, tmp_path):
        from core.ideate import load_proposals

        p = tmp_path / "p.json"
        p.write_text("{ not valid json", encoding="utf-8")
        # 容錯讀: 壞檔不 raise, 回 []
        assert load_proposals(p) == []

    def test_load_wrong_root_type_returns_empty(self, tmp_path):
        from core.ideate import load_proposals

        p = tmp_path / "p.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")  # 是 list 不是 dict
        assert load_proposals(p) == []

    def test_save_and_load_roundtrip(self, tmp_path):
        from core.ideate import load_proposals, save_proposals

        proposals = [
            {
                "id": "prop_001",
                "generated_at": "2026-05-12T10:00:00+00:00",
                "source_file": "/x/exam.pdf",
                "source_type": "exam_pdf",
                "suggested_title": "材料力學 期中考第 3 題",
                "suggested_chapters": [],
                "reason": "新進考卷, 第 3 題涉及非線性, 學生易錯",
                "estimated_duration_min": 5,
                "status": "pending",
                "job_id": None,
            }
        ]
        p = tmp_path / "p.json"
        save_proposals(p, proposals)
        loaded = load_proposals(p)
        assert loaded == proposals

    def test_save_creates_parent_dir(self, tmp_path):
        from core.ideate import save_proposals

        nested = tmp_path / "a" / "b" / "p.json"
        save_proposals(nested, [])
        assert nested.exists()

    def test_save_does_not_leave_tmp_file(self, tmp_path):
        from core.ideate import save_proposals

        p = tmp_path / "p.json"
        save_proposals(p, [])
        # .tmp 應該被 os.replace 改名, 不殘留
        assert not (tmp_path / "p.json.tmp").exists()

    def test_save_includes_generated_at_metadata(self, tmp_path):
        import json

        from core.ideate import save_proposals

        p = tmp_path / "p.json"
        save_proposals(p, [])
        raw = json.loads(p.read_text(encoding="utf-8"))
        # generated_at 必填且 aware UTC ISO (帶 +00:00 / Z)
        assert "generated_at" in raw
        ts = raw["generated_at"]
        assert "T" in ts and ("+" in ts or "Z" in ts)
