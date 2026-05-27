"""server.runner._run_render_inner — render-phase schema dispatch safety lock.

_run_render_inner 是 render 階段最內層 (由 _run_render 包 video_dimensions
/ talking_head 兩 context 進來). value-add 在 schema dispatch 一段:

  deck.json 讀進來後判 schema:
    - "sections" in deck AND "problems" not in deck → 走 deck 系列轉換:
        * source_type == SLIDES_PDF → deck_to_exam_schema_slides
          (PR-3h: 簡報走 SlideRenderer 用原始投影片當底圖)
        * source_type ∈ {REPO, DOCUMENT, URL} →
          deck_to_exam_schema_pptx(short_video_layout=bool(...))
          (長篇講解走 Forest pptx 主題, iter 88 加 short_video_layout 大字 layout)
        * 其他 (EXAM_PDF 邊緣 case) → deck_to_exam_schema (黑板)
    - 否則 (v1 problems schema) → 直接走, 不轉換

  section_id 過濾:
    - None → 全部 problems render
    - 字串值 → filter problems[].id == value
    - 找不到 → ValueError(f"section_id={section_id} 在 deck 中找不到")

  缺檔防呆:
    - deck.json 不存在 → FileNotFoundError 訊息含「deck.json 不存在」+「ingest
      階段未完成」+ 原 path (debug 用訊息該完整)

從 PR-3a / PR-3h / iter 88 上線後一路加 feature (slide_pdf 分流, pptx 主題,
short_video_layout) 但 wrapper 本身沒對應直接測試 — 任何 refactor 不小心動:

  - schema 判斷 (sections AND not problems) 兩條件被改一條
  - 三分支 dispatch 條件被改順序或漏掉 source_type
  - short_video_layout bool() 強制轉型被偷拿掉 (None 透傳會被 pptx helper 當
    truthy 走錯 layout)
  - section_id None / 字串 / 不存在 三 case 任一被偷改
  - FileNotFoundError 訊息被 truncate

就直接上線, 跟 iter 111-135 同思路 (route / helper / orchestrator safety lock).

策略 = monkeypatch core.deck.deck_to_exam_schema_* 三 helper 計呼叫 +
core.problem_to_v0_json + core.render_video stub 出來; OUTPUT_DIR / figures_dir
指 tmp_path. 不真打渲染 / ffmpeg / TTS. 0 production code 改動.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import core
import core.config as config_mod
import core.deck as deck_mod
import server.jobs as jobs_mod
import server.runner as runner_mod
from server.jobs import JobStore
from server.runner import _run_render_inner
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    SourceType,
)


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    """乾淨 JobStore — JOBS_DIR 指 tmp_path/jobs (跟 iter 129/131/134/135 同 pattern)."""
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


@pytest.fixture
def output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """OUTPUT_DIR 指 tmp_path/output (避免污染真實 OUTPUT_DIR + 觸發 render).

    runner 內 function-local `from core.config import OUTPUT_DIR` 每次重 lookup,
    monkeypatch core.config.OUTPUT_DIR 直接生效 (跟 iter 126 pattern 一致).
    """
    fake = tmp_path / "output"
    monkeypatch.setattr(config_mod, "OUTPUT_DIR", fake)
    return fake


def _make_rec(store: JobStore, source_type: SourceType, **opts):
    """建 job record — source.path 帶 / 不帶 url 看 source_type."""
    if source_type == SourceType.URL:
        src = JobSource(url="https://example.com/post")
    else:
        src = JobSource(path="/fake/source")
    return store.create(CreateJobRequest(
        source_type=source_type,
        source=src,
        options=JobOptions(**opts),
    ))


def _write_deck(deck_path: Path, deck: dict) -> None:
    """寫 deck.json 到指定 path (parent 自動建)."""
    deck_path.parent.mkdir(parents=True, exist_ok=True)
    deck_path.write_text(
        json.dumps(deck, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _v1_deck(problems: list[dict] | None = None) -> dict:
    """v1 exam schema (problems / steps) — 直接走不轉換."""
    if problems is None:
        problems = [{
            "id": "q1",
            "number": "第 1 題",
            "score": 20,
            "problem": "題目原文",
            "steps": [
                {"_section": "題目解讀", "display": "顯示", "narration": "旁白"},
            ],
        }]
    return {"exam_title": "材料力學", "problems": problems}


def _deck_sections() -> dict:
    """deck schema (sections / slides) — 需要走 deck_to_exam_schema_* 轉換."""
    return {
        "deck_title": "Python 入門",
        "source_type": "repo",
        "sections": [
            {
                "id": "intro",
                "title": "第一章",
                "slides": [
                    {
                        "id": "intro_1",
                        "title": "Hello",
                        "bullets": ["A", "B"],
                        "narration": "旁白",
                    },
                ],
            },
        ],
    }


@pytest.fixture
def stub_render(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stub 三 deck_to_exam_schema_* helper + problem_to_v0_json + render_video.

    function-local `from core.deck import ...` / `from core import problem_to_v0_json,
    render_video` 每次 _run_render_inner 進來都重新 lookup module attribute,
    monkeypatch 直接生效 (跟 iter 126/127/128/130 pattern 一致).

    所有 stub 都回固定 v1 schema, problem 數 = 入參 sections 數 (測試控制).
    """
    calls: dict = {
        "to_exam": [],
        "to_pptx": [],
        "to_slides": [],
        "p2v0": [],
        "render_video": [],
    }

    def _stub_exam(deck: dict) -> dict:
        calls["to_exam"].append({"deck_id": id(deck)})
        return _v1_from_sections(deck, marker="exam")

    def _stub_pptx(deck: dict, *, short_video_layout: bool = False) -> dict:
        calls["to_pptx"].append({
            "deck_id": id(deck),
            "short_video_layout": short_video_layout,
        })
        return _v1_from_sections(deck, marker="pptx")

    def _stub_slides(deck: dict) -> dict:
        calls["to_slides"].append({"deck_id": id(deck)})
        return _v1_from_sections(deck, marker="slides")

    def _stub_p2v0(exam_title: str, prob: dict) -> dict:
        calls["p2v0"].append({
            "exam_title": exam_title,
            "prob_id": prob.get("id"),
        })
        return {
            "title": f"{exam_title} — {prob.get('number', prob.get('id'))}",
            "steps": prob.get("steps", []),
        }

    async def _stub_render_video(json_path, out_name, start_step=None):
        calls["render_video"].append({
            "json_path": json_path,
            "out_name": out_name,
            "start_step": start_step,
        })

    monkeypatch.setattr(deck_mod, "deck_to_exam_schema", _stub_exam)
    monkeypatch.setattr(deck_mod, "deck_to_exam_schema_pptx", _stub_pptx)
    monkeypatch.setattr(deck_mod, "deck_to_exam_schema_slides", _stub_slides)
    monkeypatch.setattr(core, "problem_to_v0_json", _stub_p2v0)
    monkeypatch.setattr(core, "render_video", _stub_render_video)

    return calls


