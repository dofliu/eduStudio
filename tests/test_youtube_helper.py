"""core.youtube 測試 — auto_youtube_meta 預填生成器 + _seconds_to_hhmmss."""
from __future__ import annotations

from core.youtube import (
    DEFAULT_TAGS_BY_SOURCE,
    _seconds_to_hhmmss,
    _step_durations_for_problem,
    auto_youtube_meta,
)


# ---------- _seconds_to_hhmmss ----------

class TestSecondsToHhmmss:
    def test_under_minute(self):
        assert _seconds_to_hhmmss(0) == "0:00"
        assert _seconds_to_hhmmss(5) == "0:05"
        assert _seconds_to_hhmmss(45.7) == "0:46"  # rounds

    def test_under_hour(self):
        assert _seconds_to_hhmmss(60) == "1:00"
        assert _seconds_to_hhmmss(125) == "2:05"
        assert _seconds_to_hhmmss(3540) == "59:00"

    def test_over_hour(self):
        assert _seconds_to_hhmmss(3600) == "1:00:00"
        assert _seconds_to_hhmmss(3725) == "1:02:05"
        assert _seconds_to_hhmmss(7322) == "2:02:02"


# ---------- _step_durations_for_problem ----------

class TestStepDurations:
    def test_empty_problem(self):
        assert _step_durations_for_problem({}) == []

    def test_uses_section_label_when_present(self):
        prob = {
            "steps": [
                {"_section": "觀念切入", "narration": "短旁白。"},
                {"_section": "代入計算", "narration": "另一段。"},
            ]
        }
        result = _step_durations_for_problem(prob)
        labels = [r[0] for r in result]
        assert labels == ["觀念切入", "代入計算"]

    def test_falls_back_to_display(self):
        prob = {"steps": [{"display": "F = ma 公式套用", "narration": "n"}]}
        result = _step_durations_for_problem(prob)
        # display 取前 20 字
        assert result[0][0] == "F = ma 公式套用"

    def test_duration_proportional_to_narration_length(self):
        prob = {
            "steps": [
                {"_section": "短", "narration": "短。"},                                  # 2 chars
                {"_section": "長", "narration": "這是" + "一段比較長的旁白。" * 5},     # ~50+ chars
            ]
        }
        result = _step_durations_for_problem(prob)
        short_dur, long_dur = result[0][1], result[1][1]
        assert long_dur > short_dur
        assert short_dur >= 2.0    # 最小值

    def test_strips_whitespace_from_narration_for_count(self):
        # \n 等 whitespace 不該算進中文字數
        prob = {"steps": [{"narration": "中\n文\n旁\n白"}]}
        result = _step_durations_for_problem(prob)
        # 4 個中文字, 4/3.5 + 0.6 ≈ 1.74 → max(2.0, 1.74) = 2.0
        assert result[0][1] == 2.0


# ---------- auto_youtube_meta ----------

class TestAutoYoutubeMeta:
    def test_basic(self):
        deck = {
            "exam_title": "材料力學期中考",
            "problems": [{
                "id": "q1",
                "number": "第 1 題",
                "problem": "求樑的撓度",
                "steps": [
                    {"_section": "觀念", "narration": "這題考撓度。"},
                    {"_section": "計算", "narration": "代入數值得到答案。"},
                ],
            }],
        }
        meta = auto_youtube_meta(deck, "q1", source_type="exam_pdf")
        assert "材料力學期中考" in meta["title"]
        assert "第 1 題" in meta["title"]
        assert meta["privacy"] == "unlisted"
        assert meta["category"] == "27"

    def test_description_contains_chapter_timeline(self):
        deck = {
            "exam_title": "T",
            "problems": [{
                "id": "q1",
                "number": "第 1 題",
                "problem": "題目原文",
                "steps": [
                    {"_section": "S1", "narration": "1。"},
                    {"_section": "S2", "narration": "2。"},
                ],
            }],
        }
        meta = auto_youtube_meta(deck, "q1", source_type="exam_pdf")
        # 第一個強制 0:00 (YouTube 章節格式)
        assert "0:00  S1" in meta["description"]
        # S2 有 timestamp (>= 0:00)
        assert "S2" in meta["description"]

    def test_description_includes_problem_text(self):
        deck = {
            "exam_title": "T",
            "problems": [{
                "id": "q1",
                "number": "第 1",
                "problem": "這是題目原文,要進 description。",
                "steps": [{"_section": "x", "narration": "n"}],
            }],
        }
        meta = auto_youtube_meta(deck, "q1", source_type="exam_pdf")
        assert "這是題目原文" in meta["description"]

    def test_default_tags_by_source(self):
        deck = {
            "exam_title": "T",
            "problems": [{
                "id": "q1", "number": "第 1", "problem": "t",
                "steps": [{"narration": "n"}],
            }],
        }
        # exam_pdf
        meta = auto_youtube_meta(deck, "q1", source_type="exam_pdf")
        assert "考卷解析" in meta["tags"]
        # slides_pdf
        meta = auto_youtube_meta(deck, "q1", source_type="slides_pdf")
        assert "教學簡報" in meta["tags"]
        # repo
        meta = auto_youtube_meta(deck, "q1", source_type="repo")
        assert "程式碼講解" in meta["tags"]

    def test_unknown_source_type_empty_tags(self):
        deck = {
            "exam_title": "T",
            "problems": [{
                "id": "q1", "number": "第 1", "problem": "t",
                "steps": [{"narration": "n"}],
            }],
        }
        meta = auto_youtube_meta(deck, "q1", source_type="unknown_type")
        assert meta["tags"] == []

    def test_problem_id_not_found_returns_basic_meta(self):
        deck = {
            "exam_title": "T",
            "problems": [{
                "id": "q1", "number": "第 1", "problem": "t",
                "steps": [{"narration": "n"}],
            }],
        }
        # qX 不存在 → 不爆, 回基本 meta
        meta = auto_youtube_meta(deck, "qX", source_type="exam_pdf")
        assert meta["title"] == "T"
        assert meta["description"] == ""

    def test_uses_deck_title_for_repo_type(self):
        # repo / document / url 用 deck_title 而非 exam_title
        deck = {
            "deck_title": "我的 Repo 講解",
            "problems": [{
                "id": "intro", "number": "第 1 章 ...", "problem": "t",
                "steps": [{"narration": "n"}],
            }],
        }
        meta = auto_youtube_meta(deck, "intro", source_type="repo")
        assert "我的 Repo 講解" in meta["title"]

    def test_title_max_100_chars(self):
        long_title = "a" * 200
        deck = {
            "exam_title": long_title,
            "problems": [{
                "id": "q1", "number": "n", "problem": "p",
                "steps": [{"narration": "n"}],
            }],
        }
        meta = auto_youtube_meta(deck, "q1", source_type="exam_pdf")
        assert len(meta["title"]) <= 100


def test_default_tags_by_source_has_all_5_types():
    # 確保 5 種 source_type 都有預設 tags, 否則 React UI 上 tags 欄位會空白
    expected = {"exam_pdf", "slides_pdf", "repo", "document", "url"}
    assert set(DEFAULT_TAGS_BY_SOURCE.keys()) == expected
