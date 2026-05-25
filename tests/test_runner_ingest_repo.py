"""server.runner._run_ingest_repo — repo ingest pipeline safety lock.

`_run_ingest_repo` 是 SourceType.REPO 的 ingest 主流程:
adapter (scan_repo) → mermaid 抽取 → outliner → AI 圖 → scriptor →
cover / outro hook → 寫 raw_content.json / outline.json / deck.json.

從 iter 17 (PR-2b-i) 上線後一路加 feature (iter 43 length_mode / iter 56
AI 圖 / iter 57 mermaid 抽 / iter 62 cover / iter 63 outro / iter 92 L2/L3
narration_style + persona) 但 wrapper 本身沒對應直接測試 — 任何 refactor
不小心動:

  - `src_path.is_dir()` 防呆 (raise NotADirectoryError) — 對檔案路徑該炸
  - max_files = rec.options.max_files or 50 fallback (None → 50)
  - scan_repo 收 Path 型 src_path (不被先 str 化)
  - extract_and_render_mermaid_from_repo 收 raw 跟 figures_dir =
    deck_path.parent / "figures" (跟 AI 圖共用目錄)
  - mermaid 非空 → raw["figures"] = existing + mermaid (不被覆蓋)
  - mermaid 例外吞 (try/except 不擋 ingest, 是 design intent)
  - raw.setdefault("figures", []) 保證 key 存在 (scriptor 依賴)
  - raw_content.json / outline.json / deck.json 寫盤一律 ensure_ascii=False
    + indent=2 (中文不 escape + pretty)
  - mock=True 走 mock_outline + mock_deck_from_outline, 不該打 Gemini
  - mock=False 走 outline_repo + script_repo, length_mode /
    narration_style / persona 全透傳
  - ai_generate_diagrams / ai_generate_mermaid 兩 flag 開才呼叫對應 helper
  - prepend_cover / append_outro 兩 flag 開才呼叫對應 helper +
    cover_speaker / cover_org / cover_date / outro_thanks / outro_url
    全透傳

就直接上線 — 跟 iter 111-133 同思路 (route / helper / orchestrator safety
lock). 0 production code 改動, 純測試.

策略 = monkeypatch core.adapters.repo.scan_repo /
core.mermaid_render.extract_and_render_mermaid_from_repo / core.outliner.* /
core.scriptor.* (function-local from-import, module attribute patch 直接生效);
runner_mod._generate_ai_diagrams_for_outline /
runner_mod._generate_mermaid_for_outline /
runner_mod._prepend_cover_to_deck / runner_mod._append_outro_to_deck (module
本身就 lookup, 同 module patch 直接生效). 不真打 Gemini / 磁碟掃描 /
mermaid.ink.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import server.jobs as jobs_mod
import server.runner as runner_mod
from server.jobs import JobStore
from server.runner import _run_ingest_repo
from server.schemas import (
    CreateJobRequest,
    JobOptions,
    JobSource,
    SourceType,
)


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> JobStore:
    """乾淨 JobStore — JOBS_DIR 指 tmp_path/jobs (跟 iter 129 / 131 同 pattern)."""
    fake_root = tmp_path / "jobs"
    monkeypatch.setattr(jobs_mod, "JOBS_DIR", fake_root)
    return JobStore(root=fake_root)


@pytest.fixture
def repo_dir(tmp_path: Path) -> Path:
    """乾淨的 repo 資料夾 (空的 — scan_repo 是 stub 不真讀)."""
    d = tmp_path / "my_repo"
    d.mkdir()
    return d


def _make_rec(
    store: JobStore,
    repo_dir: Path,
    *,
    options: JobOptions | None = None,
):
    """建 REPO source_type 的 job record."""
    return store.create(CreateJobRequest(
        source_type=SourceType.REPO,
        source=JobSource(path=str(repo_dir)),
        options=options or JobOptions(),
    ))


@pytest.fixture
def stub_all(monkeypatch: pytest.MonkeyPatch):
    """把所有 dispatch 目標 stub 掉, 回傳 calls dict 給 assert.

    function-local imports:
      core.adapters.repo.scan_repo
      core.mermaid_render.extract_and_render_mermaid_from_repo
      core.outliner.mock_outline / outline_repo
      core.scriptor.mock_deck_from_outline / script_repo

    module-level (server.runner):
      _generate_ai_diagrams_for_outline / _generate_mermaid_for_outline
      _prepend_cover_to_deck / _append_outro_to_deck
    """
    import core.adapters.repo as repo_adapter
    import core.mermaid_render as mermaid_mod
    import core.outliner as outliner_mod
    import core.scriptor as scriptor_mod

    calls: dict = {
        "scan_repo": [],
        "mermaid_extract": [],
        "mock_outline": [],
        "outline_repo": [],
        "mock_deck": [],
        "script_repo": [],
        "ai_diagrams": [],
        "ai_mermaid": [],
        "cover": [],
        "outro": [],
    }

    def fake_scan_repo(src_path, *, max_files=50, **kw):
        calls["scan_repo"].append({"src_path": src_path, "max_files": max_files})
        # 預設回空 figures (各 test 想要不同 figures 自行 monkeypatch 覆蓋)
        return {"language": "python", "files": [], "figures": []}

    def fake_mermaid_extract(raw, figures_dir, **kw):
        calls["mermaid_extract"].append({"raw": raw, "figures_dir": figures_dir})
        return []  # 預設沒抽到 mermaid

    def fake_mock_outline(raw):
        calls["mock_outline"].append({"raw": raw})
        return {"sections": [{"id": "intro", "title": "Mock Outline"}]}

    def fake_outline_repo(raw, *, length_mode=None, **kw):
        calls["outline_repo"].append({"raw": raw, "length_mode": length_mode})
        return {"sections": [{"id": "intro", "title": "Real Outline"}]}

    def fake_mock_deck(outline, raw):
        calls["mock_deck"].append({"outline": outline, "raw": raw})
        return {
            "deck_title": "Mock Deck",
            "sections": [{"id": "s1", "title": "標題", "slides": []}],
        }

    def fake_script_repo(outline, raw, *, length_mode=None, narration_style=None, persona=None):
        calls["script_repo"].append({
            "outline": outline,
            "raw": raw,
            "length_mode": length_mode,
            "narration_style": narration_style,
            "persona": persona,
        })
        return {
            "deck_title": "Real Deck — 中文標題",
            "sections": [{"id": "s1", "title": "Section A", "slides": []}],
        }

    async def fake_ai_diagrams(outline, raw, job_dir):
        calls["ai_diagrams"].append({"outline": outline, "raw": raw, "job_dir": job_dir})

    async def fake_ai_mermaid(outline, raw, job_dir):
        calls["ai_mermaid"].append({"outline": outline, "raw": raw, "job_dir": job_dir})

    def fake_cover(deck, **kw):
        calls["cover"].append({"deck_id": id(deck), "kwargs": kw})

    def fake_outro(deck, **kw):
        calls["outro"].append({"deck_id": id(deck), "kwargs": kw})

    monkeypatch.setattr(repo_adapter, "scan_repo", fake_scan_repo)
    monkeypatch.setattr(mermaid_mod, "extract_and_render_mermaid_from_repo", fake_mermaid_extract)
    monkeypatch.setattr(outliner_mod, "mock_outline", fake_mock_outline)
    monkeypatch.setattr(outliner_mod, "outline_repo", fake_outline_repo)
    monkeypatch.setattr(scriptor_mod, "mock_deck_from_outline", fake_mock_deck)
    monkeypatch.setattr(scriptor_mod, "script_repo", fake_script_repo)
    monkeypatch.setattr(runner_mod, "_generate_ai_diagrams_for_outline", fake_ai_diagrams)
    monkeypatch.setattr(runner_mod, "_generate_mermaid_for_outline", fake_ai_mermaid)
    monkeypatch.setattr(runner_mod, "_prepend_cover_to_deck", fake_cover)
    monkeypatch.setattr(runner_mod, "_append_outro_to_deck", fake_outro)

    return calls


# ---------------------------------------------------------------- TestPathValidation


class TestPathValidation:
    """src_path 必須是資料夾, 不是檔不能跑 (scan_repo 假設 dir)."""

    @pytest.mark.asyncio
    async def test_file_path_raises_not_a_directory_error(
        self, store, tmp_path, stub_all,
    ):
        """src_path 指向檔案 → NotADirectoryError + 訊息含原路徑.

        鎖 `src_path.is_dir()` 防呆不被改成 `exists()` (檔案也會過 exists,
        scan_repo 會踩到 os.walk on file 行為未定義).
        """
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("hello", encoding="utf-8")
        rec = _make_rec(store, file_path)
        # rec.source.path 是 file 不是 dir
        with pytest.raises(NotADirectoryError) as exc_info:
            await _run_ingest_repo(store, rec, store.deck_path(rec.id), mock=True)
        # 訊息含原路徑 (debug 用), 不被 truncate
        assert "not_a_dir.txt" in str(exc_info.value)
        # scan_repo 不該被叫 (早 return)
        assert len(stub_all["scan_repo"]) == 0


# ---------------------------------------------------------------- TestScanRepoInvocation


class TestScanRepoInvocation:
    """scan_repo 收 Path 型 src_path + max_files fallback 50."""

    @pytest.mark.asyncio
    async def test_max_files_defaults_to_50(self, store, repo_dir, stub_all):
        """rec.options.max_files=None → fallback 50 透傳 scan_repo.

        鎖 `rec.options.max_files or 50` 不被改成 None / 其他預設.
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=True))
        store.deck_path(rec.id).parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, store.deck_path(rec.id), mock=True)
        assert stub_all["scan_repo"][0]["max_files"] == 50

    @pytest.mark.asyncio
    async def test_max_files_explicit_value_passes_through(
        self, store, repo_dir, stub_all,
    ):
        """rec.options.max_files=10 → 10 透傳 (不被覆蓋成 50).

        鎖 fallback 是 `or 50` 不是 `= 50` 強制覆寫.
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=True, max_files=10))
        store.deck_path(rec.id).parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, store.deck_path(rec.id), mock=True)
        assert stub_all["scan_repo"][0]["max_files"] == 10

    @pytest.mark.asyncio
    async def test_src_path_is_path_not_str(self, store, repo_dir, stub_all):
        """src_path 收 Path 型 (不是 str) — adapter 內部依賴 Path API."""
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=True))
        store.deck_path(rec.id).parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, store.deck_path(rec.id), mock=True)
        assert isinstance(stub_all["scan_repo"][0]["src_path"], Path)
        assert stub_all["scan_repo"][0]["src_path"] == repo_dir


# ---------------------------------------------------------------- TestMermaidExtraction


class TestMermaidExtraction:
    """extract_and_render_mermaid_from_repo: 成功 append / 空 skip / 例外吞."""

    @pytest.mark.asyncio
    async def test_mermaid_figs_appended_to_raw_figures(
        self, store, repo_dir, monkeypatch, stub_all, caplog,
    ):
        """非空 mermaid figs → raw["figures"] = existing + mermaid + log info.

        鎖 existing+new 而非 new 覆蓋 (覆蓋會吃掉 caller 已有的 figures).
        """
        import core.adapters.repo as repo_adapter
        import core.mermaid_render as mermaid_mod

        # scan_repo 回 existing fig (PDF figures, 雖 repo 不常見但 schema 支援)
        def scan_with_existing(src, *, max_files=50, **kw):
            stub_all["scan_repo"].append({"src_path": src, "max_files": max_files})
            return {"figures": [{"id": "pre_fig", "path": "pre.png"}]}
        monkeypatch.setattr(repo_adapter, "scan_repo", scan_with_existing)

        # mermaid 抽到 2 張
        def mermaid_with_figs(raw, figures_dir, **kw):
            stub_all["mermaid_extract"].append({"raw": raw, "figures_dir": figures_dir})
            return [
                {"id": "mer1", "path": "mer1.png"},
                {"id": "mer2", "path": "mer2.png"},
            ]
        monkeypatch.setattr(
            mermaid_mod, "extract_and_render_mermaid_from_repo", mermaid_with_figs,
        )

        rec = _make_rec(store, repo_dir, options=JobOptions(mock=True))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        with caplog.at_level("INFO"):
            await _run_ingest_repo(store, rec, deck_path, mock=True)

        # raw_content.json 驗 figures 順序: existing 在前, mermaid 在後
        raw_disk = json.loads((deck_path.parent / "raw_content.json").read_text(encoding="utf-8"))
        fig_ids = [f["id"] for f in raw_disk["figures"]]
        assert fig_ids == ["pre_fig", "mer1", "mer2"]
        # log info 鎖訊息格式
        assert any("Mermaid 抽取" in r.message and "2" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_mermaid_empty_setdefault_keeps_existing(
        self, store, repo_dir, stub_all,
    ):
        """mermaid 抽到空 list → raw["figures"] setdefault 確保 key 存在.

        鎖 `raw.setdefault("figures", [])` 不被偷拿掉 (scriptor 依賴此 key).
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=True))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=True)

        raw_disk = json.loads((deck_path / ".." / "raw_content.json").resolve().read_text(encoding="utf-8"))
        # 預設 stub_all 的 scan_repo 已塞 figures=[] (empty list), 加上 setdefault 不該動
        assert "figures" in raw_disk
        assert raw_disk["figures"] == []

    @pytest.mark.asyncio
    async def test_mermaid_exception_swallowed_not_propagated(
        self, store, repo_dir, monkeypatch, stub_all, caplog,
    ):
        """mermaid_extract raise → 不該擋 ingest + log.exception + raw 仍可用.

        鎖 try/except 包住 mermaid 段, design intent: mermaid 抽是 bonus
        不該擋整個 ingest 流程. 例外被改成 raise 就直接踩這條.
        """
        import core.mermaid_render as mermaid_mod

        def mermaid_boom(raw, figures_dir, **kw):
            stub_all["mermaid_extract"].append("called")
            raise RuntimeError("mermaid.ink 503")
        monkeypatch.setattr(
            mermaid_mod, "extract_and_render_mermaid_from_repo", mermaid_boom,
        )

        rec = _make_rec(store, repo_dir, options=JobOptions(mock=True))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)

        with caplog.at_level("ERROR"):
            # 不該 raise
            deck = await _run_ingest_repo(store, rec, deck_path, mock=True)

        # logger.exception 留紀錄含「Mermaid 抽取失敗」+「不擋 ingest」
        err_msgs = [r.message for r in caplog.records if r.levelname == "ERROR"]
        assert any("Mermaid 抽取失敗" in m and "不擋 ingest" in m for m in err_msgs)
        # 主流程仍完成 → deck 該回
        assert deck["deck_title"] == "Mock Deck"