def _v1_from_sections(deck: dict, *, marker: str) -> dict:
    """把 deck.sections 轉成假 v1 problems, 標 marker 區分走哪條 helper."""
    problems = []
    for sec in deck.get("sections", []):
        problems.append({
            "id": sec["id"],
            "number": f"[{marker}] {sec.get('title', '')}",
            "score": 0,
            "problem": "",
            "steps": [
                {"_section": "x", "display": "y", "narration": "z"},
            ],
        })
    return {"exam_title": deck.get("deck_title", "Untitled"), "problems": problems}


# ---------------------------------------------------------------- TestMissingDeckFile


class TestMissingDeckFile:
    """deck.json 不存在 → FileNotFoundError, 訊息該含原 path (debug 用)."""

    @pytest.mark.asyncio
    async def test_missing_deck_raises_with_path(
        self, store, output_dir, stub_render,
    ):
        """deck.json 沒寫過 → FileNotFoundError + 訊息含『deck.json 不存在』
        + 『ingest 階段未完成』+ 原 path.

        鎖訊息格式: refactor 改 raise 別 exception type / 訊息被 truncate /
        path 被拿掉, 用戶 debug 看不到哪個 job 卡哪一步, 真的會踩.
        render_video / 三 helper 完全沒被叫 (早 return).
        """
        rec = _make_rec(store, SourceType.DOCUMENT)
        # 不寫 deck.json

        with pytest.raises(FileNotFoundError) as exc_info:
            await _run_render_inner(store, rec)

        msg = str(exc_info.value)
        assert "deck.json 不存在" in msg
        assert "ingest 階段未完成" in msg
        assert str(store.deck_path(rec.id)) in msg
        # 三 helper / render_video 任一被叫 = 防呆失效
        assert stub_render["to_exam"] == []
        assert stub_render["to_pptx"] == []
        assert stub_render["to_slides"] == []
        assert stub_render["render_video"] == []


