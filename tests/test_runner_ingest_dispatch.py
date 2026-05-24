"""server.runner._run_ingest — source_type dispatch wrapper safety lock.

`_run_ingest` 是 ingest 階段的最外層 dispatch (source_type → 對應 backend
呼叫). 從 PR-2a 上線後一路加 source_type (exam_pdf / slides_pdf / repo /
document / url) 累積到現在 5 種, 但 dispatch 本身從沒打過直接測試 —
任何 refactor 不小心動:

  - non-URL path 存在驗證 (raise FileNotFoundError)
  - URL skip path check (網路來源, 不該要本機檔)
  - exam_pdf mock 走 solve.mock_output, 非 mock 走 core.solve_pdf via to_thread
  - exam_pdf 寫 deck.json ensure_ascii=False / indent=2 (跟其他寫盤點對齊)
  - slides_pdf 寫死 as_deck=True (React UI 走 SlideEditor, 不該回 v1 schema)
  - slides_pdf 寫死 single=False, brief=False (full ingest)
  - REPO → _run_ingest_repo / DOCUMENT/URL → _run_ingest_long_form 兩支
    inner helper 不該被混選 (走錯就 schema 不對 / scan_repo 對 file 炸)
  - 未支援 source_type raise ValueError (不該 fall-through to None)

就直接上線, 跟 iter 111-130 同思路 (route / helper safety lock).

策略 = monkeypatch 所有 dispatch 目標 (mock_output / solve_pdf /
ingest_slides / _run_ingest_repo / _run_ingest_long_form), 純驗
dispatch 行為; 不真打 Gemini / PDF / 磁碟掃描.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import server.jobs as jobs_mod
import server.runner as runner_mod
from server.jobs import JobStore
from server.runner import _run_ingest
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    SourceType,
)


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    """乾淨 JobStore — JOBS_DIR 指到 tmp_path/jobs (跟 iter 129 同 pattern)."""
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


def _make_rec(
    store: JobStore,
    *,
    source_type: SourceType,
    path: str | None = None,
    url: str | None = None,
    options: JobOptions | None = None,
):
    """建 job record, 回傳 rec (不走實際 schedule)."""
    return store.create(CreateJobRequest(
        source_type=source_type,
        source=JobSource(path=path, url=url),
        options=options or JobOptions(),
    ))


# ---------------------------------------------------------------- TestPathValidation


class TestPathValidation:
    """非 URL source_type 必須 check path 存在; URL 不該 check."""

    @pytest.mark.asyncio
    async def test_exam_pdf_missing_path_raises(self, store, tmp_path):
        """source.path 指向不存在的檔 → FileNotFoundError + 訊息含路徑."""
        rec = _make_rec(
            store, source_type=SourceType.EXAM_PDF,
            path=str(tmp_path / "does_not_exist.pdf"),
        )
        with pytest.raises(FileNotFoundError) as exc_info:
            await _run_ingest(store, rec)
        # 鎖訊息含原路徑 (debug 用), 不被 truncate / re-format
        assert "does_not_exist.pdf" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_none_path_raises_for_non_url(self, store):
        """source.path = None + source_type 非 URL → FileNotFoundError.

        鎖 `if src_path is None or not src_path.exists()` 防呆 — refactor
        改成只 check exists() (沒 None guard) 會 AttributeError 五倍難 debug.
        """
        rec = _make_rec(
            store, source_type=SourceType.DOCUMENT, path=None,
        )
        with pytest.raises(FileNotFoundError):
            await _run_ingest(store, rec)

    @pytest.mark.asyncio
    async def test_url_skips_path_check(self, store, monkeypatch):
        """source_type=URL → 即使 path=None 也不該 raise — URL 走網路.

        鎖 `if rec.source_type != SourceType.URL:` 條件不被改成
        無條件 check (URL job 會無辜被擋掉, 整個 url adapter 走不到).
        """
        # 直接 stub _run_ingest_long_form 避免真打 URL adapter
        async def fake_long_form(store, rec, deck_path, mock):
            return {"deck_title": "stub", "sections": []}
        monkeypatch.setattr(runner_mod, "_run_ingest_long_form", fake_long_form)

        rec = _make_rec(
            store, source_type=SourceType.URL,
            path=None, url="https://example.com/article",
        )
        deck = await _run_ingest(store, rec)
        assert deck["deck_title"] == "stub"

    @pytest.mark.asyncio
    async def test_repo_missing_path_raises(self, store, tmp_path):
        """REPO source_type 也走 path check (不是只有 PDF / DOCUMENT)."""
        rec = _make_rec(
            store, source_type=SourceType.REPO,
            path=str(tmp_path / "no_such_repo"),
        )
        with pytest.raises(FileNotFoundError):
            await _run_ingest(store, rec)


# ---------------------------------------------------------------- TestExamPdfDispatch


class TestExamPdfDispatch:
    """EXAM_PDF: mock=True → solve.mock_output, mock=False → core.solve_pdf."""

    @pytest.mark.asyncio
    async def test_mock_branch_uses_mock_output_not_solve_pdf(
        self, store, tmp_path, monkeypatch,
    ):
        """mock=True 該走 solve.mock_output, 完全不該叫到 solve_pdf.

        鎖 mock 分支不被改成 fall-through (否則 smoke test / 開發環境
        會偷打真 Gemini API 燒額度).
        """
        import core
        import solve

        # 建一個假 PDF (路徑存在驗證會過)
        pdf = tmp_path / "exam.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake\n")

        mock_calls = []
        real_calls = []

        def fake_mock_output():
            mock_calls.append(True)
            return {"exam_title": "mock exam", "problems": []}

        def fake_solve_pdf(path):
            real_calls.append(path)
            return {"exam_title": "should not be called", "problems": []}

        monkeypatch.setattr(solve, "mock_output", fake_mock_output)
        monkeypatch.setattr(core, "solve_pdf", fake_solve_pdf)

        rec = _make_rec(
            store, source_type=SourceType.EXAM_PDF,
            path=str(pdf),
            options=JobOptions(mock=True),
        )
        deck = await _run_ingest(store, rec)

        assert len(mock_calls) == 1
        assert len(real_calls) == 0  # solve_pdf 不該被叫
        assert deck["exam_title"] == "mock exam"

    @pytest.mark.asyncio
    async def test_non_mock_branch_calls_solve_pdf_with_src_path(
        self, store, tmp_path, monkeypatch,
    ):
        """mock=False → solve_pdf(src_path) 真走, 傳的是 Path 型 src_path."""
        import core

        pdf = tmp_path / "exam.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake\n")

        received = {}

        def fake_solve_pdf(path):
            received["path"] = path
            return {"exam_title": "real flow", "problems": [{"id": "q1"}]}

        monkeypatch.setattr(core, "solve_pdf", fake_solve_pdf)

        rec = _make_rec(
            store, source_type=SourceType.EXAM_PDF,
            path=str(pdf),
            options=JobOptions(mock=False),
        )
        deck = await _run_ingest(store, rec)

        # src_path 該是 Path 型, 指向真實檔
        assert received["path"] == pdf
        assert isinstance(received["path"], Path)
        assert deck["exam_title"] == "real flow"

    @pytest.mark.asyncio
    async def test_exam_pdf_writes_deck_json_with_chinese_no_escape(
        self, store, tmp_path, monkeypatch,
    ):
        """deck.json 寫盤該用 ensure_ascii=False — 鎖中文不被 \\uXXXX escape.

        Gemini 回中文 problem text, deck.json 要給人讀 / git diff 友善.
        日後 ensure_ascii=True 偷偷被改回會直接踩這條.
        """
        import core

        pdf = tmp_path / "exam.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake\n")

        chinese_deck = {
            "exam_title": "材料力學期中考",
            "problems": [{"id": "q1", "problem": "求應力分佈"}],
        }
        monkeypatch.setattr(core, "solve_pdf", lambda p: chinese_deck)

        rec = _make_rec(
            store, source_type=SourceType.EXAM_PDF, path=str(pdf),
        )
        await _run_ingest(store, rec)

        raw = store.deck_path(rec.id).read_text(encoding="utf-8")
        assert "材料力學期中考" in raw  # 原字保留
        assert "\\u" not in raw  # 沒 escape sequence

    @pytest.mark.asyncio
    async def test_exam_pdf_writes_deck_json_indent2(
        self, store, tmp_path, monkeypatch,
    ):
        """indent=2 鎖 — pretty JSON 給人讀, refactor 改 indent=None / 1 / 4 該 fail."""
        import core

        pdf = tmp_path / "exam.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake\n")

        deck = {"exam_title": "t", "problems": [{"id": "q1"}]}
        monkeypatch.setattr(core, "solve_pdf", lambda p: deck)

        rec = _make_rec(
            store, source_type=SourceType.EXAM_PDF, path=str(pdf),
        )
        await _run_ingest(store, rec)

        raw = store.deck_path(rec.id).read_text(encoding="utf-8")
        # 多行 + 至少一行 2-space 開頭 (indent=2 特徵)
        assert "\n" in raw
        assert any(line.startswith("  ") for line in raw.splitlines())


# ---------------------------------------------------------------- TestSlidesPdfDispatch


class TestSlidesPdfDispatch:
    """SLIDES_PDF: core.ingest_slides 透傳, 寫死 single=False / brief=False / as_deck=True."""

    @pytest.mark.asyncio
    async def test_slides_pdf_calls_ingest_slides_with_as_deck_true(
        self, store, tmp_path, monkeypatch,
    ):
        """as_deck=True 寫死 — PR-3h 設計, React UI 看到 sections 走 SlideEditor.

        鎖 refactor 改成 False (或拿掉 kwarg 走預設值) 會讓 UI 看到 v1 problems
        schema, SlideEditor 退回 problem editor 是很 confused 的 regression.
        """
        import core

        pdf = tmp_path / "slides.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake\n")

        kwargs_received = {}

        def fake_ingest_slides(src, deck_path, **kwargs):
            kwargs_received.update(kwargs)
            # 真寫一份 deck.json 模擬 ingest_slides 行為 (函式不回 dict, _run_ingest 再讀回)
            deck_path.write_text(
                json.dumps({"deck_title": "slides ingested", "sections": []}),
                encoding="utf-8",
            )

        monkeypatch.setattr(core, "ingest_slides", fake_ingest_slides)

        rec = _make_rec(
            store, source_type=SourceType.SLIDES_PDF, path=str(pdf),
            options=JobOptions(mock=False),
        )
        deck = await _run_ingest(store, rec)

        assert kwargs_received["as_deck"] is True
        assert kwargs_received["single"] is False  # full ingest, 不只第一頁
        assert kwargs_received["brief"] is False
        assert kwargs_received["mock"] is False
        # deck 該是 read 回來的 (不是 ingest_slides 回傳值, 它沒回)
        assert deck["deck_title"] == "slides ingested"

    @pytest.mark.asyncio
    async def test_slides_pdf_mock_passes_through(
        self, store, tmp_path, monkeypatch,
    ):
        """rec.options.mock=True 該透傳給 ingest_slides — 鎖不被寫死成 False."""
        import core

        pdf = tmp_path / "slides.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake\n")

        received = {}

        def fake_ingest_slides(src, deck_path, **kwargs):
            received.update(kwargs)
            deck_path.write_text(json.dumps({"sections": []}), encoding="utf-8")

        monkeypatch.setattr(core, "ingest_slides", fake_ingest_slides)

        rec = _make_rec(
            store, source_type=SourceType.SLIDES_PDF, path=str(pdf),
            options=JobOptions(mock=True),
        )
        await _run_ingest(store, rec)

        assert received["mock"] is True


# ---------------------------------------------------------------- TestRepoDispatch


class TestRepoDispatch:
    """REPO source_type 該 dispatch 到 _run_ingest_repo, 不是 long_form."""

    @pytest.mark.asyncio
    async def test_repo_calls_run_ingest_repo_only(
        self, store, tmp_path, monkeypatch,
    ):
        """rec.source_type=REPO → _run_ingest_repo 被叫, _run_ingest_long_form
        完全不該被叫 (兩 inner helper 不該被混選).

        鎖 dispatch order — 兩 if 順序顛倒會走錯 helper, schema 跟著錯.
        """
        repo_dir = tmp_path / "my_repo"
        repo_dir.mkdir()

        repo_calls = []
        long_form_calls = []

        async def fake_repo(s, rec, deck_path, mock):
            repo_calls.append({"deck_path": deck_path, "mock": mock})
            return {"deck_title": "repo deck", "sections": []}

        async def fake_long_form(s, rec, deck_path, mock):
            long_form_calls.append(True)
            return {"deck_title": "should not be called", "sections": []}

        monkeypatch.setattr(runner_mod, "_run_ingest_repo", fake_repo)
        monkeypatch.setattr(runner_mod, "_run_ingest_long_form", fake_long_form)

        rec = _make_rec(
            store, source_type=SourceType.REPO, path=str(repo_dir),
        )
        deck = await _run_ingest(store, rec)

        assert len(repo_calls) == 1
        assert len(long_form_calls) == 0
        assert deck["deck_title"] == "repo deck"
        # deck_path 該透傳 store.deck_path(rec.id) (不是 None / 空)
        assert repo_calls[0]["deck_path"] == store.deck_path(rec.id)


# ---------------------------------------------------------------- TestLongFormDispatch


class TestLongFormDispatch:
    """DOCUMENT / URL 都該走 _run_ingest_long_form (不被分開走兩支)."""

    @pytest.mark.asyncio
    async def test_document_calls_long_form_not_repo(
        self, store, tmp_path, monkeypatch,
    ):
        """DOCUMENT → _run_ingest_long_form (不走 _run_ingest_repo)."""
        doc = tmp_path / "article.md"
        doc.write_text("# Hello\n", encoding="utf-8")

        long_form_calls = []
        repo_calls = []

        async def fake_long_form(s, rec, deck_path, mock):
            long_form_calls.append(rec.source_type)
            return {"deck_title": "doc deck", "sections": []}

        async def fake_repo(s, rec, deck_path, mock):
            repo_calls.append(True)
            return {"deck_title": "should not be called", "sections": []}

        monkeypatch.setattr(runner_mod, "_run_ingest_long_form", fake_long_form)
        monkeypatch.setattr(runner_mod, "_run_ingest_repo", fake_repo)

        rec = _make_rec(
            store, source_type=SourceType.DOCUMENT, path=str(doc),
        )
        deck = await _run_ingest(store, rec)

        assert long_form_calls == [SourceType.DOCUMENT]
        assert len(repo_calls) == 0
        assert deck["deck_title"] == "doc deck"

    @pytest.mark.asyncio
    async def test_url_calls_long_form_with_url_source_type(
        self, store, monkeypatch,
    ):
        """URL → _run_ingest_long_form, rec.source_type 該保留 URL (不被 normalize)."""
        long_form_calls = []

        async def fake_long_form(s, rec, deck_path, mock):
            long_form_calls.append(rec.source_type)
            return {"deck_title": "url deck", "sections": []}

        monkeypatch.setattr(runner_mod, "_run_ingest_long_form", fake_long_form)

        rec = _make_rec(
            store, source_type=SourceType.URL,
            path=None, url="https://example.com/post",
        )
        deck = await _run_ingest(store, rec)

        assert long_form_calls == [SourceType.URL]
        assert deck["deck_title"] == "url deck"

    @pytest.mark.asyncio
    async def test_long_form_receives_mock_flag(
        self, store, tmp_path, monkeypatch,
    ):
        """rec.options.mock 該透傳給 _run_ingest_long_form (對齊 slides/exam 行為)."""
        doc = tmp_path / "article.md"
        doc.write_text("# Hello\n", encoding="utf-8")

        received_mock = []

        async def fake_long_form(s, rec, deck_path, mock):
            received_mock.append(mock)
            return {"sections": []}

        monkeypatch.setattr(runner_mod, "_run_ingest_long_form", fake_long_form)

        rec = _make_rec(
            store, source_type=SourceType.DOCUMENT, path=str(doc),
            options=JobOptions(mock=True),
        )
        await _run_ingest(store, rec)

        assert received_mock == [True]


# ---------------------------------------------------------------- TestSchemaDispatchExhaustive


class TestSchemaDispatchExhaustive:
    """確保 dispatch 鎖死 5 種 source_type, 沒有 fall-through 漏網."""

    @pytest.mark.asyncio
    async def test_all_known_source_types_handled(
        self, store, tmp_path, monkeypatch,
    ):
        """5 種 source_type 都該各自 dispatch, 不該有任一掉到 ValueError."""
        import core
        import solve

        pdf = tmp_path / "f.pdf"
        pdf.write_bytes(b"%PDF\n")
        doc = tmp_path / "f.md"
        doc.write_text("x", encoding="utf-8")
        repo = tmp_path / "r"
        repo.mkdir()

        # Stub 全部 backend, 不打真 Gemini / PDF
        monkeypatch.setattr(solve, "mock_output", lambda: {"problems": []})

        def fake_ingest_slides(src, dp, **kw):
            dp.write_text(json.dumps({"sections": []}), encoding="utf-8")

        monkeypatch.setattr(core, "ingest_slides", fake_ingest_slides)

        async def fake_repo(s, r, dp, m):
            return {"_dispatched": "repo"}

        async def fake_long(s, r, dp, m):
            return {"_dispatched": r.source_type.value}

        monkeypatch.setattr(runner_mod, "_run_ingest_repo", fake_repo)
        monkeypatch.setattr(runner_mod, "_run_ingest_long_form", fake_long)

        cases = [
            (SourceType.EXAM_PDF, str(pdf), None),
            (SourceType.SLIDES_PDF, str(pdf), None),
            (SourceType.REPO, str(repo), None),
            (SourceType.DOCUMENT, str(doc), None),
            (SourceType.URL, None, "https://x.example/y"),
        ]
        for st, p, u in cases:
            rec = _make_rec(
                store, source_type=st, path=p, url=u,
                options=JobOptions(mock=True),
            )
            # 不該 raise ValueError ("未支援的 source_type")
            await _run_ingest(store, rec)
