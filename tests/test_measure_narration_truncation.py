"""N1: tools/measure_narration_truncation.py 測試覆蓋.

純函式 (split_cues / measure_deck / cue_length_distribution / aggregate /
format_markdown_report) + IO 層 (load_options_for_deck / build_record /
collect_records). 不打 Gemini / TTS / ffmpeg, 純 dict + tmp_path json.
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

import pytest

# tools/ 不是 package, 且 site-packages 有同名 `tools` 套件會 shadow
# `import tools.X`. 直接把 tools 目錄掛上 path 當 top-level module 載入, 跨
# 本機 / CI 環境都穩 (不依賴 namespace package 行為).
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.append(str(_TOOLS_DIR))

from measure_narration_truncation import (  # noqa: E402
    DEFAULT_LENGTH_MODE,
    DEFAULT_NARRATION_STYLE,
    aggregate,
    build_record,
    collect_records,
    cue_length_distribution,
    format_markdown_report,
    load_fixture_records,
    load_options_for_deck,
    make_record,
    measure_deck,
    resolve_length_mode,
    resolve_narration_style,
    split_cues,
)

# N2 committed eval fixture (匿名化代表性 deck, CI 可重現截斷率測量)
_FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "narration" / "decks.json"


# --------------------------------------------------------------------------- #
# split_cues
# --------------------------------------------------------------------------- #
class TestSplitCues:
    def test_none_and_empty(self):
        assert split_cues(None) == []
        assert split_cues("") == []
        assert split_cues("   ") == []

    def test_single_sentence_no_terminal_punct(self):
        # 沒結尾標點仍算一句 (不丟資料)
        assert split_cues("這是一句話") == ["這是一句話"]

    def test_chinese_punctuation_split(self):
        cues = split_cues("第一句。第二句！第三句？")
        assert cues == ["第一句。", "第二句！", "第三句？"]

    def test_english_punctuation_split(self):
        cues = split_cues("First sentence! Second one? Third.")
        assert cues == ["First sentence!", "Second one?", "Third."]

    def test_strips_whitespace_between(self):
        cues = split_cues("甲。\n\n  乙。  ")
        assert cues == ["甲。", "乙。"]

    def test_matches_build_srt_regex(self):
        # 跟 core.srt build_srt 同一條 regex — 對齊保證重跑可量修前/修後
        from core.srt import _SENTENCE_SPLIT
        text = "一。二！三？"
        manual = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
        assert split_cues(text) == manual


# --------------------------------------------------------------------------- #
# resolve_length_mode / resolve_narration_style
# --------------------------------------------------------------------------- #
class TestResolveOptions:
    def test_length_mode_none_options(self):
        assert resolve_length_mode(None) == DEFAULT_LENGTH_MODE

    def test_length_mode_empty_value_falls_back(self):
        assert resolve_length_mode({"length_mode": None}) == DEFAULT_LENGTH_MODE
        assert resolve_length_mode({"length_mode": ""}) == DEFAULT_LENGTH_MODE

    def test_length_mode_explicit(self):
        assert resolve_length_mode({"length_mode": "lecture"}) == "lecture"

    def test_narration_style_defaults(self):
        assert resolve_narration_style(None) == DEFAULT_NARRATION_STYLE
        assert resolve_narration_style({"narration_style": None}) == DEFAULT_NARRATION_STYLE

    def test_narration_style_explicit(self):
        assert resolve_narration_style({"narration_style": "wuxia"}) == "wuxia"


# --------------------------------------------------------------------------- #
# measure_deck
# --------------------------------------------------------------------------- #
class TestMeasureDeck:
    def test_empty_deck(self):
        m = measure_deck({}, length_mode="quick")
        assert m["total_slides"] == 0
        assert m["total_cues"] == 0
        assert m["worst_slide"] is None
        assert m["worst_cue"] is None

    def test_sections_slides_schema(self):
        deck = {
            "sections": [
                {"id": "s1", "slides": [
                    {"id": "s1_1", "narration": "短句。"},
                    {"id": "s1_2", "narration": "另一句。再一句。"},
                ]},
            ],
        }
        m = measure_deck(deck, length_mode="quick", cue_budget=40)
        assert m["total_slides"] == 2
        # s1_1 一句 + s1_2 兩句 = 3 cue
        assert m["total_cues"] == 3

    def test_v1_problems_steps_schema(self):
        deck = {
            "problems": [
                {"id": "q1", "steps": [
                    {"id": "q1_1", "narration": "解題第一步。"},
                ]},
            ],
        }
        m = measure_deck(deck, length_mode="quick")
        assert m["total_slides"] == 1
        assert m["total_cues"] == 1

    def test_skips_underscore_section(self):
        deck = {
            "sections": [
                {"id": "_cover", "slides": [{"id": "c", "narration": "模板封面" * 50}]},
                {"id": "body", "slides": [{"id": "b", "narration": "正文。"}]},
            ],
        }
        m = measure_deck(deck, length_mode="quick")
        # _cover 跳過, 只算 body
        assert m["total_slides"] == 1
        assert m["cues"][0]["section_id"] == "body"

    def test_slide_over_budget_flag(self):
        # quick preset narration 上限 120 字
        long_narr = "字" * 200
        deck = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": long_narr}]}]}
        m = measure_deck(deck, length_mode="quick")
        assert m["over_slide_count"] == 1
        assert m["worst_slide"]["excess"] > 0

    def test_per_cue_over_budget_flag(self):
        # 一句 60 字 > cue_budget 40
        deck = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "字" * 60 + "。"}]}]}
        m = measure_deck(deck, length_mode="quick", cue_budget=40)
        assert m["total_cues"] == 1
        assert m["over_cue_count"] == 1
        assert m["worst_cue"]["length"] == 61

    def test_cue_budget_boundary_not_over(self):
        # 剛好等於 budget 不算 over (用 > 不是 >=)
        deck = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "字" * 40}]}]}
        m = measure_deck(deck, length_mode="quick", cue_budget=40)
        assert m["over_cue_count"] == 0

    def test_max_chars_from_length_mode(self):
        # lecture preset 上限 280, quick 120 — 同一段在不同 mode 結果不同
        narr = "字" * 200
        deck = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": narr}]}]}
        assert measure_deck(deck, length_mode="quick")["over_slide_count"] == 1
        assert measure_deck(deck, length_mode="lecture")["over_slide_count"] == 0


# --------------------------------------------------------------------------- #
# cue_length_distribution
# --------------------------------------------------------------------------- #
class TestCueDistribution:
    def test_empty(self):
        dist = cue_length_distribution([])
        assert all(d["count"] == 0 and d["ratio"] == 0.0 for d in dist)

    def test_threshold_counting(self):
        dist = cue_length_distribution([10, 35, 45, 90], thresholds=(20, 40, 80))
        by_th = {d["threshold"]: d["count"] for d in dist}
        assert by_th[20] == 3   # 35,45,90
        assert by_th[40] == 2   # 45,90
        assert by_th[80] == 1   # 90

    def test_ratio(self):
        dist = cue_length_distribution([10, 50], thresholds=(40,))
        assert dist[0]["count"] == 1
        assert dist[0]["ratio"] == 0.5


# --------------------------------------------------------------------------- #
# aggregate
# --------------------------------------------------------------------------- #
def _rec(length_mode, style, deck, source, cue_budget=40):
    return {
        "length_mode": length_mode,
        "narration_style": style,
        "source": source,
        "measure": measure_deck(deck, length_mode=length_mode, cue_budget=cue_budget),
    }


class TestAggregate:
    def test_empty_records(self):
        agg = aggregate([])
        assert agg["groups"] == []
        assert agg["overall"]["total_cues"] == 0
        assert agg["overall"]["over_cue_ratio"] == 0.0

    def test_groups_by_mode_and_style(self):
        d = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "短。"}]}]}
        records = [
            _rec("quick", "academic", d, "jobs/a/deck.json"),
            _rec("quick", "academic", d, "jobs/b/deck.json"),
            _rec("lecture", "wuxia", d, "jobs/c/deck.json"),
        ]
        agg = aggregate(records)
        assert len(agg["groups"]) == 2
        quick_grp = next(g for g in agg["groups"]
                         if g["length_mode"] == "quick" and g["narration_style"] == "academic")
        assert quick_grp["deck_count"] == 2

    def test_over_cue_ratio_computed(self):
        # 2 cue, 1 過長 → ratio 0.5
        d = {"sections": [{"id": "s", "slides": [
            {"id": "a", "narration": "字" * 60 + "。" + "短。"},
        ]}]}
        agg = aggregate([_rec("quick", "academic", d, "jobs/x/deck.json")])
        grp = agg["groups"][0]
        assert grp["total_cues"] == 2
        assert grp["over_cue_count"] == 1
        assert grp["over_cue_ratio"] == 0.5

    def test_overall_sums_across_groups(self):
        d = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "短。"}]}]}
        agg = aggregate([
            _rec("quick", "academic", d, "jobs/a/deck.json"),
            _rec("lecture", "wuxia", d, "jobs/c/deck.json"),
        ])
        assert agg["overall"]["deck_count"] == 2
        assert agg["overall"]["total_cues"] == 2

    def test_worst_cue_tracks_source(self):
        d = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "字" * 70 + "。"}]}]}
        agg = aggregate([_rec("quick", "academic", d, "jobs/zzz/deck.json")])
        wc = agg["groups"][0]["worst_cue"]
        assert wc["_source"] == "jobs/zzz/deck.json"
        assert wc["length"] == 71

    def test_groups_sorted_deterministic(self):
        d = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "短。"}]}]}
        records = [
            _rec("quick", "wuxia", d, "jobs/a/deck.json"),
            _rec("lecture", "academic", d, "jobs/b/deck.json"),
        ]
        keys = [(g["length_mode"], g["narration_style"]) for g in aggregate(records)["groups"]]
        assert keys == sorted(keys)


# --------------------------------------------------------------------------- #
# format_markdown_report
# --------------------------------------------------------------------------- #
class TestFormatReport:
    def test_empty_groups_renders(self):
        agg = aggregate([])
        report = format_markdown_report(agg, cue_budget=40, deck_count=0)
        assert "# Narration 截斷 baseline 測量報告" in report
        assert "沒有掃到任何 deck" in report

    def test_includes_over_cue_ratio_and_headers(self):
        d = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "字" * 60 + "。"}]}]}
        agg = aggregate([_rec("quick", "academic", d, "jobs/x/deck.json")])
        report = format_markdown_report(agg, cue_budget=40, deck_count=1, generated_at="2026-05-28")
        assert "全域摘要" in report
        assert "Cue 長度分布" in report
        assert "length_mode" in report
        assert "2026-05-28" in report
        # over-cue 100% (唯一 cue 過長)
        assert "100.0%" in report

    def test_excerpt_escapes_pipe(self):
        d = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "前|後" + "字" * 60 + "。"}]}]}
        agg = aggregate([_rec("quick", "academic", d, "jobs/x/deck.json")])
        report = format_markdown_report(agg, cue_budget=40, deck_count=1)
        # worst cue 範例那行不該有原始管線符破壞表格
        excerpt_lines = [ln for ln in report.split("\n") if "前/後" in ln]
        assert excerpt_lines  # 管線符被換成斜線


# --------------------------------------------------------------------------- #
# IO 層
# --------------------------------------------------------------------------- #
class TestLoadOptions:
    def test_no_state_file(self, tmp_path):
        deck = tmp_path / "deck.json"
        deck.write_text("{}", encoding="utf-8")
        assert load_options_for_deck(deck) == {}

    def test_reads_options(self, tmp_path):
        (tmp_path / "state.json").write_text(
            json.dumps({"options": {"length_mode": "lecture", "narration_style": "wuxia"}}),
            encoding="utf-8",
        )
        deck = tmp_path / "deck.json"
        deck.write_text("{}", encoding="utf-8")
        opts = load_options_for_deck(deck)
        assert opts["length_mode"] == "lecture"

    def test_bad_state_json_returns_empty(self, tmp_path):
        (tmp_path / "state.json").write_text("{not json", encoding="utf-8")
        deck = tmp_path / "deck.json"
        deck.write_text("{}", encoding="utf-8")
        assert load_options_for_deck(deck) == {}

    def test_options_not_dict_returns_empty(self, tmp_path):
        (tmp_path / "state.json").write_text(json.dumps({"options": "oops"}), encoding="utf-8")
        deck = tmp_path / "deck.json"
        deck.write_text("{}", encoding="utf-8")
        assert load_options_for_deck(deck) == {}


class TestBuildRecord:
    def test_happy_path(self, tmp_path):
        job = tmp_path / "jobs" / "abc"
        job.mkdir(parents=True)
        (job / "state.json").write_text(
            json.dumps({"options": {"length_mode": "lecture", "narration_style": "wuxia"}}),
            encoding="utf-8",
        )
        deck = job / "deck.json"
        deck.write_text(json.dumps(
            {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "句。"}]}]}
        ), encoding="utf-8")
        rec = build_record(deck, root=tmp_path, cue_budget=40)
        assert rec["length_mode"] == "lecture"
        assert rec["narration_style"] == "wuxia"
        assert rec["source"] == "jobs/abc/deck.json"   # 相對 + forward slash
        assert rec["measure"]["total_cues"] == 1

    def test_defaults_when_no_state(self, tmp_path):
        deck = tmp_path / "deck.json"
        deck.write_text(json.dumps({"sections": []}), encoding="utf-8")
        rec = build_record(deck, root=tmp_path, cue_budget=40)
        assert rec["length_mode"] == DEFAULT_LENGTH_MODE
        assert rec["narration_style"] == DEFAULT_NARRATION_STYLE

    def test_bad_deck_json_returns_none(self, tmp_path):
        deck = tmp_path / "deck.json"
        deck.write_text("{broken", encoding="utf-8")
        assert build_record(deck, root=tmp_path, cue_budget=40) is None

    def test_non_dict_deck_returns_none(self, tmp_path):
        deck = tmp_path / "deck.json"
        deck.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert build_record(deck, root=tmp_path, cue_budget=40) is None


class TestCollectRecords:
    def test_rglob_and_sorted(self, tmp_path):
        for name in ("b", "a"):
            d = tmp_path / "jobs" / name
            d.mkdir(parents=True)
            (d / "deck.json").write_text(json.dumps(
                {"sections": [{"id": "s", "slides": [{"id": "x", "narration": "句。"}]}]}
            ), encoding="utf-8")
        records = collect_records([tmp_path / "jobs"], root=tmp_path, cue_budget=40)
        assert [r["source"] for r in records] == ["jobs/a/deck.json", "jobs/b/deck.json"]

    def test_missing_dir_skipped(self, tmp_path):
        records = collect_records([tmp_path / "nope"], root=tmp_path, cue_budget=40)
        assert records == []

    def test_dedup_across_dirs(self, tmp_path):
        # 同一個 dir 傳兩次不該重複算
        d = tmp_path / "jobs" / "a"
        d.mkdir(parents=True)
        (d / "deck.json").write_text(json.dumps(
            {"sections": [{"id": "s", "slides": [{"id": "x", "narration": "句。"}]}]}
        ), encoding="utf-8")
        jobs = tmp_path / "jobs"
        records = collect_records([jobs, jobs], root=tmp_path, cue_budget=40)
        assert len(records) == 1

    def test_skips_bad_deck(self, tmp_path):
        good = tmp_path / "jobs" / "good"
        good.mkdir(parents=True)
        (good / "deck.json").write_text(json.dumps(
            {"sections": [{"id": "s", "slides": [{"id": "x", "narration": "句。"}]}]}
        ), encoding="utf-8")
        bad = tmp_path / "jobs" / "bad"
        bad.mkdir(parents=True)
        (bad / "deck.json").write_text("{broken", encoding="utf-8")
        records = collect_records([tmp_path / "jobs"], root=tmp_path, cue_budget=40)
        assert len(records) == 1
        assert records[0]["source"] == "jobs/good/deck.json"


# --------------------------------------------------------------------------- #
# N2 — make_record 共用 helper + fixtures 模式
# --------------------------------------------------------------------------- #
class TestMakeRecord:
    def test_resolves_options_and_measures(self):
        deck = {"sections": [{"id": "s", "slides": [{"id": "a", "narration": "字" * 60 + "。"}]}]}
        rec = make_record(deck, {"length_mode": "lecture", "narration_style": "wuxia"},
                          "x/y", cue_budget=40)
        assert rec["length_mode"] == "lecture"
        assert rec["narration_style"] == "wuxia"
        assert rec["source"] == "x/y"
        assert rec["measure"]["over_cue_count"] == 1

    def test_none_options_defaults_and_slash_normalized(self):
        rec = make_record({"sections": []}, None, "a\\b", cue_budget=40)
        assert rec["length_mode"] == DEFAULT_LENGTH_MODE
        assert rec["narration_style"] == DEFAULT_NARRATION_STYLE
        assert rec["source"] == "a/b"   # 反斜線 → forward slash (跟 build_record 一致)


class TestLoadFixtureRecords:
    def _write(self, tmp_path, doc):
        p = tmp_path / "decks.json"
        p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        return p

    def test_happy_path_embedded_options(self, tmp_path):
        doc = {"fixtures": [
            {"name": "a", "options": {"length_mode": "lecture", "narration_style": "wuxia"},
             "deck": {"sections": [{"id": "s", "slides": [{"id": "x", "narration": "句。"}]}]}},
        ]}
        recs = load_fixture_records(self._write(tmp_path, doc), cue_budget=40)
        assert len(recs) == 1
        assert recs[0]["length_mode"] == "lecture"
        assert recs[0]["narration_style"] == "wuxia"
        assert recs[0]["source"] == "a"
        assert recs[0]["measure"]["total_cues"] == 1

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_fixture_records(tmp_path / "nope.json", cue_budget=40) == []

    def test_bad_json_returns_empty(self, tmp_path):
        p = tmp_path / "decks.json"
        p.write_text("{broken", encoding="utf-8")
        assert load_fixture_records(p, cue_budget=40) == []

    def test_non_dict_top_returns_empty(self, tmp_path):
        assert load_fixture_records(self._write(tmp_path, [1, 2, 3]), cue_budget=40) == []

    def test_skips_non_dict_entry_and_missing_or_bad_deck(self, tmp_path):
        doc = {"fixtures": [
            "oops",                                   # 非 dict entry
            {"name": "no_deck"},                      # 缺 deck
            {"name": "bad_deck", "deck": [1, 2]},     # deck 非 dict
            {"name": "ok", "deck": {"sections": [
                {"id": "s", "slides": [{"id": "x", "narration": "句。"}]}]}},
        ]}
        recs = load_fixture_records(self._write(tmp_path, doc), cue_budget=40)
        assert [r["source"] for r in recs] == ["ok"]

    def test_options_not_dict_falls_back_to_defaults(self, tmp_path):
        doc = {"fixtures": [{"name": "a", "options": "oops", "deck": {"sections": []}}]}
        recs = load_fixture_records(self._write(tmp_path, doc), cue_budget=40)
        assert recs[0]["length_mode"] == DEFAULT_LENGTH_MODE
        assert recs[0]["narration_style"] == DEFAULT_NARRATION_STYLE

    def test_sorted_by_source_deterministic(self, tmp_path):
        doc = {"fixtures": [
            {"name": "b", "deck": {"sections": []}},
            {"name": "a", "deck": {"sections": []}},
        ]}
        recs = load_fixture_records(self._write(tmp_path, doc), cue_budget=40)
        assert [r["source"] for r in recs] == ["a", "b"]

    def test_name_fallback_to_source_then_fixture(self, tmp_path):
        doc = {"fixtures": [
            {"source": "src/x", "deck": {"sections": []}},   # 無 name → 用 source
            {"deck": {"sections": []}},                       # 都無 → 'fixture'
        ]}
        recs = load_fixture_records(self._write(tmp_path, doc), cue_budget=40)
        assert sorted(r["source"] for r in recs) == ["fixture", "src/x"]


class TestCommittedFixture:
    """鎖 tests/fixtures/narration/decks.json — N2 可重現 baseline.

    這組數字是刻意 locked 的 regression baseline. N3 (build_srt 加 per-cue 上限)
    若重生 fixture, 數字會變動 → 測試紅, 提醒人工確認「修前 vs 修後」差異是預期的,
    而不是無聲漂移. fixture 是匿名化的真實 deck subset (CI 無 jobs 資料 / 無
    Gemini 也能逐字重現).
    """
    def test_file_exists_and_parses(self):
        assert _FIXTURE_FILE.is_file()
        data = json.loads(_FIXTURE_FILE.read_text(encoding="utf-8"))
        assert isinstance(data.get("fixtures"), list)
        assert len(data["fixtures"]) == 4

    def test_four_groups_present(self):
        recs = load_fixture_records(_FIXTURE_FILE, cue_budget=40)
        groups = {(r["length_mode"], r["narration_style"]) for r in recs}
        assert groups == {
            ("lecture", "storyteller"),
            ("quick", "comedy"),
            ("quick", "storyteller"),
            ("ultra_quick", "storyteller"),
        }

    def test_aggregate_numbers_locked(self):
        recs = load_fixture_records(_FIXTURE_FILE, cue_budget=40)
        o = aggregate(recs)["overall"]
        assert o["deck_count"] == 4
        assert o["total_slides"] == 39
        assert o["total_cues"] == 196
        assert o["over_cue_count"] == 61      # cue_budget 40
        assert o["over_slide_count"] == 31
        assert o["max_cue_len"] == 105

    def test_reproducible_across_two_loads(self):
        a = aggregate(load_fixture_records(_FIXTURE_FILE, cue_budget=40))["overall"]
        b = aggregate(load_fixture_records(_FIXTURE_FILE, cue_budget=40))["overall"]
        assert a == b

    def test_narration_anonymized_length_preserving_scheme(self):
        # 所有 ascii 字母 → 'x', 數字 → '0', 非 ascii 表意文字 → '文'.
        # 鎖「無真實教材內容外洩」+「length-preserving (cue 字數測量仍代表真實 deck)」.
        data = json.loads(_FIXTURE_FILE.read_text(encoding="utf-8"))
        for fx in data["fixtures"]:
            for sec in fx["deck"].get("sections", []):
                for sl in sec.get("slides", []):
                    for ch in (sl.get("narration") or ""):
                        if ch.isascii():
                            if ch.isalpha():
                                assert ch == "x"
                            elif ch.isdigit():
                                assert ch == "0"
                        elif unicodedata.category(ch).startswith("L"):
                            assert ch == "文"

    def test_no_real_course_terms_leaked(self):
        blob = _FIXTURE_FILE.read_text(encoding="utf-8")
        for term in ("劉瑞弘", "勤益", "PID", "材料力學", "Arduino"):
            assert term not in blob

    def test_cover_outro_sections_present_but_skipped(self):
        data = json.loads(_FIXTURE_FILE.read_text(encoding="utf-8"))
        fx = next(f for f in data["fixtures"] if any(
            str(s.get("id", "")).startswith("_") for s in f["deck"].get("sections", [])))
        deck = fx["deck"]
        underscore_slides = sum(len(s.get("slides") or []) for s in deck["sections"]
                                if str(s.get("id", "")).startswith("_"))
        body_slides = sum(len(s.get("slides") or []) for s in deck["sections"]
                          if not str(s.get("id", "")).startswith("_"))
        assert underscore_slides >= 1   # 有 cover/outro 測資
        lm = (fx.get("options") or {}).get("length_mode") or DEFAULT_LENGTH_MODE
        m = measure_deck(deck, length_mode=lm, cue_budget=40)
        assert m["total_slides"] == body_slides   # _ section 完全沒算進 measure