# ---------------------------------------------------------------- TestV1SchemaPassthrough


class TestV1SchemaPassthrough:
    """v1 exam schema (problems 為頂層) → 不走 deck_to_exam_schema_* 任一."""

    @pytest.mark.asyncio
    async def test_problems_only_skips_conversion(
        self, store, output_dir, stub_render,
    ):
        """deck 只有 problems 沒 sections → 三 helper 全 0 呼叫, render_video
        直接吃 deck.problems.

        鎖 schema 判斷『if "sections" in deck AND "problems" not in deck』
        條件成立才走轉換 — 改成只看 "sections" 會讓 v1 deck 也跑進轉換炸
        KeyError (v1 沒 sections).
        """
        rec = _make_rec(store, SourceType.EXAM_PDF)
        _write_deck(store.deck_path(rec.id), _v1_deck())

        await _run_render_inner(store, rec)

        assert stub_render["to_exam"] == []
        assert stub_render["to_pptx"] == []
        assert stub_render["to_slides"] == []
        assert len(stub_render["render_video"]) == 1
        # problem_to_v0_json 該被叫過, exam_title 該是 v1 deck.exam_title
        assert len(stub_render["p2v0"]) == 1
        assert stub_render["p2v0"][0]["exam_title"] == "材料力學"
        assert stub_render["p2v0"][0]["prob_id"] == "q1"

    @pytest.mark.asyncio
    async def test_hybrid_deck_skips_conversion(
        self, store, output_dir, stub_render,
    ):
        """deck 同時有 problems AND sections → 不走轉換 (v1 優先).

        鎖條件兩段都該檢: 改成只看 'sections' 會跑進轉換, problems 已存在
        被覆蓋. 防呆設計, 不該被偷簡化掉.
        """
        rec = _make_rec(store, SourceType.REPO)
        deck = _v1_deck()
        deck["sections"] = [{"id": "x", "title": "y", "slides": []}]
        _write_deck(store.deck_path(rec.id), deck)

        await _run_render_inner(store, rec)

        assert stub_render["to_exam"] == []
        assert stub_render["to_pptx"] == []
        assert stub_render["to_slides"] == []
        assert len(stub_render["render_video"]) == 1


# ---------------------------------------------------------------- TestSchemaDispatch


