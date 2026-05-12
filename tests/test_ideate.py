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


class TestDedupeAgainstJobs:
    """dedupe_against_jobs — JobStore + 前次 proposals 三層去重。"""

    @pytest.fixture
    def make_proposal(self):
        def _build(source_file: str, status: str = "pending", title: str = "T") -> dict:
            return {
                "id": f"prop_{source_file}",
                "generated_at": "2026-05-13T00:00:00+00:00",
                "source_file": source_file,
                "source_type": "exam_pdf",
                "suggested_title": title,
                "suggested_chapters": [],
                "reason": "r",
                "estimated_duration_min": 5,
                "status": status,
                "job_id": None,
            }
        return _build

    @pytest.fixture
    def fake_store(self):
        """超簡 JobStore — 只實作 list() 回測試指定的 JobRecord-shaped objects."""
        class FakeUpload:
            def __init__(self, video_id=None):
                self.video_id = video_id

        class FakeState:
            def __init__(self, value):
                self.value = value

        class FakeSource:
            def __init__(self, path):
                self.path = path

        class FakeRecord:
            def __init__(self, path, state="done", youtube_uploads=None):
                self.source = FakeSource(path)
                self.state = FakeState(state)
                self.youtube_uploads = youtube_uploads or {}

        class FakeStore:
            def __init__(self, records):
                self._records = records

            def list(self):
                return self._records

        return FakeRecord, FakeUpload, FakeStore

    def test_empty_input_returns_empty(self, fake_store):
        from core.ideate import dedupe_against_jobs

        _, _, FakeStore = fake_store
        store = FakeStore([])
        assert dedupe_against_jobs([], store) == []

    def test_no_dups_passes_through(self, fake_store, make_proposal):
        from core.ideate import dedupe_against_jobs

        _, _, FakeStore = fake_store
        store = FakeStore([])
        proposals = [make_proposal("/x/a.pdf"), make_proposal("/x/b.pdf")]
        result = dedupe_against_jobs(proposals, store)
        assert len(result) == 2

    def test_done_state_filters_out(self, fake_store, make_proposal):
        from core.ideate import dedupe_against_jobs

        FakeRecord, _, FakeStore = fake_store
        store = FakeStore([FakeRecord("/x/a.pdf", state="done")])
        proposals = [make_proposal("/x/a.pdf"), make_proposal("/x/b.pdf")]
        result = dedupe_against_jobs(proposals, store)
        assert len(result) == 1
        assert result[0]["source_file"] == "/x/b.pdf"

    def test_non_done_state_does_not_filter(self, fake_store, make_proposal):
        """state=ingesting / rendering / failed 不算「已做過」, 應保留 proposal."""
        from core.ideate import dedupe_against_jobs

        FakeRecord, _, FakeStore = fake_store
        store = FakeStore([
            FakeRecord("/x/a.pdf", state="rendering"),
            FakeRecord("/x/b.pdf", state="failed"),
        ])
        proposals = [make_proposal("/x/a.pdf"), make_proposal("/x/b.pdf")]
        # 雖然 a/b 都有對應 job, 但 state 不是 done → 仍保留
        result = dedupe_against_jobs(proposals, store)
        assert len(result) == 2

    def test_youtube_uploaded_filters_out(self, fake_store, make_proposal):
        from core.ideate import dedupe_against_jobs

        FakeRecord, FakeUpload, FakeStore = fake_store
        store = FakeStore([
            FakeRecord(
                "/x/a.pdf",
                state="rendering",  # 即使非 done, video_id 存在仍算已上傳
                youtube_uploads={"q1.mp4": FakeUpload(video_id="abc123")},
            )
        ])
        proposals = [make_proposal("/x/a.pdf"), make_proposal("/x/b.pdf")]
        result = dedupe_against_jobs(proposals, store)
        assert len(result) == 1
        assert result[0]["source_file"] == "/x/b.pdf"

    def test_youtube_upload_without_video_id_no_filter(self, fake_store, make_proposal):
        from core.ideate import dedupe_against_jobs

        FakeRecord, FakeUpload, FakeStore = fake_store
        store = FakeStore([
            FakeRecord(
                "/x/a.pdf",
                state="rendering",
                youtube_uploads={"q1.mp4": FakeUpload(video_id=None)},  # 上傳中, 還沒拿到 id
            )
        ])
        proposals = [make_proposal("/x/a.pdf")]
        result = dedupe_against_jobs(proposals, store)
        assert len(result) == 1

    def test_previous_approved_filters_out(self, fake_store, make_proposal):
        from core.ideate import dedupe_against_jobs

        _, _, FakeStore = fake_store
        store = FakeStore([])
        proposals = [make_proposal("/x/a.pdf"), make_proposal("/x/b.pdf")]
        previous = [make_proposal("/x/a.pdf", status="approved")]
        result = dedupe_against_jobs(proposals, store, previous_proposals=previous)
        assert len(result) == 1
        assert result[0]["source_file"] == "/x/b.pdf"

    def test_previous_ignored_filters_out(self, fake_store, make_proposal):
        from core.ideate import dedupe_against_jobs

        _, _, FakeStore = fake_store
        store = FakeStore([])
        proposals = [make_proposal("/x/a.pdf")]
        previous = [make_proposal("/x/a.pdf", status="ignored")]
        assert dedupe_against_jobs(proposals, store, previous_proposals=previous) == []

    def test_previous_pending_does_not_filter(self, fake_store, make_proposal):
        """前次還是 pending 表示用戶還沒決策, 允許再次提案 (refresh proposals)."""
        from core.ideate import dedupe_against_jobs

        _, _, FakeStore = fake_store
        store = FakeStore([])
        proposals = [make_proposal("/x/a.pdf")]
        previous = [make_proposal("/x/a.pdf", status="pending")]
        result = dedupe_against_jobs(proposals, store, previous_proposals=previous)
        assert len(result) == 1

    def test_path_case_insensitive_match(self, fake_store, make_proposal):
        """Windows path 大小寫不敏感, D:\\Foo == d:\\foo 應該命中。"""
        from core.ideate import dedupe_against_jobs

        FakeRecord, _, FakeStore = fake_store
        store = FakeStore([FakeRecord("/Path/To/A.PDF", state="done")])
        proposals = [make_proposal("/path/to/a.pdf")]
        result = dedupe_against_jobs(proposals, store)
        assert len(result) == 0  # 大小寫不敏感命中 → 過濾掉


