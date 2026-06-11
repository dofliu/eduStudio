"""F9-2 課程術語/讀音表 glossary — schema + 套用層測試（全 offline，不打任何 API）。

覆蓋:
- schema 驗證（term/course 非空 type guard、別名、各語言固定譯名）。
- 套用層 map：讀音 / 翻譯固定譯名 / 縮寫展開（surface form 展開、longest-first、後者覆蓋）。
- 載入/存檔 roundtrip + 檔案不存在回 None + 壞檔嚴格拋。
- 與 tts_backend.normalize_text 的整合（extra_pronunciation 課程蓋全域、預設不影響既有）。
"""
from __future__ import annotations

import json

import pytest

from core import glossary as G
from tts_backend import normalize_text


# ---------- schema ----------
class TestSchema:
    def test_minimal_entry(self):
        e = G.GlossaryEntry(term="自然頻率")
        assert e.term == "自然頻率"
        assert e.reading is None
        assert e.translations == {}
        assert e.aliases == []

    def test_term_stripped(self):
        assert G.GlossaryEntry(term="  ω_n  ").term == "ω_n"

    def test_empty_term_rejected(self):
        with pytest.raises(ValueError):
            G.GlossaryEntry(term="   ")

    def test_course_required_non_empty(self):
        with pytest.raises(ValueError):
            G.Glossary(course="  ")

    def test_full_entry(self):
        e = G.GlossaryEntry(
            term="ω_n",
            reading="自然頻率",
            translations={"en": "natural frequency"},
            expansion="natural frequency (undamped)",
            aliases=["ωn", "wn"],
            note="控制系統脈絡",
        )
        assert e.reading == "自然頻率"
        assert e.translations["en"] == "natural frequency"

    def test_surface_forms_dedup_and_longest_first(self):
        e = G.GlossaryEntry(term="ω", aliases=["ω_n", "ω", "  ", "wn"])
        forms = e.surface_forms()
        # 去重 + 去空 + 長到短
        assert forms == ["ω_n", "wn", "ω"]


# ---------- 套用層 map ----------
class TestPronunciationMap:
    def test_collects_reading_for_all_surface_forms(self):
        gl = G.Glossary(
            course="自控",
            entries=[
                G.GlossaryEntry(term="ω_n", reading="自然頻率", aliases=["ωn", "wn"]),
            ],
        )
        m = G.to_pronunciation_map(gl)
        assert m == {"ω_n": "自然頻率", "ωn": "自然頻率", "wn": "自然頻率"}

    def test_entries_without_reading_skipped(self):
        gl = G.Glossary(
            course="材力",
            entries=[
                G.GlossaryEntry(term="σ", translations={"en": "stress"}),  # 無 reading
                G.GlossaryEntry(term="τ", reading="剪應力"),
            ],
        )
        assert G.to_pronunciation_map(gl) == {"τ": "剪應力"}

    def test_later_entry_overrides_same_form(self):
        gl = G.Glossary(
            course="x",
            entries=[
                G.GlossaryEntry(term="σ", reading="sigma"),
                G.GlossaryEntry(term="σ", reading="應力"),
            ],
        )
        assert G.to_pronunciation_map(gl)["σ"] == "應力"


class TestTranslationMap:
    def test_per_lang_lookup(self):
        gl = G.Glossary(
            course="自控",
            entries=[
                G.GlossaryEntry(
                    term="阻尼比",
                    translations={"en": "damping ratio", "ja": "減衰比"},
                    aliases=["ζ"],
                ),
                G.GlossaryEntry(term="增益", translations={"en": "gain"}),
            ],
        )
        assert G.translation_map(gl, "en") == {
            "阻尼比": "damping ratio",
            "ζ": "damping ratio",
            "增益": "gain",
        }
        assert G.translation_map(gl, "ja") == {"阻尼比": "減衰比", "ζ": "減衰比"}

    def test_lang_absent_returns_empty(self):
        gl = G.Glossary(
            course="x",
            entries=[G.GlossaryEntry(term="增益", translations={"en": "gain"})],
        )
        assert G.translation_map(gl, "fr") == {}


class TestExpansionMap:
    def test_expansion_for_surface_forms(self):
        gl = G.Glossary(
            course="自控",
            entries=[
                G.GlossaryEntry(term="PID", expansion="比例-積分-微分", aliases=["P.I.D."]),
                G.GlossaryEntry(term="增益"),  # 無 expansion
            ],
        )
        assert G.expansion_map(gl) == {
            "PID": "比例-積分-微分",
            "P.I.D.": "比例-積分-微分",
        }


# ---------- 載入 / 存檔 ----------
class TestPersistence:
    def test_roundtrip(self, tmp_path):
        gl = G.Glossary(
            course="材力",
            entries=[
                G.GlossaryEntry(term="σ", reading="應力", translations={"en": "stress"}),
            ],
        )
        p = G.glossary_path_for(tmp_path)
        assert p.name == "glossary.json"
        G.save_glossary(gl, p)
        loaded = G.load_glossary(p)
        assert loaded == gl

    def test_save_creates_parent_dirs(self, tmp_path):
        gl = G.Glossary(course="x")
        p = tmp_path / "deep" / "nested" / "glossary.json"
        G.save_glossary(gl, p)
        assert p.is_file()

    def test_missing_file_returns_none(self, tmp_path):
        assert G.load_glossary(tmp_path / "nope.json") is None

    def test_corrupt_json_raises(self, tmp_path):
        p = tmp_path / "glossary.json"
        p.write_text("{ not json", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            G.load_glossary(p)

    def test_schema_violation_raises(self, tmp_path):
        p = tmp_path / "glossary.json"
        p.write_text(json.dumps({"entries": []}), encoding="utf-8")  # 缺 course
        with pytest.raises(ValueError):
            G.load_glossary(p)


# ---------- 與 tts_backend.normalize_text 整合 ----------
class TestNormalizeIntegration:
    def test_extra_pronunciation_applied(self):
        gl = G.Glossary(
            course="自控",
            entries=[G.GlossaryEntry(term="ω_n", reading="自然頻率")],
        )
        out = normalize_text("系統的 ω_n 很高", extra_pronunciation=G.to_pronunciation_map(gl))
        assert "自然頻率" in out
        assert "ω_n" not in out

    def test_course_overrides_global(self):
        # 全域 pronunciation.json 把 σ 念 "sigma"; 課程術語表覆寫成「應力」。
        baseline = normalize_text("這裡 σ 是材料的")
        assert "sigma" in baseline
        out = normalize_text("這裡 σ 是材料的", extra_pronunciation={"σ": "應力"})
        assert "應力" in out

    def test_default_unchanged(self):
        # 不帶 extra → 與舊呼叫完全一致（既有 caller 零影響）。
        assert normalize_text("σ 應力") == normalize_text("σ 應力", extra_pronunciation=None)

    def test_empty_extra_is_noop(self):
        assert normalize_text("ζ 阻尼", extra_pronunciation={}) == normalize_text("ζ 阻尼")