class TestSchemaDispatch:
    """deck sections schema → source_type 決定走哪 helper."""

    @pytest.mark.asyncio
    async def test_slides_pdf_calls_to_exam_schema_slides(
        self, store, output_dir, stub_render,
    ):
        """source_type=SLIDES_PDF + sections schema → deck_to_exam_schema_slides.

        鎖 PR-3h 設計: 簡報走 SlideRenderer (原始投影片當底圖), 不是黑板也
        不是 pptx Forest. 改成走 pptx 會丟掉 bg_image 縮圖, UI 體驗大不同.
        其他兩 helper counter=0 (鎖分支不混選).
        """
        rec = _make_rec(store, SourceType.SLIDES_PDF)
        _write_deck(store.deck_path(rec.id), _deck_sections())

        await _run_render_inner(store, rec)

        assert len(stub_render["to_slides"]) == 1
        assert stub_render["to_pptx"] == []
        assert stub_render["to_exam"] == []

    @pytest.mark.asyncio
    async def test_repo_calls_to_exam_schema_pptx(
        self, store, output_dir, stub_render,
    ):
        """source_type=REPO + sections schema → deck_to_exam_schema_pptx.

        鎖長篇 repo 講解走 Forest pptx 主題 (比黑板適合). 改成黑板會丟掉
        Forest 色票 + Code highlight, 對程式碼 sample 體驗大壞.
        """
        rec = _make_rec(store, SourceType.REPO)
        _write_deck(store.deck_path(rec.id), _deck_sections())

        await _run_render_inner(store, rec)

        assert len(stub_render["to_pptx"]) == 1
        assert stub_render["to_slides"] == []
        assert stub_render["to_exam"] == []

    @pytest.mark.asyncio
    async def test_document_calls_to_exam_schema_pptx(
        self, store, output_dir, stub_render,
    ):
        """source_type=DOCUMENT + sections schema → deck_to_exam_schema_pptx.

        鎖 DOCUMENT 跟 REPO 共用 pptx 路徑 (兩者都是長篇講解類). 改成走 slides
        會炸 SlideRenderer 找不到 bg_image (DOCUMENT 沒有原始投影片).
        """
        rec = _make_rec(store, SourceType.DOCUMENT)
        _write_deck(store.deck_path(rec.id), _deck_sections())

        await _run_render_inner(store, rec)

        assert len(stub_render["to_pptx"]) == 1
        assert stub_render["to_slides"] == []
        assert stub_render["to_exam"] == []

    @pytest.mark.asyncio
    async def test_url_calls_to_exam_schema_pptx(
        self, store, output_dir, stub_render,
    ):
        """source_type=URL + sections schema → deck_to_exam_schema_pptx.

        鎖 URL 跟 DOCUMENT/REPO 共用 pptx 路徑 (網路爬下來的長篇文本同性質).
        """
        rec = _make_rec(store, SourceType.URL)
        _write_deck(store.deck_path(rec.id), _deck_sections())

        await _run_render_inner(store, rec)

        assert len(stub_render["to_pptx"]) == 1
        assert stub_render["to_slides"] == []
        assert stub_render["to_exam"] == []

    @pytest.mark.asyncio
    async def test_exam_pdf_with_sections_falls_back_to_to_exam_schema(
        self, store, output_dir, stub_render,
    ):
        """source_type=EXAM_PDF + sections schema (邊緣 case) → deck_to_exam_schema
        (黑板 fallback).

        EXAM_PDF 正常會直接吐 v1 schema 不走這條, 但若理論上拿到 sections
        schema (例如未來新 source type 沒接上), 該走 else 分支 (黑板 fallback).
        鎖 else 分支存在, 不被偷拿掉成 NotImplementedError 或 fall-through
        到第一 if (slides) 走錯.
        """
        rec = _make_rec(store, SourceType.EXAM_PDF)
        _write_deck(store.deck_path(rec.id), _deck_sections())

        await _run_render_inner(store, rec)

        assert len(stub_render["to_exam"]) == 1
        assert stub_render["to_pptx"] == []
        assert stub_render["to_slides"] == []


# ---------------------------------------------------------------- TestShortVideoLayoutPassthrough


class TestShortVideoLayoutPassthrough:
    """short_video_layout 該以 bool() 強制轉型透傳給 deck_to_exam_schema_pptx."""

    @pytest.mark.asyncio
    async def test_short_video_layout_true_passes_through(
        self, store, output_dir, stub_render,
    ):
        """short_video_layout=True → pptx helper 收 short_video_layout=True.

        鎖 iter 88 設計: True 觸發大字 layout (給 Shorts 用). 不被偷改成
        寫死 False 或漏 kwarg, 否則 short_video_layout=True 的 job 渲出來
        仍是長片 layout, 用戶覺得「設了沒生效」.
        """
        rec = _make_rec(store, SourceType.REPO, short_video_layout=True)
        _write_deck(store.deck_path(rec.id), _deck_sections())

        await _run_render_inner(store, rec)

        assert len(stub_render["to_pptx"]) == 1
        assert stub_render["to_pptx"][0]["short_video_layout"] is True

    @pytest.mark.asyncio
    async def test_short_video_layout_false_passes_through(
        self, store, output_dir, stub_render,
    ):
        """short_video_layout=False (預設) → pptx helper 收 short_video_layout=False.

        鎖 bool() 強制轉型 (False 預設不被誤改成 None 透傳 — None 會被 helper
        當 truthy 走錯 layout, iter 88 上線前的常見 bug).
        """
        rec = _make_rec(store, SourceType.REPO)  # short_video_layout 預設 False
        _write_deck(store.deck_path(rec.id), _deck_sections())

        await _run_render_inner(store, rec)

        assert len(stub_render["to_pptx"]) == 1
        assert stub_render["to_pptx"][0]["short_video_layout"] is False