class TestProposeFromFile:
    """propose_from_file (Gemini Vision) — mock 所有外部呼叫。"""

    @pytest.fixture
    def base_config(self):
        from core.ideate import IdeateConfig

        cfg: IdeateConfig = {
            "watched_folders": [],
            "llm_model": "gemini-2.5-flash",
            "max_proposals_per_file": 3,
            "enabled": True,
        }
        return cfg

    @pytest.fixture
    def fake_pdf(self, tmp_path):
        p = tmp_path / "exam.pdf"
        p.write_bytes(b"%PDF-1.4\nfake content")
        return {
            "path": str(p),
            "source_type": "exam_pdf",
            "mtime": 0.0,
            "size_bytes": len(b"%PDF-1.4\nfake content"),
        }

    @pytest.fixture
    def mock_io(self, monkeypatch):
        """Mock thumbs render + Gemini call. 回 helper 讓 test 客製化 raw_json."""
        from core import ideate

        monkeypatch.setattr(
            ideate, "_render_pdf_thumbs",
            lambda path, max_pages=5: [b"\x89PNG fake"],
        )

        state = {"raw_json": ""}

        def set_response(s: str):
            state["raw_json"] = s

        def fake_gemini(**kwargs):
            return state["raw_json"]

        monkeypatch.setattr(ideate, "_call_gemini_vision", fake_gemini)
        return set_response

    def test_missing_file_returns_empty(self, base_config):
        from core.ideate import FileCandidate, propose_from_file

        candidate: FileCandidate = {
            "path": "/this/does/not/exist.pdf",
            "source_type": "exam_pdf",
            "mtime": 0.0,
            "size_bytes": 0,
        }
        assert propose_from_file(candidate, base_config) == []

    def test_non_pdf_returns_empty(self, tmp_path, base_config):
        from core.ideate import FileCandidate, propose_from_file

        md = tmp_path / "note.md"
        md.write_text("# hi", encoding="utf-8")
        candidate: FileCandidate = {
            "path": str(md),
            "source_type": "document",
            "mtime": 0.0,
            "size_bytes": md.stat().st_size,
        }
        # propose_from_file 目前只走 PDF (md/txt 沒 Vision path), 回 []
        assert propose_from_file(candidate, base_config) == []

    def test_thumbs_render_fail_returns_empty(self, fake_pdf, base_config, monkeypatch):
        from core import ideate
        from core.ideate import propose_from_file

        def boom(*a, **kw):
            raise RuntimeError("pymupdf failed")
        monkeypatch.setattr(ideate, "_render_pdf_thumbs", boom)

        assert propose_from_file(fake_pdf, base_config) == []

    def test_gemini_raise_returns_empty(self, fake_pdf, base_config, monkeypatch):
        from core import ideate
        from core.ideate import propose_from_file

        monkeypatch.setattr(
            ideate, "_render_pdf_thumbs",
            lambda *a, **kw: [b"\x89PNG"],
        )

        def boom(**kw):
            raise RuntimeError("API limit")
        monkeypatch.setattr(ideate, "_call_gemini_vision", boom)

        assert propose_from_file(fake_pdf, base_config) == []

    def test_happy_path_valid_json(self, fake_pdf, base_config, mock_io):
        from core.ideate import propose_from_file

        mock_io('''
{
  "proposals": [
    {
      "suggested_title": "材料力學 第 3 題解析",
      "suggested_chapters": [],
      "reason": "計算多步, 學生易在彎矩計算錯",
      "estimated_duration_min": 5
    }
  ]
}
        '''.strip())

        result = propose_from_file(fake_pdf, base_config)
        assert len(result) == 1
        p = result[0]
        assert p["suggested_title"] == "材料力學 第 3 題解析"
        assert p["status"] == "pending"
        assert p["source_file"] == fake_pdf["path"]
        assert p["source_type"] == "exam_pdf"
        assert p["estimated_duration_min"] == 5
        assert p["job_id"] is None
        # id 格式 prop_<timestamp>_NN
        assert p["id"].startswith("prop_")

    def test_invalid_json_returns_empty(self, fake_pdf, base_config, mock_io):
        from core.ideate import propose_from_file

        mock_io("{ not valid json at all")
        assert propose_from_file(fake_pdf, base_config) == []

    def test_empty_response_returns_empty(self, fake_pdf, base_config, mock_io):
        from core.ideate import propose_from_file

        mock_io("")
        assert propose_from_file(fake_pdf, base_config) == []

    def test_proposals_not_list_returns_empty(self, fake_pdf, base_config, mock_io):
        from core.ideate import propose_from_file

        mock_io('{"proposals": "not a list"}')
        assert propose_from_file(fake_pdf, base_config) == []

    def test_truncated_to_max_proposals(self, fake_pdf, base_config, mock_io):
        from core.ideate import propose_from_file

        # max_proposals_per_file=3, 但 Gemini 給 5 個
        mock_io('''
{
  "proposals": [
    {"suggested_title": "T1", "reason": "r1", "estimated_duration_min": 5},
    {"suggested_title": "T2", "reason": "r2", "estimated_duration_min": 5},
    {"suggested_title": "T3", "reason": "r3", "estimated_duration_min": 5},
    {"suggested_title": "T4", "reason": "r4", "estimated_duration_min": 5},
    {"suggested_title": "T5", "reason": "r5", "estimated_duration_min": 5}
  ]
}
        '''.strip())

        result = propose_from_file(fake_pdf, base_config)
        assert len(result) == 3
        titles = [p["suggested_title"] for p in result]
        assert titles == ["T1", "T2", "T3"]

    def test_empty_title_filtered(self, fake_pdf, base_config, mock_io):
        from core.ideate import propose_from_file

        mock_io('''
{
  "proposals": [
    {"suggested_title": "", "reason": "no title", "estimated_duration_min": 5},
    {"suggested_title": "Real Title", "reason": "ok", "estimated_duration_min": 5}
  ]
}
        '''.strip())

        result = propose_from_file(fake_pdf, base_config)
        assert len(result) == 1
        assert result[0]["suggested_title"] == "Real Title"

    def test_markdown_fence_stripped(self, fake_pdf, base_config, mock_io):
        from core.ideate import propose_from_file

        mock_io('''```json
{"proposals": [{"suggested_title": "T1", "reason": "r", "estimated_duration_min": 5}]}
```''')
        result = propose_from_file(fake_pdf, base_config)
        assert len(result) == 1
        assert result[0]["suggested_title"] == "T1"

    def test_chapters_only_strings_up_to_six(self, fake_pdf, base_config, mock_io):
        from core.ideate import propose_from_file

        mock_io('''
{
  "proposals": [
    {
      "suggested_title": "Slides",
      "suggested_chapters": ["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
      "reason": "r",
      "estimated_duration_min": 15
    }
  ]
}
        '''.strip())
        result = propose_from_file(fake_pdf, base_config)
        assert len(result[0]["suggested_chapters"]) == 6  # 截斷


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
