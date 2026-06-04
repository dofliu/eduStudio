"""core.youtube 測試 — auto_youtube_meta 預填生成器 + _seconds_to_hhmmss."""
from __future__ import annotations

from core.youtube import (
    DEFAULT_TAGS_BY_SOURCE,
    _build_chapter_lines,
    _estimate_narration_seconds,
    _is_deck_schema,
    _seconds_to_hhmmss,
    _song_chapter_durs,
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


def test_default_tags_by_source_has_all_6_types():
    # 確保所有 source_type 都有預設 tags, 否則 React UI 上 tags 欄位會空白
    expected = {"exam_pdf", "slides_pdf", "repo", "document", "url", "song"}
    assert set(DEFAULT_TAGS_BY_SOURCE.keys()) == expected


# ---------- type guard / 共用 helper ----------

class TestIsDeckSchema:
    def test_deck_schema_has_sections_no_problems(self):
        assert _is_deck_schema({"deck_title": "T", "sections": []}) is True

    def test_exam_schema_has_problems(self):
        assert _is_deck_schema({"exam_title": "T", "problems": []}) is False

    def test_flattened_deck_with_problems_is_not_deck_schema(self):
        # deck 壓平成 exam schema 後同時有 sections + problems → 走 exam 路徑
        deck = {"deck_title": "T", "sections": [], "problems": []}
        assert _is_deck_schema(deck) is False

    def test_sections_must_be_list(self):
        # sections 不是 list (壞資料) → 不當 deck schema
        assert _is_deck_schema({"sections": "oops"}) is False


class TestBuildChapterLines:
    def test_first_chapter_forced_zero(self):
        lines = _build_chapter_lines([("A", 65.0), ("B", 30.0)])
        assert lines[0] == "0:00  A"
        # 第二章從 65 秒起 = 1:05
        assert lines[1] == "1:05  B"

    def test_empty(self):
        assert _build_chapter_lines([]) == []


def test_estimate_narration_seconds_min_floor():
    # 空字串 / 極短 → 最小 2 秒
    assert _estimate_narration_seconds("") == 2.0
    assert _estimate_narration_seconds("短") == 2.0
    # 長旁白按字數遞增
    assert _estimate_narration_seconds("一段比較長的旁白。" * 10) > 2.0


# ---------- auto_youtube_meta: deck schema (sections/slides) ----------

def _sample_deck() -> dict:
    return {
        "deck_title": "InduSpect AI 深度解析",
        "source_type": "document",
        "sections": [
            {
                "id": "intro",
                "title": "簡介",
                "slides": [
                    {"id": "intro_1", "title": "為什麼要做巡檢", "narration": "這段講動機。"},
                    {"id": "intro_2", "title": "系統概觀", "narration": "整體架構說明。"},
                ],
            },
            {
                "id": "method",
                "title": "方法",
                "slides": [
                    {"id": "method_1", "title": "資料前處理", "narration": "清洗資料的步驟說明很長很長很長。" * 3},
                ],
            },
        ],
    }


class TestAutoYoutubeMetaDeckSchema:
    def test_whole_deck_uses_section_chapters(self):
        # final.mp4 → stem "final" 對不到 section → 章節 = 各 section
        meta = auto_youtube_meta(_sample_deck(), "final", source_type="document")
        assert meta["title"] == "InduSpect AI 深度解析"
        desc = meta["description"]
        assert "📍 章節時間軸" in desc
        assert "0:00  簡介" in desc      # 第一章強制 0:00
        assert "方法" in desc            # 第二章存在
        # 章節用 section.title, 不該洩漏 slide 標題到整份章節列
        assert "為什麼要做巡檢" not in desc

    def test_single_section_uses_slide_chapters(self):
        # intro.mp4 → stem "intro" 對到 section → 章節 = 該章 slides
        meta = auto_youtube_meta(_sample_deck(), "intro", source_type="document")
        assert meta["title"] == "InduSpect AI 深度解析 | 簡介"
        desc = meta["description"]
        assert "0:00  為什麼要做巡檢" in desc
        assert "系統概觀" in desc

    def test_deck_tags_by_source(self):
        meta = auto_youtube_meta(_sample_deck(), "final", source_type="document")
        assert "文件講解" in meta["tags"]
        meta = auto_youtube_meta(_sample_deck(), "final", source_type="repo")
        assert "程式碼講解" in meta["tags"]

    def test_deck_privacy_and_category_defaults(self):
        meta = auto_youtube_meta(_sample_deck(), "final", source_type="document")
        assert meta["privacy"] == "unlisted"
        assert meta["category"] == "27"

    def test_section_chapters_are_cumulative(self):
        # 第二章 timestamp 應晚於 0:00 (第一章有兩個 slide 累積秒數 > 0)
        meta = auto_youtube_meta(_sample_deck(), "final", source_type="document")
        lines = [l for l in meta["description"].splitlines() if "簡介" in l or "方法" in l]
        assert lines[0].startswith("0:00")
        assert not lines[1].startswith("0:00")

    def test_empty_sections_no_chapter_block(self):
        deck = {"deck_title": "空", "sections": []}
        meta = auto_youtube_meta(deck, "final", source_type="document")
        assert "📍 章節時間軸" not in meta["description"]
        assert meta["title"] == "空"

    def test_section_without_title_falls_back(self):
        deck = {
            "deck_title": "D",
            "sections": [{"id": "s1", "slides": [{"narration": "n"}]}],
        }
        meta = auto_youtube_meta(deck, "final", source_type="repo")
        # section.title 缺 → "第 1 章"
        assert "0:00  第 1 章" in meta["description"]

    def test_title_capped_100_chars(self):
        deck = {"deck_title": "x" * 200, "sections": []}
        meta = auto_youtube_meta(deck, "final", source_type="document")
        assert len(meta["title"]) <= 100


# ---------- song schema (track_type=='song' + segments) ----------

def _sample_song() -> dict:
    return {
        "track_type": "song",
        "song_title": "此刻的溫度",
        "audio_path": "song.mp3",
        "segments": [
            {"id": "s1", "lines": ["舊書牆架在舊書裡", "停在你沒翻的那頁"],
             "start": 10.3, "end": 20.1, "image_path": "images/seg_s1.png"},
            {"id": "s2", "lines": ["咖啡熱情慢慢升起"],
             "start": 20.1, "end": 28.5, "image_path": "images/seg_s2.png"},
        ],
    }


class TestSongChapterDurs:
    def test_prepends_intro_when_first_segment_not_at_zero(self):
        # 首段 start=10.3 (有前奏) → 前面補「🎵 前奏」吃掉 gap
        durs = _song_chapter_durs(_sample_song()["segments"])
        labels = [d[0] for d in durs]
        assert labels[0] == "🎵 前奏"
        assert labels[1] == "舊書牆架在舊書裡"  # 取首句歌詞
        assert labels[2] == "咖啡熱情慢慢升起"

    def test_spacing_reconstructs_absolute_timestamps(self):
        # 餵 _build_chapter_lines 後累積時間戳應回到絕對 start (非段長累積漂移)
        durs = _song_chapter_durs(_sample_song()["segments"])
        lines = _build_chapter_lines(durs)
        assert lines[0] == "0:00  🎵 前奏"
        assert lines[1] == "0:10  舊書牆架在舊書裡"  # 絕對 10.3s
        assert lines[2] == "0:20  咖啡熱情慢慢升起"  # 絕對 20.1s

    def test_no_intro_when_first_segment_near_zero(self):
        segs = [
            {"id": "s1", "lines": ["第一句"], "start": 0.4, "end": 5.0},
            {"id": "s2", "lines": ["第二句"], "start": 20.0, "end": 25.0},
        ]
        durs = _song_chapter_durs(segs)
        assert [d[0] for d in durs] == ["第一句", "第二句"]

    def test_skips_invalid_segments(self):
        segs = [
            {"id": "bad", "lines": ["缺時間"]},                       # 無 start/end
            {"id": "ok", "lines": ["有效"], "start": 5.0, "end": 9.0},
            {"id": "rev", "lines": ["end<=start"], "start": 9.0, "end": 9.0},
        ]
        durs = _song_chapter_durs(segs)
        labels = [d[0] for d in durs]
        assert "缺時間" not in labels
        assert "end<=start" not in labels
        assert "有效" in labels

    def test_all_invalid_returns_empty(self):
        assert _song_chapter_durs([{"id": "x", "lines": []}]) == []

    def test_empty_segments(self):
        assert _song_chapter_durs([]) == []


class TestAutoYoutubeMetaSongSchema:
    def test_title_uses_song_title(self):
        meta = auto_youtube_meta(_sample_song(), "ignored", source_type="song")
        assert meta["title"] == "此刻的溫度"

    def test_problem_id_ignored_single_video(self):
        # song 整首單一影片, problem_id 不影響輸出 (傳什麼都一樣)
        a = auto_youtube_meta(_sample_song(), "final", source_type="song")
        b = auto_youtube_meta(_sample_song(), "s1", source_type="song")
        assert a == b

    def test_description_has_lyric_chapters(self):
        meta = auto_youtube_meta(_sample_song(), "final", source_type="song")
        desc = meta["description"]
        assert "📍 歌詞章節" in desc
        assert "0:00  🎵 前奏" in desc
        assert "0:10  舊書牆架在舊書裡" in desc

    def test_song_tags(self):
        meta = auto_youtube_meta(_sample_song(), "final", source_type="song")
        assert "歌曲 MV" in meta["tags"]
        assert meta["tags"] == DEFAULT_TAGS_BY_SOURCE["song"]

    def test_category_is_music(self):
        # MV 是音樂內容 → category 10 (Music), 非教學 27
        meta = auto_youtube_meta(_sample_song(), "final", source_type="song")
        assert meta["category"] == "10"
        assert meta["privacy"] == "unlisted"

    def test_title_falls_back_when_no_song_title(self):
        song = _sample_song()
        del song["song_title"]
        meta = auto_youtube_meta(song, "final", source_type="song")
        assert meta["title"] == "歌曲 MV"

    def test_no_segments_no_chapter_block(self):
        song = {"track_type": "song", "song_title": "純音樂", "segments": []}
        meta = auto_youtube_meta(song, "final", source_type="song")
        assert "📍 歌詞章節" not in meta["description"]
        assert meta["title"] == "純音樂"

    def test_song_dispatched_before_deck_and_exam(self):
        # song schema 無 sections / problems → 不該誤走 deck / exam 路徑
        meta = auto_youtube_meta(_sample_song(), "final", source_type="song")
        assert "章節時間軸" not in meta["description"]  # deck 路徑用詞
        assert "歌詞章節" in meta["description"]

    def test_title_capped_100_chars(self):
        song = {"track_type": "song", "song_title": "歌" * 200, "segments": []}
        meta = auto_youtube_meta(song, "final", source_type="song")
        assert len(meta["title"]) <= 100