# ---------------------------------------------------------------- TestMockBranchDispatch


class TestMockBranchDispatch:
    """mock=True / False 兩條路: 各自走 mock_* 或 *_repo, 不該混用."""

    @pytest.mark.asyncio
    async def test_mock_true_uses_mock_helpers_only(
        self, store, repo_dir, stub_all,
    ):
        """mock=True → mock_outline + mock_deck_from_outline, 不該打 outline_repo / script_repo.

        鎖 mock 分支不被改成 fall-through (否則 smoke test / dev 偷打真 Gemini 燒額度).
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=True))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=True)

        assert len(stub_all["mock_outline"]) == 1
        assert len(stub_all["mock_deck"]) == 1
        assert len(stub_all["outline_repo"]) == 0
        assert len(stub_all["script_repo"]) == 0

    @pytest.mark.asyncio
    async def test_mock_false_uses_real_helpers_only(
        self, store, repo_dir, stub_all,
    ):
        """mock=False → outline_repo + script_repo, mock_* 完全不該叫."""
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=False))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=False)

        assert len(stub_all["outline_repo"]) == 1
        assert len(stub_all["script_repo"]) == 1
        assert len(stub_all["mock_outline"]) == 0
        assert len(stub_all["mock_deck"]) == 0


# ---------------------------------------------------------------- TestScriptOptionsPassthrough


class TestScriptOptionsPassthrough:
    """length_mode / narration_style / persona 三個 iter 43+92 options 該透傳."""

    @pytest.mark.asyncio
    async def test_length_mode_passes_to_outline_and_script(
        self, store, repo_dir, stub_all,
    ):
        """length_mode='lecture' → outline_repo + script_repo 都收到.

        鎖兩處 kwarg 都該帶 (iter 43 設計: outline 用來算 max section
        + scriptor 用來控 narration 長度, 任一缺都會錯).
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(
            mock=False, length_mode="lecture",
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=False)

        assert stub_all["outline_repo"][0]["length_mode"] == "lecture"
        assert stub_all["script_repo"][0]["length_mode"] == "lecture"

    @pytest.mark.asyncio
    async def test_narration_style_and_persona_pass_to_script_only(
        self, store, repo_dir, stub_all,
    ):
        """narration_style + persona 該到 script_repo (iter 92 L2/L3 hook).

        鎖 script_repo 兩個 kwarg 都該帶, 不被寫死 None / 拿掉 kwarg.
        outline_repo 不該收 — iter 92 設計只在 scriptor 階段套風格.
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(
            mock=False, narration_style="wuxia", persona="jliu_v1",
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=False)

        assert stub_all["script_repo"][0]["narration_style"] == "wuxia"
        assert stub_all["script_repo"][0]["persona"] == "jliu_v1"


# ---------------------------------------------------------------- TestAiHelpersGated


class TestAiHelpersGated:
    """ai_generate_diagrams / ai_generate_mermaid 兩 flag 才呼叫對應 helper."""

    @pytest.mark.asyncio
    async def test_neither_flag_skips_both_helpers(
        self, store, repo_dir, stub_all,
    ):
        """兩 flag 都 False → AI 圖 / AI mermaid 兩 helper 都不該叫.

        鎖 default opt-out 行為 (iter 56/57b 預設不開, 成本考量).
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=False))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=False)

        assert len(stub_all["ai_diagrams"]) == 0
        assert len(stub_all["ai_mermaid"]) == 0

    @pytest.mark.asyncio
    async def test_ai_diagrams_flag_triggers_only_diagram_helper(
        self, store, repo_dir, stub_all,
    ):
        """ai_generate_diagrams=True → AI 圖 helper 該叫一次, mermaid 仍不該叫.

        鎖兩 flag 獨立 gated (任一被改成 OR / 共用條件就直接踩).
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(
            mock=False, ai_generate_diagrams=True,
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=False)

        assert len(stub_all["ai_diagrams"]) == 1
        assert len(stub_all["ai_mermaid"]) == 0

    @pytest.mark.asyncio
    async def test_ai_mermaid_flag_triggers_only_mermaid_helper(
        self, store, repo_dir, stub_all,
    ):
        """ai_generate_mermaid=True → mermaid helper 該叫一次, AI 圖仍不該叫.

        對稱於 ai_diagrams test, 鎖兩 flag 不該被合成同一條.
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(
            mock=False, ai_generate_mermaid=True,
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=False)

        assert len(stub_all["ai_diagrams"]) == 0
        assert len(stub_all["ai_mermaid"]) == 1

    @pytest.mark.asyncio
    async def test_mock_branch_skips_ai_helpers(
        self, store, repo_dir, stub_all,
    ):
        """mock=True 即使 ai_generate_* flag 開, AI helper 也不該叫.

        鎖 AI helper 在 `if mock: ... else:` 的 else 分支 (mock 路徑該完全
        繞過所有 Gemini 呼叫, 包含 AI 圖).
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(
            mock=True, ai_generate_diagrams=True, ai_generate_mermaid=True,
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=True)

        assert len(stub_all["ai_diagrams"]) == 0
        assert len(stub_all["ai_mermaid"]) == 0


# ---------------------------------------------------------------- TestCoverOutroGated


class TestCoverOutroGated:
    """prepend_cover / append_outro 兩 flag 開才呼叫 helper + override 透傳."""

    @pytest.mark.asyncio
    async def test_no_cover_no_outro_skips_both(
        self, store, repo_dir, stub_all,
    ):
        """兩 flag 都 False → cover / outro helper 不該叫."""
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=True))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=True)

        assert len(stub_all["cover"]) == 0
        assert len(stub_all["outro"]) == 0

    @pytest.mark.asyncio
    async def test_prepend_cover_passes_all_overrides(
        self, store, repo_dir, stub_all,
    ):
        """prepend_cover=True → _prepend_cover_to_deck 收 speaker/org/date/narration 四 override.

        鎖 iter 62b + iter 65 全 override 都該透傳, 不被偷拿掉 (UI 設定的
        per-job 講者 / 單位 / 日期 / 口白 任一漏就 fallback 到 env 預設,
        用戶會覺得「設了沒生效」).
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(
            mock=True,
            prepend_cover=True,
            cover_speaker="劉老師",
            cover_org="勤益科大 IAE",
            cover_date="2026-05-24",
            cover_narration="今天來看看材料力學",
        ))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=True)

        assert len(stub_all["cover"]) == 1
        kw = stub_all["cover"][0]["kwargs"]
        assert kw["speaker_override"] == "劉老師"
        assert kw["org_override"] == "勤益科大 IAE"
        assert kw["date_override"] == "2026-05-24"
        assert kw["narration_override"] == "今天來看看材料力學"

    @pytest.mark.asyncio
    async def test_append_outro_passes_all_overrides(
        self, store, repo_dir, stub_all,
    ):
        """append_outro=True → _append_outro_to_deck 收 7 個 override.

        鎖 iter 63 + 67 全 override 都該透傳: speaker / org (跟 cover 共用),
        outro_thanks / outro_url / outro_narration / show_qr / outro_youtube_url.
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(
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
        await _run_ingest_repo(store, rec, deck_path, mock=True)

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
    async def test_three_json_files_all_chinese_no_escape_indent2(
        self, store, repo_dir, stub_all,
    ):
        """三個 JSON 都該 ensure_ascii=False (中文不變 \\uXXXX) + indent=2.

        鎖三處 write_text 都用同一組參數 — 任一被改成 ensure_ascii=True
        會讓中文無法 grep / git diff 看不懂; 任一改 indent=None 變單行
        會讓人讀 deck.json 抓設定 issue 變痛苦.
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=False))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        await _run_ingest_repo(store, rec, deck_path, mock=False)

        job_dir = deck_path.parent
        raw_content = (job_dir / "raw_content.json").read_text(encoding="utf-8")
        outline = (job_dir / "outline.json").read_text(encoding="utf-8")
        deck = deck_path.read_text(encoding="utf-8")

        # 中文原字 (script_repo stub 回傳 "Real Deck — 中文標題") 該存在 deck.json
        assert "中文標題" in deck
        # 三檔都沒 \\u escape sequence
        for blob in (raw_content, outline, deck):
            assert "\\u" not in blob, "ensure_ascii=False 鎖被改"
        # indent=2 鎖: 多行 + 至少一行 2-space 開頭
        for label, blob in (("raw", raw_content), ("outline", outline), ("deck", deck)):
            assert "\n" in blob, f"{label} indent=2 鎖被改 (沒換行)"
            assert any(line.startswith("  ") for line in blob.splitlines()), (
                f"{label} indent=2 鎖被改 (沒 2-space 開頭)"
            )

    @pytest.mark.asyncio
    async def test_return_value_matches_deck_on_disk(
        self, store, repo_dir, stub_all,
    ):
        """return 的 deck 該跟 deck.json 寫盤內容一致 (caller _run_ingest 拿 in-memory).

        鎖 deck 不被偷做 deepcopy / transform 後寫盤 (in-memory 跟 disk 該同源,
        否則 caller 收到的跟 review UI 讀回看到的不一樣).
        """
        rec = _make_rec(store, repo_dir, options=JobOptions(mock=False))
        deck_path = store.deck_path(rec.id)
        deck_path.parent.mkdir(parents=True, exist_ok=True)
        deck_returned = await _run_ingest_repo(store, rec, deck_path, mock=False)
        deck_on_disk = json.loads(deck_path.read_text(encoding="utf-8"))

        assert deck_returned == deck_on_disk
