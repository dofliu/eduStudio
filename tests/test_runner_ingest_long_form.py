"""server.runner._run_ingest_long_form — DOCUMENT / URL ingest pipeline safety lock.

`_run_ingest_long_form` 是 SourceType.DOCUMENT / SourceType.URL 共用的 ingest
主流程: adapter (scan_document / scan_url) → PDF figures or Mermaid 抽取 →
outliner (outline_long_form) → AI 圖 → scriptor (script_long_form) → cover /
outro hook → 寫 raw_content.json / outline.json / deck.json.

跟 _run_ingest_repo 結構一致, 差別:
  - 兩種 source 分流: DOCUMENT 走 scan_document + 格式分流 (pdf 抽 figures,
    md/txt 抽 mermaid, 其他 fmt 直接 figures=[]); URL 走 scan_url + setdefault
  - DOCUMENT 缺檔 / URL 缺 url 防呆
  - outliner / scriptor 換成 outline_long_form / script_long_form (long-form
    prompt template)

從上線後一路加 feature (iter 51 PDF figure 抽 / iter 57 .md mermaid /
iter 56 AI 圖 / iter 62 cover / iter 63 outro / iter 92 L2/L3 narration_style
+ persona) 但 wrapper 本身沒對應直接測試 — 任何 refactor 不小心動:

  - DOCUMENT: src_path = Path(rec.source.path) (function-local Path() 不被
    str 化)
  - format 分流: pdf → extract_pdf_figures / md|txt →
    extract_and_render_mermaid_from_text / 其他 → figures=[] 三條分支
  - PDF figure 抽例外吞 + raw["figures"] = [] 確保 key 存在
  - .md mermaid 例外吞 + raw["figures"] = []
  - URL: rec.source.url None/空 raise ValueError 含 source_type=url 訊息
  - URL: raw.setdefault("figures", []) 保證 key 存在 (scriptor 依賴)
  - raw_content.json / outline.json / deck.json 寫盤 ensure_ascii=False +
    indent=2
  - mock=True 走 mock_outline + mock_deck_from_outline, 不該打 Gemini
  - mock=False 走 outline_long_form + script_long_form, length_mode /
    narration_style / persona 全透傳 (narration_style + persona 只到 script,
    iter 92 設計)
  - ai_generate_diagrams / ai_generate_mermaid 兩 flag 開才呼叫對應 helper
  - prepend_cover / append_outro 兩 flag 開才呼叫對應 helper +
    cover_speaker / cover_org / cover_date / outro_thanks / outro_url /
    show_qr_on_outro / outro_youtube_url 全透傳

就直接上線 — 跟 iter 111-134 同思路 (route / helper / orchestrator safety
lock). 0 production code 改動, 純測試.

策略 = monkeypatch core.adapters.document.scan_document /
core.adapters.document.extract_pdf_figures / core.adapters.url.scan_url /
core.mermaid_render.extract_and_render_mermaid_from_text /
core.outliner.* / core.scriptor.* (function-local from-import, module
attribute patch 直接生效); runner_mod._generate_ai_diagrams_for_outline /
_generate_mermaid_for_outline / _prepend_cover_to_deck /
_append_outro_to_deck (module 本身就 lookup, 同 module patch 直接生效).
不真打 Gemini / 真讀 PDF / mermaid.ink HTTP.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import server.jobs as jobs_mod
import server.runner as runner_mod
from server.jobs import JobStore
from server.runner import _run_ingest_long_form
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    SourceType,
)


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    """乾淨 JobStore — JOBS_DIR 指 tmp_path/jobs (跟 iter 129 / 131 / 134 同 pattern)."""
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


def _make_doc_rec(
    store: JobStore,
    *,
    path: str = "/fake/doc.md",
    options: JobOptions | None = None,
):
    """建 DOCUMENT source_type 的 job record (path 不用真實存在 — adapter 全 stub)."""
    return store.create(CreateJobRequest(
        source_type=SourceType.DOCUMENT,
        source=JobSource(path=path),
        options=options or JobOptions(),
    ))


def _make_url_rec(
    store: JobStore,
    *,
    url: str | None = "https://example.com/post",
    options: JobOptions | None = None,
):
    """建 URL source_type 的 job record."""
    return store.create(CreateJobRequest(
        source_type=SourceType.URL,
        source=JobSource(url=url),
        options=options or JobOptions(),
    ))


@pytest.fixture
def stub_all(monkeypatch: pytest.MonkeyPatch):
    """把所有 dispatch 目標 stub 掉, 回傳 calls dict 給 assert.

    function-local imports (從 module 直接 patch 生效):
      core.adapters.document.scan_document / extract_pdf_figures
      core.adapters.url.scan_url
      core.mermaid_render.extract_and_render_mermaid_from_text
      core.outliner.mock_outline / outline_long_form
      core.scriptor.mock_deck_from_outline / script_long_form

    module-level (server.runner):
      _generate_ai_diagrams_for_outline / _generate_mermaid_for_outline
      _prepend_cover_to_deck / _append_outro_to_deck
    """
    import core.adapters.document as doc_adapter
    import core.adapters.url as url_adapter
    import core.mermaid_render as mermaid_mod
    import core.outliner as outliner_mod
    import core.scriptor as scriptor_mod

    calls: dict = {
        "scan_document": [],
        "extract_pdf_figures": [],
        "scan_url": [],
        "mermaid_text": [],
        "mock_outline": [],
        "outline_long_form": [],
        "mock_deck": [],
        "script_long_form": [],
        "ai_diagrams": [],
        "ai_mermaid": [],
        "cover": [],
        "outro": [],
    }

    # scan_document 預設回 .md 格式 (跟 _make_doc_rec 預設 path=/fake/doc.md 對齊)
    def fake_scan_document(doc_path, **kw):
        calls["scan_document"].append({"doc_path": doc_path})
        return {
            "source_kind": "document",
            "title": "fake_doc",
            "format": "md",
            "content": "# heading\nbody text",
            "primary_language": "zh-tw",
            "stats": {"chars": 20},
        }

    def fake_extract_pdf_figures(doc_path, figures_dir, **kw):
        calls["extract_pdf_figures"].append({
            "doc_path": doc_path, "figures_dir": figures_dir,
        })
        return [{"id": "pdf_fig1", "path": "pdf_fig1.png"}]

    def fake_scan_url(url, **kw):
        calls["scan_url"].append({"url": url})
        return {
            "source_kind": "url",
            "title": "fake_url",
            "url": url,
            "content": "scraped text",
        }

    def fake_mermaid_text(content, figures_dir, *, source_label=None, **kw):
        calls["mermaid_text"].append({
            "content": content, "figures_dir": figures_dir,
            "source_label": source_label,
        })
        return []  # 預設沒抽到 mermaid

    def fake_mock_outline(raw):
        calls["mock_outline"].append({"raw": raw})
        return {"sections": [{"id": "intro", "title": "Mock Outline"}]}

    def fake_outline_long_form(raw, *, length_mode=None, **kw):
        calls["outline_long_form"].append({"raw": raw, "length_mode": length_mode})
        return {"sections": [{"id": "intro", "title": "Real Outline"}]}

    def fake_mock_deck(outline, raw):
        calls["mock_deck"].append({"outline": outline, "raw": raw})
        return {
            "deck_title": "Mock Deck",
            "sections": [{"id": "s1", "title": "標題", "slides": []}],
        }

    def fake_script_long_form(
        outline, raw, *, length_mode=None, narration_style=None, persona=None,
    ):
        calls["script_long_form"].append({
            "outline": outline,
            "raw": raw,
            "length_mode": length_mode,
            "narration_style": narration_style,
            "persona": persona,
        })
        return {
            "deck_title": "Long Form Deck — 中文標題",
            "sections": [{"id": "s1", "title": "Section A", "slides": []}],
        }

    async def fake_ai_diagrams(outline, raw, job_dir):
        calls["ai_diagrams"].append({
            "outline": outline, "raw": raw, "job_dir": job_dir,
        })

    async def fake_ai_mermaid(outline, raw, job_dir):
        calls["ai_mermaid"].append({
            "outline": outline, "raw": raw, "job_dir": job_dir,
        })

    def fake_cover(deck, **kw):
        calls["cover"].append({"deck_id": id(deck), "kwargs": kw})

    def fake_outro(deck, **kw):
        calls["outro"].append({"deck_id": id(deck), "kwargs": kw})

    monkeypatch.setattr(doc_adapter, "scan_document", fake_scan_document)
    monkeypatch.setattr(doc_adapter, "extract_pdf_figures", fake_extract_pdf_figures)
    monkeypatch.setattr(url_adapter, "scan_url", fake_scan_url)
    monkeypatch.setattr(
        mermaid_mod, "extract_and_render_mermaid_from_text", fake_mermaid_text,
    )
    monkeypatch.setattr(outliner_mod, "mock_outline", fake_mock_outline)
    monkeypatch.setattr(outliner_mod, "outline_long_form", fake_outline_long_form)
    monkeypatch.setattr(scriptor_mod, "mock_deck_from_outline", fake_mock_deck)
    monkeypatch.setattr(scriptor_mod, "script_long_form", fake_script_long_form)
    monkeypatch.setattr(runner_mod, "_generate_ai_diagrams_for_outline", fake_ai_diagrams)
    monkeypatch.setattr(runner_mod, "_generate_mermaid_for_outline", fake_ai_mermaid)
    monkeypatch.setattr(runner_mod, "_prepend_cover_to_deck", fake_cover)
    monkeypatch.setattr(runner_mod, "_append_outro_to_deck", fake_outro)

    return calls


# ---------------------------------------------------------------- TestUrlValidation


class TestUrlValidation:
    """URL source: rec.source.url 缺/空時 raise ValueError, 訊息含 source_type=url."""

    @pytest.mark.asyncio
    async def test_missing_url_raises_value_error(self, store, stub_all):
        """source_type=url + url=None → ValueError + 訊息含 'source_type=url'.

        鎖 URL 防呆訊息格式 (debug 用), 不被 truncate. scan_url / scan_document
        都不該被叫 (早 return).
        """
        rec = _make_url_rec(store, url=None)
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        with pytest.raises(ValueError) as exc_info:
            await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert "source_type=url" in str(exc_info.value)
        assert len(stub_all["scan_url"]) == 0
        assert len(stub_all["scan_document"]) == 0

    @pytest.mark.asyncio
    async def test_url_present_calls_scan_url_not_scan_document(
        self, store, stub_all,
    ):
        """source_type=url + url 有值 → scan_url 該被叫, scan_document 完全不叫.

        鎖 DOCUMENT / URL 分支不該混選 — 否則 URL job 會跑進 PDF figure
        抽取路徑炸不存在路徑.
        """
        rec = _make_url_rec(store, url="https://example.com/blog/post")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert len(stub_all["scan_url"]) == 1
        assert stub_all["scan_url"][0]["url"] == "https://example.com/blog/post"
        assert len(stub_all["scan_document"]) == 0


# ---------------------------------------------------------------- TestDocumentInvocation


class TestDocumentInvocation:
    """scan_document 收 Path 型 src_path (function-local Path() 轉型)."""

    @pytest.mark.asyncio
    async def test_scan_document_receives_path_not_str(self, store, stub_all):
        """src_path 該是 Path 型, 不是 str (adapter 內依賴 Path API).

        鎖 `Path(rec.source.path)` 不被偷拿掉 — adapter 收 str 會 AttributeError
        (.is_file() / .suffix 都是 Path API).
        """
        rec = _make_doc_rec(store, path="/abs/path/to/doc.md")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert isinstance(stub_all["scan_document"][0]["doc_path"], Path)
        assert str(stub_all["scan_document"][0]["doc_path"]) in (
            "/abs/path/to/doc.md", "\\abs\\path\\to\\doc.md",
        ) or stub_all["scan_document"][0]["doc_path"].name == "doc.md"


# ---------------------------------------------------------------- TestPdfFormatBranch


class TestPdfFormatBranch:
    """raw.format == 'pdf' → extract_pdf_figures 抽圖 (失敗吞例外 + figures=[])."""

    @pytest.mark.asyncio
    async def test_pdf_format_extracts_figures_to_raw(
        self, store, monkeypatch, stub_all, caplog,
    ):
        """raw["format"]='pdf' → extract_pdf_figures(src_path, figures_dir) 被叫.

        鎖 figures_dir 該等於 job_dir/"figures" (跟 mermaid 共用目錄, scriptor
        依此找圖). 結果寫進 raw["figures"]. 記 logger.info "PDF figure 抽取".
        """
        import core.adapters.document as doc_adapter

        def pdf_scan(doc_path, **kw):
            stub_all["scan_document"].append({"doc_path": doc_path})
            return {
                "source_kind": "document",
                "title": "research_paper",
                "format": "pdf",
                "content": "abstract...",
                "stats": {"chars": 10},
            }
        monkeypatch.setattr(doc_adapter, "scan_document", pdf_scan)

        rec = _make_doc_rec(store, path="/fake/paper.pdf")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        with caplog.at_level("INFO"):
            await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert len(stub_all["extract_pdf_figures"]) == 1
        assert stub_all["extract_pdf_figures"][0]["figures_dir"] == \
            deck_path.parent / "figures"

        # raw_content.json 該含 figures 跟 extract_pdf_figures 回的內容對齊
        raw_disk = json.loads(
            (deck_path.parent / "raw_content.json").read_text(encoding="utf-8"),
        )
        assert raw_disk["figures"] == [
            {"id": "pdf_fig1", "path": "pdf_fig1.png"},
        ]
        # logger.info 含「PDF figure 抽取」
        assert any("PDF figure 抽取" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_pdf_figure_exception_swallowed_sets_empty_list(
        self, store, monkeypatch, stub_all, caplog,
    ):
        """extract_pdf_figures raise → 不擋 ingest + raw["figures"]=[] + log.exception.

        鎖 try/except 內 `raw["figures"] = []` fallback 不被偷拿掉 — scriptor
        依賴此 key 存在, 沒 fallback 會 KeyError. 例外被改成 raise 直接踩.
        """
        import core.adapters.document as doc_adapter

        def pdf_scan(doc_path, **kw):
            stub_all["scan_document"].append({"doc_path": doc_path})
            return {
                "source_kind": "document",
                "title": "broken_pdf",
                "format": "pdf",
                "content": "...",
                "stats": {"chars": 3},
            }

        def boom(doc_path, figures_dir, **kw):
            stub_all["extract_pdf_figures"].append("called")
            raise RuntimeError("PyMuPDF parse error")

        monkeypatch.setattr(doc_adapter, "scan_document", pdf_scan)
        monkeypatch.setattr(doc_adapter, "extract_pdf_figures", boom)

        rec = _make_doc_rec(store, path="/fake/broken.pdf")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        with caplog.at_level("ERROR"):
            # 不該 raise
            deck = await _run_ingest_long_form(store, rec, deck_path, mock=True)

        # 主流程仍完成
        assert deck["deck_title"] == "Mock Deck"
        # raw["figures"] = [] fallback 鎖
        raw_disk = json.loads(
            (deck_path.parent / "raw_content.json").read_text(encoding="utf-8"),
        )
        assert raw_disk["figures"] == []
        # logger.exception 留紀錄含「PDF figure 抽取失敗」+「不擋 ingest」
        err_msgs = [r.message for r in caplog.records if r.levelname == "ERROR"]
        assert any(
            "PDF figure 抽取失敗" in m and "不擋 ingest" in m for m in err_msgs
        )


# ---------------------------------------------------------------- TestMdMermaidBranch


class TestMdMermaidBranch:
    """raw.format in ('md', 'txt') → extract_and_render_mermaid_from_text 抽 mermaid."""

    @pytest.mark.asyncio
    async def test_md_format_extracts_mermaid_to_raw(
        self, store, monkeypatch, stub_all, caplog,
    ):
        """raw["format"]='md' → mermaid extract 被叫 + 抽到的 figs 放 raw["figures"].

        鎖 .md 分支走 mermaid_text (iter 57 設計), 不該走 pdf figure 抽取
        (兩條路會搶 raw["figures"]). source_label 該收 raw.title 'doc'.
        """
        import core.mermaid_render as mermaid_mod

        def mermaid_with_figs(content, figures_dir, *, source_label=None, **kw):
            stub_all["mermaid_text"].append({
                "content": content, "figures_dir": figures_dir,
                "source_label": source_label,
            })
            return [{"id": "m1", "path": "m1.png"}]
        monkeypatch.setattr(
            mermaid_mod, "extract_and_render_mermaid_from_text", mermaid_with_figs,
        )

        rec = _make_doc_rec(store, path="/fake/notes.md")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        with caplog.at_level("INFO"):
            await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert len(stub_all["mermaid_text"]) == 1
        # figures_dir 該共用 job_dir/"figures" (跟 PDF figure 抽同目錄)
        assert stub_all["mermaid_text"][0]["figures_dir"] == \
            deck_path.parent / "figures"
        # source_label 該收 raw.title (fake_scan_document 預設回 "fake_doc")
        assert stub_all["mermaid_text"][0]["source_label"] == "fake_doc"
        # extract_pdf_figures 完全不叫 (兩條路不該混)
        assert len(stub_all["extract_pdf_figures"]) == 0
        # raw_disk 含抽到的 mermaid figs
        raw_disk = json.loads(
            (deck_path.parent / "raw_content.json").read_text(encoding="utf-8"),
        )
        assert raw_disk["figures"] == [{"id": "m1", "path": "m1.png"}]
        # logger.info 含「Mermaid 抽取 (.md)」
        assert any(
            "Mermaid 抽取" in r.message and ".md" in r.message
            for r in caplog.records
        )

    @pytest.mark.asyncio
    async def test_md_mermaid_exception_swallowed_sets_empty_list(
        self, store, monkeypatch, stub_all, caplog,
    ):
        """extract_and_render_mermaid_from_text raise → 不擋 ingest + raw["figures"]=[].

        對稱於 PDF figure 失敗路徑 — 兩 helper 失敗都該吞例外 + 補空 list.
        """
        import core.mermaid_render as mermaid_mod

        def boom(content, figures_dir, **kw):
            stub_all["mermaid_text"].append("called")
            raise RuntimeError("mermaid.ink 503")
        monkeypatch.setattr(
            mermaid_mod, "extract_and_render_mermaid_from_text", boom,
        )

        rec = _make_doc_rec(store, path="/fake/notes.md")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        with caplog.at_level("ERROR"):
            deck = await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert deck["deck_title"] == "Mock Deck"
        raw_disk = json.loads(
            (deck_path.parent / "raw_content.json").read_text(encoding="utf-8"),
        )
        assert raw_disk["figures"] == []
        err_msgs = [r.message for r in caplog.records if r.levelname == "ERROR"]
        assert any(
            "Mermaid 抽取失敗" in m and "不擋 ingest" in m for m in err_msgs
        )

    @pytest.mark.asyncio
    async def test_txt_format_also_extracts_mermaid(
        self, store, monkeypatch, stub_all,
    ):
        """raw["format"]='txt' → 同 .md 分支跑 mermaid 抽取.

        鎖條件是 `format in ("md", "txt")` 不被改成只 'md' (iter 57 設計兩種
        都試, 雖 txt 罕見有 mermaid block).
        """
        import core.adapters.document as doc_adapter

        def txt_scan(doc_path, **kw):
            stub_all["scan_document"].append({"doc_path": doc_path})
            return {
                "source_kind": "document",
                "title": "plain_note",
                "format": "txt",
                "content": "plain text",
                "stats": {"chars": 10},
            }
        monkeypatch.setattr(doc_adapter, "scan_document", txt_scan)

        rec = _make_doc_rec(store, path="/fake/note.txt")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        # mermaid extract 該被叫 (鎖條件含 'txt')
        assert len(stub_all["mermaid_text"]) == 1
        # extract_pdf_figures 不該叫
        assert len(stub_all["extract_pdf_figures"]) == 0


# ---------------------------------------------------------------- TestUnknownFormatBranch


class TestUnknownFormatBranch:
    """raw.format 既非 pdf 也非 md/txt → figures=[] (沒抽圖, 不該炸)."""

    @pytest.mark.asyncio
    async def test_unknown_format_sets_empty_figures(
        self, store, monkeypatch, stub_all,
    ):
        """未來 adapter 加新 format (例 html / docx) 預期 fallback figures=[].

        鎖 else 分支該存在 — scriptor 依賴 raw["figures"] key. 不該炸 KeyError
        也不該誤跑 PDF figure / mermaid.
        """
        import core.adapters.document as doc_adapter

        def html_scan(doc_path, **kw):
            stub_all["scan_document"].append({"doc_path": doc_path})
            return {
                "source_kind": "document",
                "title": "snapshot",
                "format": "html",  # 假未來 format
                "content": "<p>body</p>",
                "stats": {"chars": 10},
            }
        monkeypatch.setattr(doc_adapter, "scan_document", html_scan)

        rec = _make_doc_rec(store, path="/fake/page.html")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        # 兩條圖路徑都不該跑
        assert len(stub_all["extract_pdf_figures"]) == 0
        assert len(stub_all["mermaid_text"]) == 0
        # raw["figures"]=[] 透過 raw_content.json 驗
        raw_disk = json.loads(
            (deck_path.parent / "raw_content.json").read_text(encoding="utf-8"),
        )
        assert raw_disk["figures"] == []


# ---------------------------------------------------------------- TestUrlFiguresSetdefault


class TestUrlFiguresSetdefault:
    """URL adapter 不抽圖 — raw.setdefault("figures", []) 補空 list."""

    @pytest.mark.asyncio
    async def test_url_raw_figures_setdefault_empty(
        self, store, stub_all,
    ):
        """URL scan 不該觸發 PDF figure / mermaid 抽 + raw["figures"] 該 setdefault [].

        鎖 URL 分支不該誤走 DOCUMENT format 分流 (URL 沒 format 欄位). scriptor
        依賴 raw["figures"] key 存在 — setdefault 不被偷拿掉就會 KeyError.
        """
        rec = _make_url_rec(store, url="https://example.com")
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        # 兩條圖抽路徑都不該跑 (URL 不抽圖)
        assert len(stub_all["extract_pdf_figures"]) == 0
        assert len(stub_all["mermaid_text"]) == 0
        # raw_content.json 該含 figures=[] (setdefault 補上)
        raw_disk = json.loads(
            (deck_path.parent / "raw_content.json").read_text(encoding="utf-8"),
        )
        assert "figures" in raw_disk
        assert raw_disk["figures"] == []


# ---------------------------------------------------------------- TestMockBranchDispatch


class TestMockBranchDispatch:
    """mock=True / False 兩條路: 各自走 mock_* 或 *_long_form, 不該混用."""

    @pytest.mark.asyncio
    async def test_mock_true_uses_mock_helpers_only(self, store, stub_all):
        """mock=True → mock_outline + mock_deck_from_outline, 不該打 *_long_form.

        鎖 mock 分支不被改成 fall-through (否則 smoke test / dev 偷打真 Gemini).
        """
        rec = _make_doc_rec(store, options=JobOptions(mock=True))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert len(stub_all["mock_outline"]) == 1
        assert len(stub_all["mock_deck"]) == 1
        assert len(stub_all["outline_long_form"]) == 0
        assert len(stub_all["script_long_form"]) == 0

    @pytest.mark.asyncio
    async def test_mock_false_uses_real_long_form_helpers_only(
        self, store, stub_all,
    ):
        """mock=False → outline_long_form + script_long_form, mock_* 完全不該叫."""
        rec = _make_doc_rec(store, options=JobOptions(mock=False))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=False)

        assert len(stub_all["outline_long_form"]) == 1
        assert len(stub_all["script_long_form"]) == 1
        assert len(stub_all["mock_outline"]) == 0
        assert len(stub_all["mock_deck"]) == 0


# ---------------------------------------------------------------- TestScriptOptionsPassthrough


class TestScriptOptionsPassthrough:
    """length_mode / narration_style / persona 三個 iter 43 + 92 options 透傳."""

    @pytest.mark.asyncio
    async def test_length_mode_passes_to_outline_and_script(
        self, store, stub_all,
    ):
        """length_mode='lecture' → outline_long_form + script_long_form 都收.

        鎖兩處 kwarg 都該帶 (iter 43 設計: outliner 算 section 數 + scriptor
        控 narration 長度, 任一缺都會錯). 對稱 _run_ingest_repo 行為.
        """
        rec = _make_doc_rec(store, options=JobOptions(
            mock=False, length_mode="lecture",
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=False)

        assert stub_all["outline_long_form"][0]["length_mode"] == "lecture"
        assert stub_all["script_long_form"][0]["length_mode"] == "lecture"

    @pytest.mark.asyncio
    async def test_narration_style_and_persona_pass_to_script_only(
        self, store, stub_all,
    ):
        """narration_style + persona 該到 script_long_form (iter 92 L2/L3 hook).

        鎖 script_long_form 兩個 kwarg 都該帶, outline_long_form 不該收 — iter
        92 設計只在 scriptor 階段套風格, outliner 不該知道.
        """
        rec = _make_doc_rec(store, options=JobOptions(
            mock=False, narration_style="storyteller", persona="jliu_v1",
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=False)

        assert stub_all["script_long_form"][0]["narration_style"] == "storyteller"
        assert stub_all["script_long_form"][0]["persona"] == "jliu_v1"
        # outline_long_form 不該收 narration_style / persona kwargs
        # (function signature 也不接, fake stub 用 **kw 接走後沒紀錄)
        # 透過 outline_long_form 紀錄的 keys 驗證 — 只有 raw + length_mode
        outline_call = stub_all["outline_long_form"][0]
        assert set(outline_call.keys()) == {"raw", "length_mode"}


# ---------------------------------------------------------------- TestAiHelpersGated


class TestAiHelpersGated:
    """ai_generate_diagrams / ai_generate_mermaid 兩 flag 才呼叫對應 helper."""

    @pytest.mark.asyncio
    async def test_neither_flag_skips_both_helpers(self, store, stub_all):
        """兩 flag 都 False → AI 圖 / AI mermaid 兩 helper 都不該叫.

        鎖 default opt-out 行為 (iter 56/57b 預設不開, Gemini 成本考量).
        """
        rec = _make_doc_rec(store, options=JobOptions(mock=False))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=False)

        assert len(stub_all["ai_diagrams"]) == 0
        assert len(stub_all["ai_mermaid"]) == 0

    @pytest.mark.asyncio
    async def test_ai_diagrams_flag_triggers_only_diagram_helper(
        self, store, stub_all,
    ):
        """ai_generate_diagrams=True → AI 圖 helper 該叫一次, mermaid 仍不該叫.

        鎖兩 flag 獨立 gated (任一被改成 OR / 共用條件就直接踩).
        """
        rec = _make_doc_rec(store, options=JobOptions(
            mock=False, ai_generate_diagrams=True,
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=False)

        assert len(stub_all["ai_diagrams"]) == 1
        assert len(stub_all["ai_mermaid"]) == 0

    @pytest.mark.asyncio
    async def test_mock_branch_skips_ai_helpers(self, store, stub_all):
        """mock=True 即使 ai_generate_* flag 開, AI helper 也不該叫.

        鎖 AI helper 在 `if mock: ... else:` 的 else 分支 (mock 路徑該完全繞過
        所有 Gemini 呼叫, 包含 AI 圖). 對齊 _run_ingest_repo iter 134 同條.
        """
        rec = _make_doc_rec(store, options=JobOptions(
            mock=True, ai_generate_diagrams=True, ai_generate_mermaid=True,
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert len(stub_all["ai_diagrams"]) == 0
        assert len(stub_all["ai_mermaid"]) == 0


# ---------------------------------------------------------------- TestCoverOutroGated


class TestCoverOutroGated:
    """prepend_cover / append_outro 兩 flag 開才呼叫 helper + override 透傳."""

    @pytest.mark.asyncio
    async def test_no_cover_no_outro_skips_both(self, store, stub_all):
        """兩 flag 都 False → cover / outro helper 不該叫."""
        rec = _make_doc_rec(store, options=JobOptions(mock=True))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert len(stub_all["cover"]) == 0
        assert len(stub_all["outro"]) == 0

    @pytest.mark.asyncio
    async def test_prepend_cover_passes_all_overrides(self, store, stub_all):
        """prepend_cover=True → _prepend_cover_to_deck 收 speaker/org/date/narration 四 override.

        鎖 iter 62b + iter 65 全 override 都該透傳, 不被偷拿掉. 對稱
        _run_ingest_repo iter 134 同條 — long_form ingest 也該支援 cover hook.
        """
        rec = _make_doc_rec(store, options=JobOptions(
            mock=True,
            prepend_cover=True,
            cover_speaker="劉老師",
            cover_org="勤益科大 IAE",
            cover_date="2026-05-25",
            cover_narration="今天來看一篇研究論文",
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert len(stub_all["cover"]) == 1
        kw = stub_all["cover"][0]["kwargs"]
        assert kw["speaker_override"] == "劉老師"
        assert kw["org_override"] == "勤益科大 IAE"
        assert kw["date_override"] == "2026-05-25"
        assert kw["narration_override"] == "今天來看一篇研究論文"

    @pytest.mark.asyncio
    async def test_append_outro_passes_all_overrides(self, store, stub_all):
        """append_outro=True → _append_outro_to_deck 收 7 個 override.

        鎖 iter 63 + 63b + 67 全 override 都該透傳 — iter 63b 特別 fix 過
        long_form ingest 漏 hook 的 bug, 別再被 refactor 拿掉.
        """
        rec = _make_doc_rec(store, options=JobOptions(
            mock=True,
            append_outro=True,
            cover_speaker="劉老師",
            cover_org="勤益科大 IAE",
            outro_thanks="感謝聆聽",
            outro_url="https://doflab.cc",
            outro_narration="今天到此為止",
            show_qr_on_outro=True,
            outro_youtube_url="https://www.youtube.com/@dofliu",
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=True)

        assert len(stub_all["outro"]) == 1
        kw = stub_all["outro"][0]["kwargs"]
        assert kw["speaker_override"] == "劉老師"
        assert kw["org_override"] == "勤益科大 IAE"
        assert kw["thanks_override"] == "感謝聆聽"
        assert kw["url_override"] == "https://doflab.cc"
        assert kw["narration_override"] == "今天到此為止"
        assert kw["show_qr"] is True
        assert kw["youtube_url_override"] == "https://www.youtube.com/@dofliu"


# ---------------------------------------------------------------- TestDiskWrites


class TestDiskWrites:
    """raw_content.json / outline.json / deck.json 三檔寫盤格式統一."""

    @pytest.mark.asyncio
    async def test_three_json_files_chinese_no_escape_indent2(
        self, store, stub_all,
    ):
        """三檔都該 ensure_ascii=False (中文不變 \\uXXXX) + indent=2 (多行 + 2-space).

        鎖三處 write_text 都用同一組參數 — 任一被改成 ensure_ascii=True
        會讓中文無法 grep / git diff 看不懂; 任一改 indent=None 變單行讓
        deck.json review 變痛苦.
        """
        rec = _make_doc_rec(store, options=JobOptions(mock=False))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_long_form(store, rec, deck_path, mock=False)

        job_dir = deck_path.parent
        raw_content = (job_dir / "raw_content.json").read_text(encoding="utf-8")
        outline = (job_dir / "outline.json").read_text(encoding="utf-8")
        deck = deck_path.read_text(encoding="utf-8")

        # script_long_form stub 回 "Long Form Deck — 中文標題", 該保留中文
        assert "中文標題" in deck
        # 三檔都沒 \\u escape sequence
        for label, blob in (("raw", raw_content), ("outline", outline), ("deck", deck)):
            assert "\\u" not in blob, f"{label} ensure_ascii=False 鎖被改"
        # indent=2 鎖
        for label, blob in (("raw", raw_content), ("outline", outline), ("deck", deck)):
            assert "\n" in blob, f"{label} indent=2 鎖被改 (沒換行)"
            assert any(line.startswith("  ") for line in blob.splitlines()), (
                f"{label} indent=2 鎖被改 (沒 2-space 開頭)"
            )

    @pytest.mark.asyncio
    async def test_return_value_matches_deck_on_disk(self, store, stub_all):
        """return 的 deck 該跟 deck.json 寫盤內容一致 (caller _run_ingest 拿 in-memory).

        鎖 deck 不被偷做 deepcopy / transform 後寫盤 (in-memory 跟 disk 該同源,
        否則 caller 收到的跟 review UI 讀回看到的不一樣). 對稱 _run_ingest_repo
        iter 134 同條.
        """
        rec = _make_doc_rec(store, options=JobOptions(mock=False))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        deck_returned = await _run_ingest_long_form(store, rec, deck_path, mock=False)
        deck_on_disk = json.loads(deck_path.read_text(encoding="utf-8"))

        assert deck_returned == deck_on_disk