# ---------------------------------------------------------------- TestSectionIdFilter


class TestSectionIdFilter:
    """section_id 過濾 — None 全部 / 字串 filter / 不存在 ValueError."""

    @pytest.mark.asyncio
    async def test_section_id_none_renders_all(
        self, store, output_dir, stub_render,
    ):
        """section_id=None → 全部 problems render.

        鎖預設行為 (整份 render). 三個 problem 都該叫 render_video 一次.
        """
        rec = _make_rec(store, SourceType.EXAM_PDF)
        problems = [
            {"id": "q1", "number": "Q1", "problem": "p1", "steps": [], "score": 0},
            {"id": "q2", "number": "Q2", "problem": "p2", "steps": [], "score": 0},
            {"id": "q3", "number": "Q3", "problem": "p3", "steps": [], "score": 0},
        ]
        _write_deck(store.deck_path(rec.id), _v1_deck(problems=problems))

        await _run_render_inner(store, rec, section_id=None)

        assert len(stub_render["render_video"]) == 3

    @pytest.mark.asyncio
    async def test_section_id_matching_filters_to_one(
        self, store, output_dir, stub_render,
    ):
        """section_id='q2' → 只 render 該 problem.

        鎖 PR-4a section re-render: 用戶點某章重 render, 不該誤動其他章.
        改成 render 全部會把已 review 的 final.mp4 也重打.
        """
        rec = _make_rec(store, SourceType.EXAM_PDF)
        problems = [
            {"id": "q1", "number": "Q1", "problem": "p1", "steps": [], "score": 0},
            {"id": "q2", "number": "Q2", "problem": "p2", "steps": [], "score": 0},
            {"id": "q3", "number": "Q3", "problem": "p3", "steps": [], "score": 0},
        ]
        _write_deck(store.deck_path(rec.id), _v1_deck(problems=problems))

        await _run_render_inner(store, rec, section_id="q2")

        assert len(stub_render["render_video"]) == 1
        assert len(stub_render["p2v0"]) == 1
        assert stub_render["p2v0"][0]["prob_id"] == "q2"

    @pytest.mark.asyncio
    async def test_section_id_unmatched_raises_value_error(
        self, store, output_dir, stub_render,
    ):
        """section_id='zzz' (deck 中找不到) → ValueError + 訊息含 'section_id='
        + 原值.

        鎖訊息格式 (debug 用). render_video 完全沒被叫 (早 raise).
        """
        rec = _make_rec(store, SourceType.EXAM_PDF)
        _write_deck(store.deck_path(rec.id), _v1_deck())

        with pytest.raises(ValueError) as exc_info:
            await _run_render_inner(store, rec, section_id="zzz")

        msg = str(exc_info.value)
        assert "section_id=zzz" in msg
        assert "找不到" in msg
        assert stub_render["render_video"] == []

    @pytest.mark.asyncio
    async def test_section_id_filter_works_after_schema_dispatch(
        self, store, output_dir, stub_render,
    ):
        """deck sections schema + section_id 過濾 → 仍能 filter to_pptx 回傳的
        v1 problems (鎖 filter 在 schema dispatch 後跑).

        deck.sections=[{id:intro}, {id:body}], stub_pptx 把它變成
        problems=[{id:intro},{id:body}], filter section_id='body' 該只剩 1.
        若 filter 跑在 schema dispatch 前, 會對 deck.sections (沒 problems key)
        操作炸 KeyError.
        """
        rec = _make_rec(store, SourceType.REPO)
        deck = _deck_sections()
        deck["sections"].append({"id": "body", "title": "Body", "slides": []})
        _write_deck(store.deck_path(rec.id), deck)

        await _run_render_inner(store, rec, section_id="body")

        # pptx helper 仍被叫過 (filter 在 dispatch 之後)
        assert len(stub_render["to_pptx"]) == 1
        # filter 後只 render 一個
        assert len(stub_render["render_video"]) == 1
        assert stub_render["p2v0"][0]["prob_id"] == "body"
